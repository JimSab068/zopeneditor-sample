Here is the updated **Functional Design Document** incorporating all structural, architectural, and data model changes.

---

# Conjecture-Validated Legacy Rule Extraction — Functional Design Document

**Author:** Sabdha Ambati

**Status:** Updated Draft — Post-Harness & Validator Architecture

**Target Reference Architecture:** Hypercubic HyperLoop, Loop 1 (Conjecture Generation $\rightarrow$ Mechanical Validation $\rightarrow$ Audit/Promotion)

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
* Automated conjecture generation against each extracted `SAM1` branch (heuristic and LLM-backed).
* Structural sanity checking of candidate conjectures before execution.
* Mechanical validation of each conjecture via real program execution against compiled binaries (not sampled, not LLM self-assessment).
* Audit/promotion of confirmed conjectures into a traceable business-rule ledger, and routing of refuted/unresolved conjectures into a Findings Log.
* Three documented findings from source review: an OS-coupling risk pattern class, a dead/unreachable `CRUNCH` transaction path in SAM2, and unhandled transaction types (`RPTALL`, `GEN`) in `REPTTOTL.cpy`.

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
| **Traceability** | Branch identity, source path, source lines, conjecture, execution evidence, and promoted rule remain linked. |
| **LLM non-authority** | LLM output is treated purely as an execution hypothesis; it cannot independently establish or promote a business rule. |
| **Negative validation** | At least one deliberately incorrect conjecture is mechanically refuted by the validator. |
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
             │ Conjecture    │  → Proposes input transactions
             │ Generator     │    and claimed postconditions
             │ (Heuristic/   │    (LLM treated as hypothesis agent)
             │  LLM Agent)   │
             └───────┬───────┘
                     │ Conjecture (CONJ-XXXX)
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
* **Constraint:** Branch IDs (`BR-XXXX`) must remain stable and be propagated through conjecture generation, execution, validation, and ledger promotion.

### 5.2 Conjecture Agent — **Built (Heuristic & LLM-Backed)**

* **Input:** A specific branch object from the extractor.
* **Output:** A structured `Conjecture` hypothesis containing test preconditions, fixed-width input transactions, and claimed postconditions.
* **LLM Role:** Used strictly as a hypothesis generator to synthesize inputs for complex paths. An LLM-generated conjecture that fails mechanical validation remains `refuted` or `unresolved` and is **never promoted** solely because the LLM considers it plausible.

### 5.3 Conjecture Sanity Check — **Built (In Pipeline)**

* **Input:** Generated `Conjecture`.
* **Output:** Pass/Fail decision before invoking the execution harness.
* **Function:** Pre-screens candidate hypotheses for logical contradictions or invalid test fixtures (e.g., expecting "NO MATCHING KEY" for a known existing fixture key, or expecting state sequence errors from a single isolated transaction) to prevent unnecessary execution cycles.

### 5.4 Execution Harness (Mechanical Layer) — **Built & Verified** (`harness.py`)

* **Input:** Target transaction records generated from a conjecture.
* **Output:** Captured program artifacts (`custout.txt`, `custrpt.txt`, stdout, stderr, return code).
* **Method:** Invokes compiled `SAM1` executable (with `SAM2.so` dynamic library) via subprocess in an isolated runtime environment.

### 5.5 Validator — **Built** (`conjecture_validator.py`)

* **Input:** `Conjecture` + `RunResult` from harness.
* **Output:** `ValidationResult` containing status (`confirmed`, `refuted`, `unresolved`), actual observed evidence, and failure reasons.
* **Confirmed:** Observed execution evidence completely satisfies the conjecture's claimed postcondition.
* **Refuted:** Observed execution evidence explicitly contradicts the conjecture's claim (e.g., wrong report output or unexpected record state).
* **Unresolved:** The test could not be evaluated reliably due to malformed input, harness error, or incomplete state assertions.



### 5.6 Audit Agent — **Built**

* **Input:** Mechanically validated `ValidationResult` entries.
* **Output:** Promoted `BusinessRule` entries added to the ledger.
* **Constraint:** The audit agent does **not** determine truth. Mechanical validation establishes execution facts; the audit agent formats, categorizes, and reviews confirmed conjectures for domain traceability.

---

## 6. Data Contracts

### 6.1 Pipeline Identity & Evidence Chain

$$\text{Branch (BR-XXXX)} \longrightarrow \text{Conjecture (CONJ-XXXX)} \longrightarrow \text{Execution (EXEC-XXXX)} \longrightarrow \text{Validation (VAL-XXXX)} \longrightarrow \text{Rule (RULE-XXXX)}$$

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
  "domain_summary": "When an UPDATE transaction is processed for a non-existent customer key, the system flags the transaction with 'NO MATCHING KEY' in the report and leaves customer records unchanged.",
  "source_lines": [297, 301],
  "status": "promoted"
}

```

---

## 7. Test Plan

1. **Branch Identity & Traceability Test:** Verify that `branch_id` and `source_lines` are preserved across all pipeline stages ($\text{Branch} \rightarrow \text{Conjecture} \rightarrow \text{Execution} \rightarrow \text{Validation} \rightarrow \text{Ledger}$).
2. **LLM Invalid-Input Test:** Feed malformed or non-compliant customer keys from LLM output into the generator/sanity check and verify they are rejected or normalized before harness execution.
3. **Contradictory Conjecture Sanity Test:** Provide an impossible conjecture (e.g., `key_exists = true` combined with claimed outcome `"NO MATCHING KEY"`) and assert that the sanity check intercepts it prior to binary execution.
4. **Stateful Branch Test:** Validate out-of-sequence transaction handling by generating multi-transaction sequence test cases.
5. **Negative Validator Test:** Pass a deliberately wrong claim (e.g., non-existent account `00077A` updated to `"JOHN DOE"`) through the validator to verify that the system returns `refuted` and blocks rule promotion.

---

## 8. Deliverables

1. **Source Repository:** Local GnuCOBOL adaptation of `SAM1.cbl`/`SAM2.cbl`, containing extractor, generator, sanity checker, harness, validator, and documentation generator modules.
2. **Verified Business Rule Ledger:** JSON and Markdown summary of all mechanically confirmed rules.
3. **Findings Log:** Documented record of refuted/unresolved conjectures and static COBOL code smells.
4. **Project README:** Architectural overview detailing Loop 1 mechanics, ground-truth execution guarantees, and explicit non-goals.

---

## 9. Timeline & Progress Status

| Phase | Description | Status |
| --- | --- | --- |
| **Day 1** | GnuCOBOL setup, source adaptation, manual binary end-to-end verification, execution harness build. | **Done** |
| **Day 2** | Branch extraction parser, heuristic & LLM conjecture generation, validator, findings logging. | **Done** |
| **Current Stage** | Strict data model update, `BR-XXXX` identity propagation, negative validator test suite, conjecture sanity checking. | **In Progress** |
| **Final Stage** | Grounded LLM generator tuning, full pipeline verification run, ledger/README generation. | **Pending** |