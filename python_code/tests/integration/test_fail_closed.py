"""
test_fail_closed.py — Section 7 of the functional design doc requires this
explicitly: "deliberately wrong conjecture fed into the validator to
confirm it correctly reports refuted, proving the fail-closed path
actually works and isn't just an unused code path." This was specified
but never implemented until now.
"""

import unittest
from unittest.mock import patch
from harness import RunResult
from conjecture_validator import Conjecture, ExpectedOutcome, validate_conjecture


class TestFailClosedPath(unittest.TestCase):

    @patch("conjecture_validator.get_customer_record")
    @patch("conjecture_validator.run_sam1")
    @patch("conjecture_validator.write_transaction_file")
    def test_deliberately_wrong_conjecture_is_refuted(self, mock_write, mock_run, mock_get_rec):
        """
        A conjecture that claims something the actual run contradicts must
        come back as failed, not silently pass. This is the test that
        would catch a validator with an inverted condition or a bug that
        makes it always return passed=True.
        """
        mock_run.return_value = RunResult(
            returncode=0,
            stdout="",
            stderr="",
            custout_contents="",
            report_contents="Error Processing Transaction. NO MATCHING KEY: 00099A",
            transactions_processed=[],
        )
        mock_get_rec.return_value = None  # record genuinely doesn't exist

        # Deliberately wrong: claims a successful update happened, when the
        # actual (mocked) run shows a rejection.
        wrong_conjecture = Conjecture(
            branch_id="BR-DELIBERATELY-WRONG",
            description="Incorrectly claims UPDATE succeeded against a non-existent key",
            input_transactions=["UPDATE 00099A        REPLACE  NAME"],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=["UPDATE 00099A"],  # not actually in the report
                customer_record_contains={"00099A": "SHOULD NOT EXIST"},
            ),
        )

        result = validate_conjecture(wrong_conjecture)

        self.assertFalse(result.passed, "Fail-closed path did not trigger — validator passed a wrong conjecture")
        self.assertIn("Report missing expected substring", result.reason)

    @patch("conjecture_validator.run_sam1")
    @patch("conjecture_validator.write_transaction_file")
    def test_sam1_timeout_is_reported_not_raised(self, mock_write, mock_run):
        """
        If SAM1 hangs or crashes, validate_conjecture must return a failed
        ValidationResult, not propagate an exception that would kill a
        pipeline run partway through dozens of branches.
        """
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="SAM1", timeout=10)

        conj = Conjecture(
            branch_id="BR-TIMEOUT-TEST",
            description="Should be caught, not raised",
            input_transactions=["UPDATE 00001A"],
            expected=ExpectedOutcome(),
        )

        result = validate_conjecture(conj)  # must not raise
        self.assertFalse(result.passed)
        self.assertIn("timed out", result.reason)


if __name__ == "__main__":
    unittest.main()