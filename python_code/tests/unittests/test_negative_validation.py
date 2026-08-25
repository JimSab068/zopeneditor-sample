"""
test_negative_validation.py — negative validator test suite.

Proves:
  wrong conjecture -> actual execution -> REFUTED -> NOT promoted
"""

import sys
from harness import build_transaction_line
from conjecture_validator import Conjecture, ExpectedOutcome, validate_conjecture
from ledger_builder import build_ledger


def test_negative_validation():
    print("Running Negative Validator Test...")

    # 1. Construct a deliberately wrong conjecture:
    # Claim: Updating non-existent key '00077A' will successfully modify record '00077A' with 'JOHN DOE'
    wrong_conjecture = Conjecture(
        branch_id="BR-NEG-001",
        description="Deliberately false claim: Non-existent key update modifies record",
        input_transactions=[
            build_transaction_line(
                tran_code="UPDATE",
                tran_key="00077A",
                tran_action="REPLACE",
                tran_field_name="NAME",
                name_value="JOHN DOE",
            )
        ],
        expected=ExpectedOutcome(
            returncode=0,
            report_contains=["UPDATE 00077A"],  # False: Actual report is 'NO MATCHING KEY'
            customer_record_contains={"00077A": "JOHN DOE"},  # False: Key does not exist in custout.txt
        ),
        source_lines=[297, 301],
    )

    # 2. Execute against compiled SAM1 binary via validator
    result = validate_conjecture(wrong_conjecture)

    print(f"  Execution Result Passed: {result.passed}")
    print(f"  Refutation Reason: {result.reason}")

    assert not result.passed, "FAIL: Wrong conjecture was incorrectly marked as passed!"

    # 3. Pass through Ledger Builder
    ledger = build_ledger([result])

    # 4. Verify assertion: NOT promoted, routed to findings
    promoted_ids = [r["branch_id"] for r in ledger["business_rules"]]
    finding_ids = [f["branch_id"] for f in ledger["findings"]]

    assert "BR-NEG-001" not in promoted_ids, "FAIL: False conjecture was promoted to Business Rule Ledger!"
    assert "BR-NEG-001" in finding_ids, "FAIL: Refuted conjecture was not recorded in Findings Log!"

    print("\nPROVED:")
    print("  Wrong Conjecture -> Execution -> REFUTED -> NOT Promoted (Logged in Findings)")


if __name__ == "__main__":
    try:
        test_negative_validation()
        sys.exit(0)
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)