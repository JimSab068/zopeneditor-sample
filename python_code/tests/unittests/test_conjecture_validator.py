import unittest
from unittest.mock import patch
from harness import RunResult
from conjecture_validator import (
    Conjecture,
    ExpectedOutcome,
    validate_conjecture
)

class TestConjectureValidator(unittest.TestCase):

    @patch("conjecture_validator.get_customer_record")
    @patch("conjecture_validator.run_sam1")
    @patch("conjecture_validator.write_transaction_file")
    def test_validate_conjecture_pass(self, mock_write, mock_run, mock_get_rec):
        mock_run.return_value = RunResult(
            returncode=0,
            stdout="",
            stderr="",
            custout_contents="",
            report_contents="Transaction processed: UPDATE 00001A REPLACE NAME",
            transactions_processed=["UPDATE 00001A REPLACE NAME"]
        )
        mock_get_rec.return_value = "00001A  UPDATED NAME   00100000"

        conj = Conjecture(
            branch_id="BR-001",
            description="Update name test",
            input_transactions=["UPDATE 00001A        REPLACE  NAME"],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=["UPDATE 00001A"],
                customer_record_contains={"00001A": "UPDATED NAME"}
            )
        )

        result = validate_conjecture(conj)
        self.assertTrue(result.passed)
        self.assertEqual(result.reason, "All expectations met")
        mock_write.assert_called_once_with(conj.input_transactions)

    @patch("conjecture_validator.get_customer_record")
    @patch("conjecture_validator.run_sam1")
    @patch("conjecture_validator.write_transaction_file")
    def test_validate_conjecture_fail_report(self, mock_write, mock_run, mock_get_rec):
        mock_run.return_value = RunResult(
            returncode=0,
            stdout="",
            stderr="",
            custout_contents="",
            report_contents="Transaction error",
            transactions_processed=[]
        )

        conj = Conjecture(
            branch_id="BR-001",
            description="Update name test",
            input_transactions=["UPDATE 00001A"],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=["UPDATE 00001A"]
            )
        )

        result = validate_conjecture(conj)
        self.assertFalse(result.passed)
        self.assertIn("Report missing expected substring", result.reason)

if __name__ == "__main__":
    unittest.main()