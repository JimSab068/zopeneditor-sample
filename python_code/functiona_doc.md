# Conjecture-Validated Legacy Rule Extraction — Functional Design Document

**Author:** Sabdha Ambati
**Status:** Draft — pre-implementation
**Target reference architecture:** Hypercubic HyperLoop, Loop 1 (conjecture generation → mechanical validation → audit/promotion)

---

## 1. Problem Statement

Modernizing a legacy COBOL program requires knowing, with evidence, what the program actually does — not what it appears to do from reading the source, and not what an LLM guesses it does from a summary. Plausible translation is not the hard problem; proving behavioral correctness is.

This project implements a small, self-contained analog of the first stage of that problem: given a legacy COBOL program, produce a set of business-rule claims about its behavior, each one backed by mechanical evidence (an actual program execution), not model assertion.

## 2. Scope

**In scope:**
- Two COBOL programs (`SAM1.cbl` + `SAM2.cbl`, a customer-file transaction processor with inter-program `CALL` linkage, Apache-2.0 licensed, sourced from IBM's official `zopeneditor-sample` repository), adapted for local GnuCOBOL execution
- Full branch enumeration of `SAM1`'s control flow (7-9 reachable paths: out-of-sequence, UPDATE match/no-match with SAM2's internal success/fail split, ADD match/no-match, DELETE match/no-match, invalid transaction code, comment-skip)
- `SAM2` treated as **black-box tested** via a handful of representative integration cases (NAME update, BALANCE replace, BALANCE add, non-numeric rejection, invalid field) rather than exhaustive internal branch coverage — a deliberate scope decision given the time box, stated here and in the README rather than left implicit
- Automated conjecture generation against each SAM1 branch
- Mechanical validation of each conjecture via real program execution (not sampled, not LLM self-assessment)
- Audit/promotion of validated conjectures into a traceable business-rule ledger
- Three documented findings from source review: an OS-coupling risk pattern class (kept general, not tied to this specific source), a dead/unreachable `CRUNCH` transaction path in SAM2 (reachable in SAM2's own logic, never dispatched by SAM1's caller contract), and evidence in `REPTTOTL.cpy` of additional transaction types (`RPTALL`, `GEN`) that the current `SAM1` procedure logic never dispatches — all logged rather than silently dropped or silently "fixed"

**Out of scope (explicitly, and stated as such in deliverables):**
- Formal verification (Dafny/SMT-style proof of memory safety, type correctness) — this system produces empirical evidence from concrete executions, not mathematical proof
- Exhaustive multi-program dependency analysis beyond the single SAM1→SAM2 call
- State beyond flat sequential files (`custfile.txt`/`custout.txt`/`tranfile.txt`) — no CICS, no VSAM, no JCL orchestration
- Live/production traffic replay
- Simulation-twin compilation (Isomorphic-style COBOL→verified-IR→modern-runtime pipeline)

This project targets a scaled-down analog of Loop 1 only. Loops 2 and 3 require infrastructure (a verification-aware compiler, live mainframe access) that is out of scope for a solo, time-boxed build.

## 3. Goals / Success Criteria

| Goal | Success criterion |
|---|---|
| Full branch coverage | All reachable branches in `SAM1.cbl` have at least one generated conjecture |
| Mechanical validation | Every conjecture is checked against a real compiled-binary execution, not an LLM's self-report |
| Traceability | Every promoted rule links to the specific source lines it was derived from |
| Fail-closed behavior | A conjecture that cannot be mechanically confirmed is never promoted, and is reported as unresolved rather than silently dropped |
| Honest scoping | Deliverable README states plainly what this is (Loop 1 analog, SAM1 full coverage + SAM2 black-box) and is not (formal verification, exhaustive SAM2 internal coverage) |

## 4. System Architecture

```
COBOL source (SAM1.cbl)
        │
        ▼
 ┌─────────────────────┐
 │ Branch Extractor     │  → enumerates reachable control-flow paths
 └─────────┬────────────┘
           │ branch list
           ▼
 ┌─────────────────────┐
 │ Conjecture Agent     │  → LLM proposes a testable claim per branch
 └─────────┬────────────┘
           │ conjecture (input spec + expected outcome)
           ▼
 ┌─────────────────────┐
 │ Execution Harness    │  → runs compiled SAM1 (+ SAM2 as a loadable
 │ (mechanical layer)   │     module) via subprocess against a generated
 │                       │     transaction file; reads back custout.txt
 │                       │     and the report for structured evidence
 └─────────┬────────────┘
           │ observed outcome
           ▼
 ┌─────────────────────┐
 │ Validator             │  → compares observed vs. claimed outcome
 └─────────┬────────────┘
           │ pass / fail + evidence
           ▼
 ┌─────────────────────┐
 │ Audit Agent           │  → reviews validated conjectures, promotes
 │ (critic)              │     to business rule, tags source trace
 └─────────┬────────────┘
           │
           ▼
   Business Rule Ledger (JSON + human-readable summary)
   Findings Log (unresolved conjectures + code smells)
```

## 5. Components

### 5.1 Branch Extractor — **not yet built**
- **Input:** COBOL source file path (`SAM1.cbl`)
- **Output:** list of `{branch_id, condition_path, source_lines}` — the reachable paths enumerated in Section 2
- **Method:** targeted parse of `PROCEDURE DIVISION` conditional structure (the `EVALUATE TRAN-CODE` in `100-PROCESS-TRANSACTIONS` and the nested `IF`s in `200`/`210`/`220`) — not a full COBOL grammar, scoped to this program's actual control structure
- **Status note:** branch enumeration currently exists as manual source analysis (documented in the compatibility checklist), not as automated extraction. This is the component actively being built next.

### 5.2 Conjecture Agent — not yet built
- **Input:** one branch (condition path + source context)
- **Output:** a structured conjecture — `{branch_id, preconditions, claimed_postcondition}`, e.g. *"if account found and transaction type = UPDATE with a matching key, SAM2 is called and the named field is updated per its action code"*
- **Constraint:** conjecture must be phrased as a checkable claim, not prose explanation

### 5.3 Execution Harness (mechanical layer) — **built** (`harness.py`)
- **Input:** compiled `SAM1` binary (with `SAM2` compiled as a loadable module via `cobc -m`, discovered at runtime via `COB_LIBRARY_PATH`), a set of transaction records targeting specific branches
- **Output:** full contents of `custout.txt` (post-transaction customer file) and the generated report (`custrpt.txt`, which already contains structured "Transaction processed: ..." lines used as evidence), plus stdout/stderr/return code
- **Method:** subprocess invocation against a generated fixed-width transaction file (`tranfile.txt`, built field-by-field per `TRANREC.cpy`'s exact 80-byte layout) — each run is a fresh process, so `SAM1`'s working-storage (including the out-of-sequence check) resets naturally between test cases with no manual state reset needed
- **Note:** this is the ground-truth oracle — nothing here is LLM-generated or LLM-assessed. Confirmed correct against a manual end-to-end run (UPDATE/ADD/DELETE all verified against expected output before automation began)

### 5.4 Validator — not yet built
- **Input:** conjecture + harness output
- **Output:** `{branch_id, status: confirmed | refuted, evidence}`
- **Method:** deterministic comparison of claimed postcondition against observed file/report state

### 5.5 Audit Agent (critic) — not yet built
- **Input:** all validated conjectures
- **Output:** promoted business rule entries (only for `confirmed` status), each tagged with source line numbers
- **Fail-closed rule:** a `refuted` or inconclusive conjecture is never promoted; it is written to the findings log instead, with the reason it failed

### 5.6 Business Rule Ledger (deliverable artifact)
- Format: JSON (machine-readable) + a rendered markdown summary
- Fields per entry: `rule_id`, `description`, `source_lines`, `validated_by` (input case used as evidence), `status`

### 5.7 Findings Log (deliverable artifact)
- Any conjecture that failed mechanical validation
- The three findings from source review listed in Section 2, documented as first-class tracked objects rather than silently patched or dropped

## 6. Data Contracts

```json
// Conjecture
{
  "branch_id": "update_no_matching_key",
  "preconditions": {"tran_code": "UPDATE", "tran_key": "00099A", "key_exists_in_custfile": false},
  "claimed_postcondition": "transaction rejected, 'NO MATCHING KEY:' logged, no record written",
  "source_lines": [297, 301]
}

// Validation result
{
  "branch_id": "update_no_matching_key",
  "status": "confirmed",
  "evidence": {
    "input": {"tran_code": "UPDATE", "tran_key": "00099A", "action": "REPLACE", "field": "NAME"},
    "report_line": "Error Processing Transaction. NO MATCHING KEY: 00099A",
    "custout_changed": false
  }
}

// Promoted rule (ledger entry)
{
  "rule_id": "R-003",
  "description": "An UPDATE transaction against a key not present in the customer file is rejected without any output-file change.",
  "source_lines": [297, 301],
  "validated_by": "branch_id=update_no_matching_key",
  "status": "promoted"
}
```

## 7. Test Plan

- Unit-level: each component (extractor, harness, validator) tested independently with hand-constructed fixtures before wiring the full loop
- End-to-end: every branch in the enumeration (Section 2) must reach `confirmed` status against the real compiled binary before the ledger is considered complete
- Negative case: deliberately wrong conjecture fed into the validator to confirm it correctly reports `refuted`, proving the fail-closed path actually works and isn't just an unused code path

## 8. Deliverables

1. Source repository — a fork of IBM's `zopeneditor-sample` on the `local-gnucobol-adaptation` branch, containing the adapted `SAM1.cbl`/`SAM2.cbl`, plus the extractor/agents/harness/validator as clearly separated modules
2. Business Rule Ledger (JSON + markdown) for `SAM1.cbl`
3. Findings Log
4. README stating scope, explicit non-goals (see Section 2), and how this maps to Loop 1 of the reference architecture
5. *(Stretch, time-permitting)* MCP server wrapper exposing `validate_conjecture(cobol_path, conjecture) → {status, evidence}` as a callable tool

## 9. Timeline

| Day | Work | Status |
|---|---|---|
| Day 1 | Environment setup (GnuCOBOL), source adaptation (`ASSIGN TO`, `COPY IN`, `ORGANIZATION IS LINE SEQUENTIAL`), manual end-to-end verification of SAM1+SAM2 against sample data | **Done** — clean run confirmed correct (UPDATE/ADD/DELETE all verified against expected output) |
| Day 2 | Branch extractor, conjecture agent, validator, audit agent wired end-to-end; ledger and findings log generated; README written; stretch: MCP wrapper | **In progress** — execution harness (`harness.py`) built and confirmed working; branch extractor next |

## 10. Explicit Limitations (stated for the reader, not hidden)

This system produces empirical, execution-backed evidence for a small program pair (`SAM1`/`SAM2`) with flat-file state and no external I/O beyond the filesystem. It does not constitute formal verification, does not handle CICS/VSAM/JCL-level state, and was not tested against adversarial or production-scale input distributions. `SAM2` is validated as a black box via representative cases, not exhaustively. It demonstrates the agentic orchestration pattern (generate → mechanically check → fail-closed audit) at a scale tractable for a two-day solo build, not the full engineering substrate a production system would require.