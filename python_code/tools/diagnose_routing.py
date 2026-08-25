"""
diagnose_routing.py — Dry-run branch classification. No LLM calls, no
harness execution, no compiled binary needed. Just parsing + classification.

Run this BEFORE any --llm pipeline run so --llm-limit is set from the real
number of branches the heuristic generator has to guess on, not a round
number picked in advance.
"""

import argparse
from collections import Counter

from branch_extractor import parse_cobol, enumerate_branches
from conjecture_generator import classify_branch_confidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cobol_path", nargs="?", default="COBOL/SAM1.cbl")
    parser.add_argument("--entry", default="100-PROCESS-TRANSACTIONS")
    parser.add_argument("--rpm", type=float, default=4.0,
                        help="Your model's requests-per-minute cap, used only "
                             "to print a rough time estimate.")
    args = parser.parse_args()

    print(f"Parsing {args.cobol_path}...")
    ast, order = parse_cobol(args.cobol_path)
    branches = enumerate_branches(ast, args.entry)
    print(f"Discovered {len(branches)} reachable branches from '{args.entry}'.\n")

    counts = Counter()
    low_confidence_ids = []

    for b in branches:
        category, confidence = classify_branch_confidence(b)
        counts[(category, confidence)] += 1
        if confidence == "low":
            low_confidence_ids.append(b["branch_id"])

    print(f"{'Category':16s} {'Confidence':10s} Count")
    print("-" * 40)
    for (category, confidence), n in sorted(counts.items()):
        print(f"{category:16s} {confidence:10s} {n}")

    total_low = sum(n for (_, conf), n in counts.items() if conf == "low")
    total_high = sum(n for (_, conf), n in counts.items() if conf == "high")

    print("-" * 40)
    print(f"Total: {total_low} low-confidence (LLM candidates)")
    print(f"       {total_high} high-confidence (heuristic resolves cleanly)\n")

    est_minutes = total_low / args.rpm
    print(f"Recommended --llm-limit: {total_low}")
    print(f"At {args.rpm:.1f} RPM, generating conjectures for all {total_low} would take "
          f"~{est_minutes:.0f} min of LLM call time alone (excludes harness execution time).")
    print("Setting --llm-limit below this caps Gemini spend; the excess low-confidence")
    print("branches just fall back to the heuristic's existing guess, same as today.\n")

    out_path = "low_confidence_branch_ids.txt"
    with open(out_path, "w") as f:
        f.write("\n".join(low_confidence_ids) + "\n")
    print(f"Wrote {len(low_confidence_ids)} low-confidence branch IDs to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())