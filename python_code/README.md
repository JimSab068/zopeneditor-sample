# Conjecture-Validated Legacy Rule Extraction

## Overview

Modernizing legacy COBOL is not only a code-translation problem. The difficult part is establishing, with evidence, what the existing system actually does.

This project implements a **conjecture-validated legacy rule extraction pipeline**. It treats COBOL behavior as something to be experimentally tested rather than inferred solely from source code or generated explanations.

The system:

1. Extracts reachable control-flow paths from legacy COBOL.
2. Assigns each path a stable branch identity.
3. Routes branches between deterministic heuristic generation and LLM-assisted generation based on the confidence of the existing heuristic.
4. Generates executable conjectures about program behavior.
5. Rejects structurally contradictory conjectures before execution.
6. Executes accepted conjectures against compiled COBOL binaries.
7. Compares claimed behavior with observed execution evidence.
8. Promotes only mechanically passing validations into the business-rule ledger.
9. Records failed validations as findings together with their failure reasons.
10. The intended pipeline supports checkpointed/resumable execution; the exact orchestration behavior should remain synchronized with the current pipeline runner.

The central design principle is:

> **The LLM proposes hypotheses. Program execution establishes evidence.**

An LLM can therefore help generate tests, but it is never treated as the authority on what the legacy system does.

---

## Project Scope

The current implementation targets two COBOL programs:

- `SAM1.cbl`
- `SAM2.cbl`

The programs originate from IBM's official `zopeneditor-sample` repository and have been adapted for local **GnuCOBOL** execution.

### Current scope

- Full reachable control-flow path extraction for `SAM1`.
- `SAM2` exercised through representative black-box integration cases.
- Confidence-based routing between heuristic and LLM conjecture generation.
- Pre-execution conjecture sanity checks.
- Mechanical execution against compiled binaries.
- Validation of return codes, reports, transaction processing, and customer-record state.
- Checkpointed/resumable pipeline execution where supported by the pipeline runner.
- Ledger promotion of mechanically passing validations.
- Findings capture for failed validations and source-review observations.

The current extractor produces **1,086 reachable control-flow path candidates** for `SAM1.cbl`.

These are **control-flow candidates, not 1,086 independent business rules**. Business-level interpretation remains based on the underlying transaction behavior and coverage of the original business cases.

`SAM2` is not exhaustively enumerated internally. It is treated as a black box and tested through representative integration cases such as NAME updates, BALANCE replacement/addition, non-numeric rejection, and invalid-field behavior.

---

## Architecture

```text
                         SAM1.cbl
                            |
                            v
                  +---------------------+
                  |   Branch Extractor  |
                  |---------------------|
                  | conditions          |
                  | execution path      |
                  | source lines        |
                  +----------+----------+
                             |
                     BR-XXXX identity
                             |
                             v
                  +---------------------+
                  |   Confidence Router |
                  |---------------------|
                  | deterministic/high  |
                  | ambiguous/low       |
                  +----------+----------+
                             |
                    routing decision
                             |
                             v
              +------------------------------+
              |    Conjecture Generator      |
              |------------------------------|
              | heuristic                    |
              | LLM                          |
              | LLM -> heuristic fallback    |
              +--------------+---------------+
                             |
                       CONJ-XXXX
                             |
                             v
                  +---------------------+
                  |   Sanity Checker    |
                  +----------+----------+
                             |
                     valid hypothesis
                             |
                             v
                  +---------------------+
                  |   Execution Harness |
                  |---------------------|
                  | SAM1 executable     |
                  | SAM2.so             |
                  | file outputs        |
                  | stdout/stderr       |
                  | return code         |
                  +----------+----------+
                             |
                     EXEC-XXXX evidence
                             |
                             v
                  +---------------------+
                  |      Validator      |
                  +----------+----------+
                             |
              +--------------+--------------+
              |              |              |
          CONFIRMED       REFUTED      UNRESOLVED
              |              |              |
              v              +------+-------+
        Audit / Promote             |
              |                     v
              v               Findings Log
      Business Rule Ledger
```

Every stage preserves the identity of the behavior being analyzed:

```text
Branch
  -> Routing Decision
  -> Conjecture
  -> Execution
  -> Validation
  -> Promoted Rule
```

---

## Components

### 1. Branch Extractor

**Module:** `branch_extractor.py`

The branch extractor performs a targeted parse of the COBOL `PROCEDURE DIVISION`.

It is intentionally **not a full COBOL grammar**. The current parser is scoped to the source style used by the project:

- fixed-format COBOL columns
- one clause per line
- explicit scope terminators such as `END-IF` and `END-EVALUATE`

The parser builds an internal AST for structures including:

- `IF`
- `EVALUATE`
- `PERFORM`
- `CALL`
- ordinary statements

Each reachable path receives:

- `branch_id`
- conditions
- execution path
- source line numbers
- terminal information

The branch identifier (`BR-XXXX`) is required to survive all later pipeline stages.

---

### 2. Confidence Router

**Modules:** `complexity_router.py` and the routing logic in `conjecture_generator.py`

The router determines whether the existing deterministic heuristic generator can resolve a branch without guessing.

A branch is classified using:

- transaction category
- confidence level
- routing reason

The confidence categories are:

- **high** — the heuristic can resolve the branch deterministically
- **low** — the heuristic would need to make an ambiguous/best-effort guess

The routing decision is designed to mirror the behavior of the actual heuristic generator instead of relying on an unrelated structural approximation.

This matters because the router should answer:

> "Can the generator that we actually use resolve this branch?"

rather than:

> "Does this branch look simple?"

### Current corpus

For the current `SAM1.cbl` corpus:

| Category | Count |
|---|---:|
| ADD / high | 318 |
| DELETE / high | 312 |
| UPDATE / high | 150 |
| INVALID_CODE / high | 78 |
| OUT_OF_SEQUENCE / high | 39 |
| UPDATE / low | 150 |
| UNCLASSIFIED / low | 39 |
| **Total** | **1,086** |

The documented corpus therefore contains:

- **897 high-confidence branches**
- **189 low-confidence branches**

The router sends only up to the configured `llm_budget` of low-confidence branches to the LLM; remaining low-confidence branches are handled by the heuristic path along with all high-confidence branches. The exact number of LLM calls therefore depends on the configured budget.

---

### 3. Conjecture Generator

The conjecture generator produces executable hypotheses containing:

- branch identity
- source lines
- routing metadata
- preconditions
- fixed-width input transactions
- claimed return code
- claimed report output
- claimed customer-record state

Each conjecture records where it came from:

```text
heuristic
llm
llm_fallback_to_heuristic
```

The LLM is intentionally limited to the role of **hypothesis generation**.

If an LLM-generated conjecture fails sanity checking or mechanical validation, it is not promoted simply because it sounds plausible. The pipeline can fall back to the heuristic generator and records that fallback explicitly.

---

### 4. Sanity Checker

**Module:** `sanity_checker.py`

The sanity checker prevents obviously contradictory hypotheses from reaching the execution layer.

Examples of checks include:

- empty transaction inputs
- mutually exclusive error reports
- error reports combined with customer-record updates
- non-zero return codes combined with claimed record updates
- record updates for keys not represented in the transaction inputs

The purpose is not to establish program truth. It is to eliminate hypotheses that are internally inconsistent before consuming execution or LLM resources.

---

### 5. Execution Harness

**Module:** `harness.py`

The harness is the mechanical ground-truth layer.

It executes the compiled COBOL program rather than asking an LLM whether a conjecture is plausible.

The harness captures artifacts including:

- return code
- `custout.txt`
- `custrpt.txt`
- processed transactions
- stdout
- stderr
- customer-record state

The runtime invokes the compiled `SAM1` executable with the `SAM2` shared library available through `COB_LIBRARY_PATH`.

---

### 6. Conjecture Validator

**Module:** `conjecture_validator.py`

The validator compares:

```text
claimed outcome
       vs.
observed execution outcome
```

The validation process checks:

1. return code
2. expected report substrings
3. expected customer-record state

The current validator returns a boolean `passed` value together with observed evidence and a failure reason. A failed result may represent a contradicted claim, a sanity rejection, an execution failure, or another inability to verify the claim. The current `ValidationResult` model does not have a dedicated status field separating `refuted` from `unresolved`.

The ledger builder currently records failed validations under `status: "unresolved"` together with the specific failure reason. Only `passed=True` validations are eligible for promotion.

A deliberately incorrect conjecture therefore fails closed rather than becoming a promoted business rule.

---

### 7. Pipeline Orchestration and Checkpointing

**Module:** `run_pipeline.py`

The orchestration layer connects the full workflow.

It supports flags such as:

```text
--llm
--llm-limit
--fresh
```

After each branch, the pipeline appends a full evidence record to:

```text
pipeline_checkpoint.jsonl
```

The checkpoint records enough information to resume after:

- API rate limits
- daily quota exhaustion
- network interruptions
- process termination
- infrastructure failures

On restart, already-processed branches are skipped rather than being sent back through the LLM or execution harness.

`--fresh` allows a clean rerun when prior results have been invalidated by a code change, such as a classifier fix.

---

### 8. Ledger Builder / Promotion Layer

**Module:** `ledger_builder.py`

The promotion layer operates **after** mechanical validation. It:

- preserves branch ID and source lines
- preserves conjecture description and input transactions
- stores claimed and observed outcomes when available
- promotes `passed=True` results into `business_rules`
- records failed results in `findings` with the validation reason

The current ledger uses `promoted` and `unresolved` statuses. It does not currently expose first-class `refuted` and `untestable_requires_fault_injection` statuses.

Truth is established by mechanical validation; the ledger builder does not independently determine truth.

---

### 9. Rule Consolidator

**Module:** `rule_consolidator.py`

Promoted micro-branch rules can be consolidated into higher-level business rules.

The consolidator:

- groups promoted rules by description/intent
- aggregates covered branch IDs
- aggregates micro-rule IDs when present
- unions source-line coverage
- preserves sample input transactions
- preserves an observed outcome when supplied
- calculates the number of branches represented by each consolidated rule

The consolidated ledger also retains the raw business rules and findings, providing a higher-level business-rule view without discarding lower-level entries.

---

## Evidence and Data Contracts

The system maintains an explicit identity chain:

```text
BR-XXXX
   |
   v
Routing Decision
   |
   v
CONJ-XXXX
   |
   v
Execution Evidence
   |
   v
VAL-XXXX
   |
   v
RULE-XXXX
```

A representative branch looks like:

```json
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
```

A generated conjecture extends this with routing and behavioral claims:

```json
{
  "conjecture_id": "CONJ-0421",
  "branch_id": "BR-0421",
  "source_lines": [297, 301],
  "generation_source": "heuristic",
  "routing_reason": "UPDATE/high",
  "preconditions": {
    "tran_code": "UPDATE",
    "tran_key": "00077A",
    "key_exists_in_custfile": false
  },
  "input_transactions": [
    "UPDATE 00077A        REPLACE  NAME        JOHN DOE"
  ],
  "claimed_postcondition": {
    "expected_returncode": 0,
    "expected_report_contains": ["NO MATCHING KEY"],
    "expected_customer_record_contains": {}
  }
}
```

The resulting validation record preserves both the claim and the observed evidence.

---

## LLM Design Principles

The project deliberately separates **generation** from **verification**.

### What the LLM does

The LLM can:

- interpret ambiguous branch conditions
- propose transaction inputs
- propose expected postconditions
- help formulate a conjecture where deterministic generation cannot confidently do so

The supplied client uses AWS Bedrock; the current default model ID is `google.gemma-3-27b-it`.

### What the LLM does not do

The LLM cannot:

- declare a rule true
- promote a rule directly
- replace binary execution
- override a failed validator result

An LLM response is treated as an executable hypothesis that must pass the subsequent validation path before it can contribute to a promoted rule.

---

## Rate Limiting 

The confidence router reduces API usage by separating low- and high-confidence branches. Only the first `llm_budget` low-confidence branches are routed to the LLM; the rest follow the heuristic path.

For the current 1,086-branch corpus:

```text
1,086 total branches
 ├── 897 high-confidence
 └── 189 low-confidence / LLM-eligible
```

The actual number of LLM requests therefore depends on the configured budget.


---

## Findings

The implementation surfaced several findings that are important both for the COBOL application and for the extraction system itself.

The findings section intentionally describes analytical outcomes that are not all represented as distinct ledger status values. For example, `refuted` and `untestable_requires_fault_injection` are useful interpretations of particular failures, but the current ledger code records failed validations as `unresolved` with a detailed reason.

### 1. OS-coupling risk

The source contains environmental and filesystem assumptions that need explicit consideration during modernization.

### 2. Dead `CRUNCH` transaction path

A `CRUNCH` transaction path exists in `SAM2`, but no reachable trigger was found under the current entry point/extraction scope.

### 3. Unhandled transaction types

`RPTALL` and `GEN` appear in `REPTTOTL.cpy` without corresponding processing branches.

### 4. Heuristic classifier defect

An early ADD-branch classifier used loose substring matching:

```text
"ADD" + "PROCESS"
```

This was dangerously broad because the COBOL `ADD` verb and the ubiquitous `PROCESS` paragraph name appeared on many unrelated paths.

The result was:

```text
1,066 / 1,086 branches (98%)
```

being incorrectly classified as ADD.

The defect was detected with zero-cost diagnostic tooling before corrupted routing could produce/promote conjectures.

The classifier was corrected to anchor the fallback to the actual business signal:

```text
TRAN-CODE = 'ADD'
```

The corrected corpus reconciles to:

```text
ADD              318
DELETE           312
UPDATE           300
INVALID_CODE      78
OUT_OF_SEQUENCE   39
UNCLASSIFIED      39
--------------------
TOTAL           1,086
```

This is an important example of the project's core philosophy being applied to its own tooling: a plausible result was not trusted until it was checked against actual evidence.

### 5. Untestable runtime-dependent branches

Nine branches downstream of `WS-CUSTOUT-STATUS = OTHER` were mechanically refuted because no normal transaction input can deterministically produce the required condition.

The analysis indicates that `WS-CUSTOUT-STATUS` is populated through the customer output file's COBOL runtime `FILE STATUS`, making these branches dependent on an OS/filesystem-level write failure rather than ordinary transaction semantics.

These are better categorized as:

```text
untestable_requires_fault_injection
```

rather than ordinary unresolved business rules.

A future harness capable of intentionally injecting a file-write failure would be required to test these paths.

---

## Testing Strategy

The functional design identifies the following important test classes:

### Branch identity and traceability

Verify that `branch_id` and `source_lines` remain linked through extraction, routing, conjecture generation, execution, validation, and ledger promotion.

### Router fidelity

Verify that the confidence router agrees with the behavior of the actual heuristic generator.

### Invalid LLM input

Verify malformed or non-compliant LLM-generated transactions are rejected or normalized before execution.

### Sanity rejection

Verify contradictory conjectures are blocked before consuming execution resources.

### Stateful transaction behavior

Validate transaction-sequence-dependent conditions such as out-of-sequence handling.

### Negative validation

Send an intentionally incorrect claim through the validator and verify that validation fails and the claim cannot be promoted.

### Checkpoint resume

Interrupt a run, restart it without `--fresh`, and verify that completed branches are not re-executed or sent to the LLM again.

---




---

## Limitations

This project is intentionally scoped.

It does **not** currently provide:

- formal SMT/Dafny-style verification
- exhaustive multi-program dependency analysis
- broad CICS/VSAM/JCL modernization
- live traffic replay
- isomorphic COBOL-to-IR runtime compilation
- exhaustive internal branch coverage of `SAM2`
- automatic fault injection for OS/filesystem-dependent behavior

The architecture is best understood as a **Loop 1 analogue**:

> conjecture generation -> mechanical validation -> audit/promotion

rather than a complete legacy modernization platform.

