
---

# Conjecture-Validated Legacy Rule Extraction — Functional Design Document

**Author:** Sabdha Ambati

---

## 1. Problem Statement

Modernizing a legacy COBOL program requires knowing, with evidence, what the program actually does — not what it appears to do from reading the source, and not what an LLM guesses it does from a summary. Plausible translation is not the hard problem; proving behavioral correctness is.

This system generates executable hypotheses (conjectures) about legacy COBOL program behavior, experimentally executes them against compiled binaries, and promotes only those behaviors supported by concrete execution evidence into a verified Business Rule Ledger.

---

## 2. Scope

**In Scope:**

* Two COBOL programs (`SAM1.cbl` + `SAM2.cbl`, a customer-file transaction processor with inter-program `CALL` linkage, Apache-2.0 licensed, sourced from IBM's official `zopeneditor-sample` repository), adapted for local GnuCOBOL execution.
* Full reachable control-flow path enumeration of `SAM1` under the current targeted parser. The current extractor produces **1,086 reachable branch/path candidates** for `SAM1.cbl`. These are finer-grained control-flow paths and should not be interpreted as 1,086 distinct business rules. The original 7–9 cases remain the intended business-level behavior categories used for interpretation and coverage analysis.
* `SAM2` treated as **black-box tested** via representative integration cases (NAME update, BALANCE replace, BALANCE add, non-numeric rejection, invalid field) rather than exhaustive internal branch coverage.
* Confidence-based routing of extracted branches between deterministic (heuristic) conjecture generation and LLM-backed generation, so LLM budget is spent only where the heuristic classifier cannot resolve a branch unambiguously. Against the current corpus this routes **189 of 1,086 branches (~17%) to the LLM**, with the remaining **897 resolved deterministically at zero API cost**.
* Structural sanity checking of candidate conjectures before execution.
* Mechanical validation of each conjecture via real program execution against compiled binaries (not sampled, not LLM self-assessment).
* Rate-limit-safe, checkpointed pipeline execution: LLM calls respect the account's actual per-minute quota, and per-branch progress is persisted to disk so a run can be paused (rate limit, daily quota reset, network interruption) and resumed without re-spending LLM budget or re-executing already-validated branches.
* Audit/promotion of confirmed conjectures into a traceable business-rule ledger, and routing of refuted/unresolved conjectures into a Findings Log.
* Four documented findings from source review and tooling development: an OS-coupling risk pattern class, a dead/unreachable `CRUNCH` transaction path in SAM2, unhandled transaction types (`RPTALL`, `GEN`) in `REPTTOTL.cpy`, and a branch-classification defect in the project's own heuristic conjecture generator (see §9, Finding 4) discovered through diagnostic tooling before it could contaminate the promoted rule ledger.

**Out of Scope:**

* Formal verification (Dafny/SMT-style proof of memory safety or type correctness).
* Exhaustive multi-program dependency analysis beyond the single SAM1 $\rightarrow$ SAM2 call.
* Flat file persistence beyond sequential `custfile.txt`/`custout.txt`/`tranfile.txt` (no CICS, VSAM, JCL).
* Live traffic replay or isomorphic COBOL-to-IR runtime compilation.

---

## 3. Goals / Success Criteria

| Goal | Success Criterion |
| --- | --- |
| **Control-flow coverage** | Every reachable branch/path emitted by the current extractor has at least one generated conjecture. |
| **Mechanical validation** | Every executable conjecture is evaluated against a real compiled `SAM1`/`SAM2` execution. |
| **Fail-closed behavior** | Only mechanically confirmed conjectures can be promoted; unconfirmed hypotheses are never promoted. |
| **Traceability** | Branch identity, source path, source lines, conjecture, generation source (heuristic vs. LLM), execution evidence, and promoted rule remain linked. |
| **LLM non-authority** | LLM output is treated purely as an execution hypothesis; it cannot independently establish or promote a business rule. |
| **LLM budget discipline** | LLM calls are reserved for branches the deterministic classifier cannot resolve confidently, and the run respects the account's real rate limit rather than an assumed one. |
| **Negative validation** | At least one deliberately incorrect conjecture is mechanically refuted by the validator. |
| **Resumability** | A pipeline run interrupted at any point (rate limit, daily quota reset, process kill) can resume from its last completed branch without re-spending LLM calls or re-running the harness on already-validated branches. |
| **Honest scoping** | Deliverable README explicitly states scope limitations (Loop 1 analog, SAM1 full path extraction + SAM2 black-box integration). |

---

## 4. System Architecture

```
                  SAM1.cbl
                     │
                     ▼
             ┌───────────────┐
             │ Branch        │  → Emits path, conditions,
             │ Extractor     │    and exact source lines
             └───────┬───────┘
                     │ Branch Identity (BR-XXXX)
                     ▼
             ┌───────────────┐
             │ Confidence    │  → Classifies each branch as
             │ Router        │    heuristic-resolvable ("high")
             │ (dry-run,     │    or heuristic-ambiguous ("low"),
             │  no LLM cost) │    with zero LLM/harness calls
             └───────┬───────┘
                     │ Routing Decision + Reason
                     ▼
             ┌───────────────┐
             │ Conjecture    │  → Proposes input transactions
             │ Generator     │    and claimed postconditions.
             │ (Heuristic    │    "high"-confidence branches never
             │  or LLM,      │    touch the LLM; "low"-confidence
             │  per routing) │    branches spend LLM budget, with
             └───────┬───────┘    heuristic fallback on rejection
                     │ Conjecture (CONJ-XXXX) + generation_source
                     ▼
             ┌───────────────┐
             │ Conjecture    │  → Filters structural contradictions
             │ Sanity Check  │    and bad test fixtures pre-run
             └───────┬───────┘
                     │ Validated Hypothesis
                     ▼
             ┌───────────────┐
             │ Execution     │  → Subprocess execution of compiled
             │ Harness       │    SAM1/SAM2 binary; captures file
             │               │    state, reports, stdout/stderr
             └───────┬───────┘
                     │ Execution Evidence (EXEC-XXXX)
                     ▼
             ┌───────────────┐
             │ Validator     │  → Compares claimed postconditions
             └───────┬───────┘    against observed evidence
                     │
                     ├──────────► Checkpoint (pipeline_checkpoint.jsonl)
                     │            written after every branch, enabling
                     │            pause/resume across quota resets
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
      CONFIRMED   REFUTED   UNRESOLVED
          │          │          │
          ▼          └────┬─────┘
   ┌─────────────┐        │
   │ Audit Agent │        ▼
   └──────┬──────┘   Findings Log
          │
          ▼
   Business Rule
      Ledger

```

---

## 5. Components

### 5.1 Branch Extractor — **Built**

* **Input:** COBOL source file path (`SAM1.cbl`).
* **Output:** List of `{branch_id, conditions, path, source_lines}` objects.
* **Method:** Targeted parse of `PROCEDURE DIVISION` conditional structures (including `EVALUATE` and nested `IF` branches). Produces 1,086 reachable control-flow path candidates for `SAM1.cbl`.
* **Constraint:** Branch IDs (`BR-XXXX`) must remain stable and be propagated through routing, conjecture generation, execution, validation, and ledger promotion.

### 5.2 Confidence Router — **Built** (`complexity_router.py`, `classify_branch_confidence` in `conjecture_generator.py`)

* **Input:** A branch object from the extractor.
* **Output:** `(category, confidence)` — category is one of `UPDATE`, `ADD`, `DELETE`, `INVALID_CODE`, `OUT_OF_SEQUENCE`, `UNCLASSIFIED`; confidence is `"high"` (the heuristic generator resolves this branch deterministically, e.g. a clean no-matching-key or duplicate-key polarity check) or `"low"` (the heuristic would have to guess, e.g. an undetermined field name or ambiguous condition polarity).
* **Method:** Mirrors the real control flow of `_heuristic_generator` exactly, rather than an independent structural proxy (branch depth, condition count, etc.) — this guarantees the routing decision reflects what the deterministic generator would actually do, not an approximation of it.
* **Diagnostic tooling:** `diagnose_routing.py` runs this classification across the full branch corpus with zero LLM calls and zero harness executions, producing a category/confidence histogram and a recommended `--llm-limit` before any API quota is spent. Against the current `SAM1.cbl` corpus: 897 branches resolve at "high" confidence (ADD 318, DELETE 312, UPDATE 150, INVALID_CODE 78, OUT_OF_SEQUENCE 39), and 189 resolve at "low" confidence (UPDATE 150, UNCLASSIFIED 39).
* **Constraint:** Low-confidence branches are the only branches eligible to spend LLM budget; if the configured budget is smaller than the low-confidence count, the excess falls back to the heuristic generator's existing best-effort guess rather than being skipped.

### 5.3 Conjecture Agent — **Built (Heuristic & Confidence-Routed LLM)**

* **Input:** A specific branch object from the extractor, plus its routing decision from the Confidence Router.
* **Output:** A structured `Conjecture` hypothesis containing test preconditions, fixed-width input transactions, and claimed postconditions — now additionally tagged with `generation_source` (`"heuristic"`, `"llm"`, or `"llm_fallback_to_heuristic"`) and `routing_reason` (the category/confidence pair that produced the routing decision), so every promoted rule carries an auditable explanation of how it was derived.
* **LLM Role:** Used strictly as a hypothesis generator, and only for branches the deterministic classifier could not resolve on its own. An LLM-generated conjecture that fails structural sanity checking or mechanical validation falls back to the heuristic generator and is tagged `llm_fallback_to_heuristic`; it is **never promoted** solely because the LLM considers it plausible.
* **Rate-limit handling:** the shared LLM client (`llm_clients.py`) enforces a request interval matching the account's actual per-minute cap (not an assumed higher one), with exponential backoff on 429/quota-exhausted responses.

### 5.4 Conjecture Sanity Check — **Built (In Pipeline)**

* **Input:** Generated `Conjecture`.
* **Output:** Pass/Fail decision before invoking the execution harness.
* **Function:** Pre-screens candidate hypotheses for logical contradictions or invalid test fixtures (e.g., expecting "NO MATCHING KEY" for a known existing fixture key, or expecting state sequence errors from a single isolated transaction) to prevent unnecessary execution cycles.

### 5.5 Execution Harness (Mechanical Layer) — **Built & Verified** (`harness.py`)

* **Input:** Target transaction records generated from a conjecture.
* **Output:** Captured program artifacts (`custout.txt`, `custrpt.txt`, stdout, stderr, return code).
* **Method:** Invokes compiled `SAM1` executable (with `SAM2.so` dynamic library) via subprocess in an isolated runtime environment.

### 5.6 Validator — **Built** (`conjecture_validator.py`)

* **Input:** `Conjecture` + `RunResult` from harness.
* **Output:** `ValidationResult` containing status (`confirmed`, `refuted`, `unresolved`), actual observed evidence, and failure reasons.
* **Confirmed:** Observed execution evidence completely satisfies the conjecture's claimed postcondition.
* **Refuted:** Observed execution evidence explicitly contradicts the conjecture's claim (e.g., wrong report output or unexpected record state).
* **Unresolved:** The test could not be evaluated reliably due to malformed input, harness error, or incomplete state assertions.

### 5.7 Pipeline Orchestration & Checkpointing — **Built** (`run_pipeline.py`)

* **Input:** Full branch corpus, routing decisions, CLI flags (`--llm`, `--llm-limit`, `--fresh`).
* **Output:** Per-branch checkpoint records (`pipeline_checkpoint.jsonl`), consolidated ledger, functional spec document.
* **Method:** After every branch's validation, a full evidence record (conjecture, generation source, routing reason, claimed/observed outcome, pass/fail) is appended to a checkpoint file. On restart, already-checkpointed branches are skipped — the pipeline neither re-spends LLM budget nor re-executes the harness for branches it has already mechanically confirmed or refuted. `--fresh` discards the checkpoint for a clean rerun (e.g., after a fix to the heuristic generator invalidates prior results).
* **Rationale:** at free-tier LLM rate limits, a full-corpus run spans tens of minutes to hours; checkpointing makes the run safely interruptible across rate-limit windows, daily quota resets, or infrastructure hiccups without losing evidence already gathered.

### 5.8 Audit Agent — **Built**

* **Input:** Mechanically validated `ValidationResult` entries.
* **Output:** Promoted `BusinessRule` entries added to the ledger.
* **Constraint:** The audit agent does **not** determine truth. Mechanical validation establishes execution facts; the audit agent formats, categorizes, and reviews confirmed conjectures for domain traceability.

---

## 6. Data Contracts

### 6.1 Pipeline Identity & Evidence Chain

$$\text{Branch (BR-XXXX)} \longrightarrow \text{Routing Decision} \longrightarrow \text{Conjecture (CONJ-XXXX)} \longrightarrow \text{Execution (EXEC-XXXX)} \longrightarrow \text{Validation (VAL-XXXX)} \longrightarrow \text{Rule (RULE-XXXX)}$$

### 6.2 Data Schemas

```json
// 1. Branch Contract (Extractor Output)
{
  "branch_id": "BR-0421",
  "conditions": [
    "TRAN-CODE = 'UPDATE'",
    "CUST-KEY NOT FOUND"
  ],
  "path": [
    "100-PROCESS-TRANSACTIONS",
    "200-PROCESS-UPDATE-TRAN"
  ],
  "source_lines": [297, 301]
}

// 2. Conjecture Contract (Generator Output)
{
  "conjecture_id": "CONJ-0421",
  "branch_id": "BR-0421",
  "source_lines": [297, 301],
  "generation_source": "heuristic", // "heuristic" | "llm" | "llm_fallback_to_heuristic"
  "routing_reason": "UPDATE/high",
  "preconditions": {
    "tran_code": "UPDATE",
    "tran_key": "00077A",
    "key_exists_in_custfile": false
  },
  "input_transactions": [
    "UPDATE 00077A        REPLACE  NAME        JOHN DOE                            "
  ],
  "claimed_postcondition": {
    "expected_returncode": 0,
    "expected_report_contains": ["NO MATCHING KEY"],
    "expected_customer_record_contains": {}
  }
}

// 3. Validation Result Contract (Validator Output)
{
  "validation_id": "VAL-0421",
  "conjecture_id": "CONJ-0421",
  "branch_id": "BR-0421",
  "generation_source": "heuristic",
  "routing_reason": "UPDATE/high",
  "status": "confirmed", // "confirmed" | "refuted" | "unresolved"
  "reason": "All expectations met",
  "observed_evidence": {
    "actual_returncode": 0,
    "actual_report_text": "Transaction processed: UPDATE 00077A NO MATCHING KEY",
    "customer_record_found": false,
    "stdout": "",
    "stderr": ""
  }
}

// 4. Promoted Business Rule Ledger Contract
{
  "rule_id": "RULE-0421",
  "branch_id": "BR-0421",
  "conjecture_id": "CONJ-0421",
  "validation_id": "VAL-0421",
  "generation_source": "heuristic",
  "routing_reason": "UPDATE/high",
  "domain_summary": "When an UPDATE transaction is processed for a non-existent customer key, the system flags the transaction with 'NO MATCHING KEY' in the report and leaves customer records unchanged.",
  "source_lines": [297, 301],
  "status": "promoted"
}

```

---

## 7. Test Plan

1. **Branch Identity & Traceability Test:** Verify that `branch_id` and `source_lines` are preserved across all pipeline stages ($\text{Branch} \rightarrow \text{Routing} \rightarrow \text{Conjecture} \rightarrow \text{Execution} \rightarrow \text{Validation} \rightarrow \text{Ledger}$).
2. **Routing Classifier Fidelity Test:** For a sample of branches per category, assert that `classify_branch_confidence`'s "high"/"low" decision matches what `_heuristic_generator` would actually produce — i.e., the router never marks a branch "high" that the generator would in fact have to guess on, and vice versa. (This test class would have caught the ADD-classifier defect in §9, Finding 4, before it reached the ledger.)
3. **LLM Invalid-Input Test:** Feed malformed or non-compliant customer keys from LLM output into the generator/sanity check and verify they are rejected or normalized before harness execution.
4. **Contradictory Conjecture Sanity Test:** Provide an impossible conjecture (e.g., `key_exists = true` combined with claimed outcome `"NO MATCHING KEY"`) and assert that the sanity check intercepts it prior to binary execution.
5. **Stateful Branch Test:** Validate out-of-sequence transaction handling by generating multi-transaction sequence test cases.
6. **Negative Validator Test:** Pass a deliberately wrong claim (e.g., non-existent account `00077A` updated to `"JOHN DOE"`) through the validator to verify that the system returns `refuted` and blocks rule promotion.
7. **Checkpoint Resume Test:** Interrupt a pipeline run partway through (simulated process kill after N branches), restart without `--fresh`, and assert that (a) no branch already in the checkpoint is re-validated or re-sent to the LLM, and (b) the final ledger is identical to an uninterrupted run over the same corpus.

---

## 8. Deliverables

1. **Source Repository:** Local GnuCOBOL adaptation of `SAM1.cbl`/`SAM2.cbl`, containing extractor, confidence router, generator, sanity checker, harness, validator, checkpointed pipeline orchestrator, and documentation generator modules.
2. **Verified Business Rule Ledger:** JSON and Markdown summary of all mechanically confirmed rules, tagged with generation source and routing reason.
3. **Findings Log:** Documented record of refuted/unresolved conjectures, static COBOL code smells, and the tooling defect described in §9.
4. **Project README:** Architectural overview detailing Loop 1 mechanics, ground-truth execution guarantees, confidence-routing rationale, and explicit non-goals.

---

## 9. Findings

1. **OS-coupling risk pattern class** (source review) — identified path/environment assumptions in the COBOL source that would need explicit handling during modernization.
2. **Dead/unreachable `CRUNCH` transaction path in SAM2** (source review) — a transaction code branch with no reachable trigger under the current extractor's entry point.
3. **Unhandled transaction types (`RPTALL`, `GEN`) in `REPTTOTL.cpy`** (source review) — transaction codes referenced in the copybook with no corresponding processing branch.
4. **Branch-classification defect in the project's own heuristic conjecture generator** (tooling development) — `_is_add_branch`'s fallback matched on the loose combination of the substrings `"ADD"` and `"PROCESS"` anywhere in a branch's path. Because COBOL's arithmetic `ADD` verb (e.g. incrementing a running transaction counter) appears on nearly every transaction path, and `"PROCESS"` trivially matches the entry paragraph name present on every path, this caused **1,066 of 1,086 branches (98%)** to misclassify as ADD-type, silently swallowing all DELETE and OUT_OF_SEQUENCE branches (0 of each detected) and corrupting the routing decision for every other category. Caught before any conjectures were generated or promoted, via a zero-cost diagnostic script (`inspect_conditions.py`) run against the classifier's actual condition-string output rather than trusting its aggregate counts. Fixed by anchoring the fallback to the actual business signal (`TRAN-CODE = 'ADD'`) instead of independent substring matches. Post-fix corpus: ADD 318, DELETE 312, UPDATE 300, INVALID_CODE 78, OUT_OF_SEQUENCE 39, UNCLASSIFIED 39 — totals reconcile to all 1,086 branches. This finding is itself a demonstration of the system's core thesis applied recursively: a plausible-looking classification (correct on the 3-branch sample originally spot-checked) was not trusted until checked against ground truth.
5. **A class of branches with no valid transaction-level conjecture at all** (mechanical validation) — 9 branches (all downstream of `WHEN WS-CUSTOUT-STATUS = OTHER`, reachable from multiple distinct upstream flows: the transaction-file-EOF record-copy path and the full `UPDATE` path through `CALL SAM2`) were routed to the LLM as low-confidence, and all 9 were mechanically refuted. Root cause, confirmed against source (`SAM1.cbl:48`): `WS-CUSTOUT-STATUS` is declared as the `FILE STATUS` clause for the customer output file, populated exclusively by the COBOL runtime after each `WRITE` — never by any transaction field. No input transaction can deterministically trigger this branch; the true precondition is an OS/filesystem-level write failure (disk full, permission denied), outside what this harness's fixture strategy can express. Given an unsatisfiable task, the LLM did not flag the impossibility — it produced a conjecture with a transaction shape copied verbatim from its own few-shot prompt example (`tran_key: "00002A"`, `tran_action: "REPLACE"`, `tran_field_name: "NAME"`, `name_value: "NEW NAME"`, identical across all 9 branches), substituting only the one salient string actually present in the branch — the COBOL literal from the `MOVE` statement — into `expected_report`. The validator correctly refuted all 9 (0 false promotions). Classified separately from ordinary `unresolved` findings as **`untestable_requires_fault_injection`**, since the fix is a different harness strategy (mocking the `WRITE` syscall to fail), not a better conjecture. Folded into Finding 1 (OS-coupling risk pattern class) as a second, independently-discovered instance of the same underlying pattern — this time surfaced through mechanical validation of an LLM hypothesis rather than manual source review.

---

## 10. Timeline & Progress Status

| Phase | Description | Status |
| --- | --- | --- |
| **Day 1** | GnuCOBOL setup, source adaptation, manual binary end-to-end verification, execution harness build. | **Done** |
| **Day 2** | Branch extraction parser, heuristic & LLM conjecture generation, validator, findings logging. | **Done** |
| **Day 3** | Confidence-based LLM routing (`classify_branch_confidence`, `complexity_router.py`), zero-cost diagnostic tooling (`diagnose_routing.py`, `inspect_conditions.py`), rate-limiter correction to match actual account quota, checkpointed/resumable pipeline orchestration, `generation_source`/`routing_reason` traceability fields. | **Done** |
| **Day 3 (cont.)** | Discovered and fixed `_is_add_branch` classification defect (§9, Finding 4) via diagnostic tooling before any LLM-generated conjectures were produced against the corrupted routing. | **Done** |
| **Current Stage** | Full 1,086-branch pipeline run (897 heuristic, 189 LLM-routed) pending execution; targeted checkpointed run given free-tier rate limits. | **In Progress** |
| **Final Stage** | Full-corpus ledger/README generation, routing-classifier fidelity test suite (Test Plan §7.2), UNCLASSIFIED-bucket review for a possible sixth branch category. | **Pending** |