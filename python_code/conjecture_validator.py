from dataclasses import dataclass, field
from sanity_checker import check_conjecture_sanity
from harness import write_transaction_file, run_sam1, get_customer_record, RunResult
import subprocess

@dataclass
class ExpectedOutcome:
    """The CLAIMED outcome asserted by the conjecture."""
    returncode: int = 0
    report_contains: list[str] = field(default_factory=list)
    customer_record_contains: dict[str, str] = field(default_factory=dict)  # key -> expected substring


@dataclass
class ObservedOutcome:
    """The OBSERVED outcome gathered directly from binary execution."""
    returncode: int
    report_contents: str
    transactions_processed: list[str]
    customer_records: dict[str, str | None] = field(default_factory=dict)  # key -> actual record line (or None)


@dataclass
class Conjecture:
    branch_id: str
    description: str
    input_transactions: list[str]
    expected: ExpectedOutcome
    source_lines: list[int] = field(default_factory=list)


@dataclass
class ValidationResult:
    conjecture: Conjecture
    passed: bool
    claimed: ExpectedOutcome
    observed: ObservedOutcome | None
    actual_run: RunResult | None
    reason: str = ""

# conjecture_validator.py — add two fields to Conjecture
@dataclass
class Conjecture:
    branch_id: str
    description: str
    input_transactions: list[str]
    expected: ExpectedOutcome
    source_lines: list[int] = field(default_factory=list)
    generation_source: str = "heuristic"   # "heuristic" | "llm" | "llm_fallback_to_heuristic"
    routing_reason: str = ""               # e.g. "UPDATE/low: ambiguous polarity"

def validate_conjecture(conjecture: Conjecture) -> ValidationResult:
    """
    Executes a conjecture through the harness, captures actual observed state 
    into ObservedOutcome, and validates it against claimed ExpectedOutcome.
    """

    is_sane, sanity_reason = check_conjecture_sanity(conjecture)
    if not is_sane:
        return ValidationResult(
            conjecture=conjecture,
            passed=False,
            claimed=conjecture.expected,
            observed=None,
            actual_run=None,
            reason=f"SANITY REJECTED: {sanity_reason}",
        )

    write_transaction_file(conjecture.input_transactions)

    try:
        run_res = run_sam1()
    except subprocess.TimeoutExpired:
        return ValidationResult(
            conjecture=conjecture,
            passed=False,
            claimed=conjecture.expected,
            observed=None,
            actual_run=None,
            reason="SAM1 execution timed out (possible infinite loop or hang in generated input)",
        )
    except (OSError, FileNotFoundError) as e:
        return ValidationResult(
            conjecture=conjecture,
            passed=False,
            claimed=conjecture.expected,
            observed=None,
            actual_run=None,
            reason=f"SAM1 could not be executed: {e}",
        )

    # Gather observed customer record states for every key mentioned in the claim
    observed_records = {}
    for key in conjecture.expected.customer_record_contains.keys():
        observed_records[key] = get_customer_record(key)

    observed = ObservedOutcome(
        returncode=run_res.returncode,
        report_contents=run_res.report_contents,
        transactions_processed=run_res.transactions_processed,
        customer_records=observed_records,
    )

    # Check 1: Return Code
    if run_res.returncode != conjecture.expected.returncode:
        return ValidationResult(
            conjecture=conjecture,
            passed=False,
            claimed=conjecture.expected,
            observed=observed,
            actual_run=run_res,
            reason=f"Expected returncode {conjecture.expected.returncode}, got {run_res.returncode}"
        )

    # Check 2: Report Substrings
    for expected_str in conjecture.expected.report_contains:
        found_in_processed = any(expected_str in proc for proc in run_res.transactions_processed)
        found_in_raw_report = expected_str in run_res.report_contents

        if not (found_in_processed or found_in_raw_report):
            return ValidationResult(
                conjecture=conjecture,
                passed=False,
                claimed=conjecture.expected,
                observed=observed,
                actual_run=run_res,
                reason=f"Report missing expected substring: '{expected_str}'"
            )

    # Check 3: Customer Record Substrings
    for key, expected_sub in conjecture.expected.customer_record_contains.items():
        record = observed_records.get(key)
        if not record or expected_sub not in record:
            return ValidationResult(
                conjecture=conjecture,
                passed=False,
                claimed=conjecture.expected,
                observed=observed,
                actual_run=run_res,
                reason=f"Customer record '{key}' missing expected substring '{expected_sub}' (Actual: '{record}')"
            )

    return ValidationResult(
        conjecture=conjecture,
        passed=True,
        claimed=conjecture.expected,
        observed=observed,
        actual_run=run_res,
        reason="All expectations met"
    )