"""
sanity_checker.py — Pre-execution verification for Conjectures.

Catches logically impossible or contradictory hypotheses before 
binary execution or LLM conjecture acceptance.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conjecture_validator import Conjecture

ERROR_REPORTS = {
    "NO MATCHING KEY",
    "DUPLICATE KEY",
    "INVALID TRAN CODE",
    "TRANSACTION OUT OF SEQUENCE",
}


def check_conjecture_sanity(conjecture: "Conjecture") -> tuple[bool, str]:
    """
    Validates internal consistency and non-contradictory assertions.

    Returns:
        (is_sane, reason)
    """
    # 1. Non-empty input check
    if not conjecture.input_transactions:
        return False, "Conjecture contains no input transactions."

    expected = conjecture.expected
    reports = set(expected.report_contains)

    # 2. Mutually exclusive report errors
    found_errors = [
        err for err in ERROR_REPORTS if any(err in r for r in reports)
    ]
    if len(found_errors) > 1:
        return (
            False,
            f"Mutually exclusive error reports claimed: {found_errors}.",
        )

    # 3. Contradiction: Error report claimed AND record update claimed
    has_error_report = len(found_errors) > 0
    if has_error_report and expected.customer_record_contains:
        return (
            False,
            f"Contradiction: Claims error report '{found_errors[0]}' but expects customer record update for key(s) {list(expected.customer_record_contains.keys())}.",
        )

    # 4. Contradiction: Non-zero returncode AND record update claimed
    if expected.returncode != 0 and expected.customer_record_contains:
        return (
            False,
            "Contradiction: Claims customer record modification on non-zero return code.",
        )

    # 5. Key Alignment Check: Asserting record updates on untargeted keys
    tx_keys = set()
    for tx in conjecture.input_transactions:
        if len(tx) >= 13:
            tx_keys.add(tx[7:13].strip())

    for rec_key in expected.customer_record_contains.keys():
        if tx_keys and rec_key not in tx_keys:
            return (
                False,
                f"Contradiction: Expects record change on key '{rec_key}' which is not present in transaction input keys {list(tx_keys)}.",
            )

    return True, "Sanity check passed."