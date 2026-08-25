"""
run_pipeline.py — Complete end-to-end pipeline execution:
COBOL Source -> AST Extraction -> Conjecture Generation -> Harness Validation ->
Ledger Consolidation -> Functional Spec Generation.

Updates in this version:
  - LLM budget is spent only on branches the heuristic generator would
    otherwise have to guess on (see conjecture_generator.classify_branch_confidence),
    instead of the first N branches in enumeration order.
  - Every result carries generation_source ("heuristic" | "llm" |
    "llm_fallback_to_heuristic") and routing_reason, so the ledger stays
    traceable about *why* a conjecture was generated the way it was.
  - Progress is checkpointed to disk after every branch, so a run can be
    stopped (rate limit, RPD cap, network) and resumed later without
    losing already-validated evidence or re-spending LLM budget.
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from branch_extractor import parse_cobol, enumerate_branches
from conjecture_generator import generate_conjecture_for_branch
from conjecture_validator import (
    Conjecture,
    ExpectedOutcome,
    ObservedOutcome,
    ValidationResult,
    validate_conjecture,
)
from complexity_router import route_branches
from ledger_builder import build_ledger, write_ledger, write_markdown
from rule_consolidator import build_consolidated_ledger
from functional_doc_generator import generate_functional_doc

CHECKPOINT_PATH = Path("pipeline_checkpoint.jsonl")


def load_checkpoint() -> dict[str, ValidationResult]:
    """
    Reconstructs full ValidationResults for branches already processed in
    a prior invocation of this script, so a resumed run's final ledger
    includes them without re-running the harness or re-spending LLM budget.
    """
    done: dict[str, ValidationResult] = {}
    if not CHECKPOINT_PATH.exists():
        return done

    with open(CHECKPOINT_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)

            conj = Conjecture(
                branch_id=rec["branch_id"],
                description=rec["description"],
                input_transactions=rec["input_transactions"],
                expected=ExpectedOutcome(**rec["claimed"]),
                source_lines=rec["source_lines"],
                generation_source=rec["generation_source"],
                routing_reason=rec["routing_reason"],
            )
            observed = ObservedOutcome(**rec["observed"]) if rec["observed"] else None

            done[rec["branch_id"]] = ValidationResult(
                conjecture=conj,
                passed=rec["passed"],
                claimed=conj.expected,
                observed=observed,
                actual_run=None,  # raw subprocess evidence isn't persisted across runs
                reason=rec["reason"],
            )
    return done


def append_checkpoint(result: ValidationResult) -> None:
    c = result.conjecture
    rec = {
        "branch_id": c.branch_id,
        "description": c.description,
        "input_transactions": c.input_transactions,
        "source_lines": c.source_lines,
        "generation_source": c.generation_source,
        "routing_reason": c.routing_reason,
        "claimed": asdict(c.expected),
        "observed": asdict(result.observed) if result.observed else None,
        "passed": result.passed,
        "reason": result.reason,
    }
    with open(CHECKPOINT_PATH, "a") as f:
        f.write(json.dumps(rec) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cobol_path", nargs="?", default="COBOL/SAM1.cbl")
    parser.add_argument("--entry", default="100-PROCESS-TRANSACTIONS")
    parser.add_argument("--llm", action="store_true",
                        help="Use live LLM for conjecture generation and documentation.")
    parser.add_argument("--llm-limit", type=int, default=200,
                        help="Max number of low-confidence branches routed to the LLM. "
                             "Branches the heuristic generator resolves cleanly never use LLM budget.")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore any existing checkpoint file and start over.")
    args = parser.parse_args()

    if args.fresh and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        print(f"--fresh: removed existing {CHECKPOINT_PATH}\n")

    print(f"Parsing {args.cobol_path}...")
    ast, order = parse_cobol(args.cobol_path)

    branches = enumerate_branches(ast, args.entry)
    print(f"Discovered {len(branches)} reachable branches from '{args.entry}'.\n")

    llm_client = None
    daily_quota = None
    if args.llm:
        try:
            from llm_clients import live_gemini_client
            llm_client = live_gemini_client
            try:
                from llm_clients import gemini_daily_quota
                daily_quota = gemini_daily_quota
                print(f"Daily quota: {daily_quota.remaining()}/{daily_quota.daily_limit} "
                      f"remaining today (Pacific date, resets at midnight PT).\n")
            except ImportError:
                print("No daily quota tracker in this LLM client — running without a daily cap.\n")
        except ImportError as e:
            print(f"WARNING: Could not import llm_clients ({e}); falling back to heuristic generator.\n")

    llm_branches, heuristic_branches = route_branches(branches, args.llm_limit)
    llm_ids = {b["branch_id"] for b in llm_branches}

    if args.llm:
        print(f"Routing: {len(llm_branches)} low-confidence branches -> LLM "
              f"(budget {args.llm_limit}), {len(heuristic_branches)} -> heuristic only.\n")

    checkpointed = load_checkpoint()
    if checkpointed:
        print(f"Resuming from checkpoint: {len(checkpointed)}/{len(branches)} "
              f"branches already validated.\n")

    quota_exhausted_notice_shown = False
    results: list[ValidationResult] = []
    for branch in branches:
        bid = branch.get("branch_id")

        if bid in checkpointed:
            results.append(checkpointed[bid])
            continue

        use_llm_here = llm_client is not None and bid in llm_ids
        if use_llm_here and daily_quota is not None and not daily_quota.can_make_request():
            if not quota_exhausted_notice_shown:
                print(f"\nDaily quota exhausted (0/{daily_quota.daily_limit} remaining). "
                      f"Remaining LLM-routed branches are being left UNPROCESSED for this "
                      f"run (not checkpointed as heuristic) so they still get a real LLM "
                      f"attempt on the next run, after the Pacific midnight reset.\n")
                quota_exhausted_notice_shown = True
            # Skip entirely rather than silently falling back to heuristic —
            # falling back here and checkpointing it would permanently lock
            # this branch out of ever getting an LLM attempt on resume.
            continue

        client = llm_client if use_llm_here else None

        conj = generate_conjecture_for_branch(branch, llm_client=client)
        result = validate_conjecture(conj)
        results.append(result)
        append_checkpoint(result)

        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] ({conj.generation_source}) {conj.branch_id}: {conj.description[:60]}")
        if not result.passed:
            print(f"         reason: {result.reason}")

    # Step 1: Build & Consolidate Ledger
    raw_ledger = build_ledger(results)
    consolidated_ledger = build_consolidated_ledger(raw_ledger)
    write_ledger(consolidated_ledger)
    write_markdown(consolidated_ledger)

    # Step 2: Generate Functional Specification Document
    doc = generate_functional_doc(results, llm_client=llm_client if args.llm else None)
    with open("functional_spec.md", "w") as f:
        f.write(doc)

    s = raw_ledger["summary"]
    llm_used = sum(1 for r in results if r.conjecture.generation_source == "llm")
    llm_fallback = sum(1 for r in results if r.conjecture.generation_source == "llm_fallback_to_heuristic")

    print(f"\n{'='*60}")
    print(f"{s['rules_promoted']}/{s['total_branches_tested']} branches mechanically confirmed "
          f"({s['unresolved_findings']} unresolved)")
    if args.llm:
        print(f"LLM generation used: {llm_used} branches "
              f"({llm_fallback} LLM attempts rejected, fell back to heuristic)")
    print("Outputs written to business_rule_ledger.json, business_rule_ledger.md, and functional_spec.md")
    print(f"Checkpoint: {CHECKPOINT_PATH} ({len(results)} branches recorded)")

    return 0 if s["unresolved_findings"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())