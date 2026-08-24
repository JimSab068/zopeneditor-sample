import unittest
from harness import build_transaction_line, SAM1_BINARY
from conjecture_validator import (
    Conjecture,
    ExpectedOutcome,
    validate_conjecture,
)


class TestSAM1SAM2Integration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not SAM1_BINARY.exists():
            raise unittest.SkipTest(
                "SAM1 binary not found in python_code/. Compile SAM1 and SAM2 first."
            )

    def test_update_name_conjecture(self):
        """Integration test: Verify SAM1/SAM2 updates customer name in custout.txt."""
        tx_line = build_transaction_line(
            tran_code="UPDATE",
            tran_key="00002A",
            tran_action="REPLACE",
            tran_field_name="NAME",
            name_value="VAL-TEST CORP",
        )
        conj = Conjecture(
            branch_id="BR-UPDATE-NAME-001",
            description="Validate REPLACE NAME on record 00002A",
            input_transactions=[tx_line],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=["UPDATE 00002A"],
                customer_record_contains={"00002A": "VAL-TEST CORP"},
            ),
        )

        result = validate_conjecture(conj)
        self.assertTrue(result.passed, f"Conjecture failed: {result.reason}")

    def test_update_balance_conjecture(self):
        """Integration test: Verify SAM1/SAM2 processes BALANCE add transaction."""
        tx_line = build_transaction_line(
            tran_code="UPDATE",
            tran_key="00002A",
            tran_action="ADD",
            tran_field_name="BALANCE",
            numeric_value="250.00",
        )
        conj = Conjecture(
            branch_id="BR-UPDATE-BAL-001",
            description="Validate ADD BALANCE on record 00002A",
            input_transactions=[tx_line],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=["UPDATE 00002A        ADD      BALANCE"],
                customer_record_contains={"00002A": "00002A"},
            ),
        )

        result = validate_conjecture(conj)
        self.assertTrue(result.passed, f"Conjecture failed: {result.reason}")


if __name__ == "__main__":
    unittest.main()