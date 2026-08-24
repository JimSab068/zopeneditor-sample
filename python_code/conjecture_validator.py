from dataclasses import dataclass, field
from harness import write_transaction_file, run_sam1, get_customer_record, RunResult

@dataclass
class ExpectedOutcome:
    returncode: int = 0
    report_contains: list[str] = field(default_factory=list)
    customer_record_contains: dict[str, str] = field(default_factory=dict)  # key -> substring


@dataclass
class Conjecture:
    branch_id: str
    description: str
    input_transactions: list[str]
    expected: ExpectedOutcome


@dataclass
class ValidationResult:
    conjecture: Conjecture
    passed: bool
    actual_run: RunResult
    reason: str = ""


def validate_conjecture(conjecture: Conjecture) -> ValidationResult:
    """
    Executes a conjecture through the harness and checks actual run artifacts 
    against expectations. Returns a structured ValidationResult.
    """
    write_transaction_file(conjecture.input_transactions)
    run_res = run_sam1()

    if run_res.returncode != conjecture.expected.returncode:
        return ValidationResult(
            conjecture=conjecture,
            passed=False,
            actual_run=run_res,
            reason=f"Expected returncode {conjecture.expected.returncode}, got {run_res.returncode}"
        )

    for expected_str in conjecture.expected.report_contains:
        found_in_processed = any(expected_str in proc for proc in run_res.transactions_processed)
        found_in_raw_report = expected_str in run_res.report_contents
        
        if not (found_in_processed or found_in_raw_report):
            return ValidationResult(
                conjecture=conjecture,
                passed=False,
                actual_run=run_res,
                reason=f"Report missing expected substring: '{expected_str}'"
            )

    for key, expected_sub in conjecture.expected.customer_record_contains.items():
        record = get_customer_record(key)
        if not record or expected_sub not in record:
            return ValidationResult(
                conjecture=conjecture,
                passed=False,
                actual_run=run_res,
                reason=f"Customer record '{key}' missing expected substring '{expected_sub}' (Actual: '{record}')"
            )

    return ValidationResult(
        conjecture=conjecture,
        passed=True,
        actual_run=run_res,
        reason="All expectations met"
    )