import unittest
from unittest.mock import patch
from harness import (
    build_transaction_line,
    _parse_report,
    get_customer_record,
    RunResult,
    RECORD_LENGTH,
)


class TestHarness(unittest.TestCase):

    def test_build_transaction_line_length(self):
        """Verify output always strictly adheres to the 80-byte record length."""
        line = build_transaction_line(
            tran_code="UPDATE",
            tran_key="00001A",
            tran_action="REPLACE",
            tran_field_name="NAME",
            name_value="IBM-RTP",
        )
        self.assertEqual(len(line), RECORD_LENGTH)

    def test_build_transaction_line_positive_numeric(self):
        """Verify numeric formatting aligns + sign, 6 integer digits, and 2 cent digits."""
        line = build_transaction_line(
            tran_code="UPDATE",
            tran_key="00001A",
            tran_action="ADD",
            tran_field_name="BALANCE",
            numeric_value="150.00",
        )
        self.assertEqual(len(line), RECORD_LENGTH)
        # Offsets 44:53 -> sign (+), 6 digits (000150), 2 cents (00)
        self.assertEqual(line[44:53], "+00015000")

    def test_build_transaction_line_negative_numeric(self):
        """Verify negative numeric values properly place the '-' at byte offset 44."""
        line = build_transaction_line(
            tran_code="UPDATE",
            tran_key="00001A",
            tran_action="ADD",
            tran_field_name="ORDERS",
            numeric_value="-25.50",
        )
        self.assertEqual(line[44:53], "-00002550")

    def test_build_transaction_line_comment(self):
        """Verify setting comment=True places '*' at offset 0."""
        line = build_transaction_line("UPDATE", "00001A", comment=True)
        self.assertTrue(line.startswith("*"))

    def test_parse_report_extracts_processed_transactions(self):
        """Verify report parser extracts processed transaction summary strings."""
        res = RunResult(
            returncode=0,
            stdout="",
            stderr="",
            custout_contents="",
            report_contents=(
                "HEADER LINE\n"
                "Transaction processed:  UPDATE 00001A        REPLACE  NAME       01 IBM-RTP\n"
                "FOOTER LINE"
            ),
        )
        _parse_report(res)
        self.assertEqual(
            res.transactions_processed,
            ["UPDATE 00001A        REPLACE  NAME       01 IBM-RTP"],
        )

    @patch("harness.CUSTOUT_FILE")
    def test_get_customer_record_found(self, mock_file):
        """Verify customer record lookup extracts correct key line."""
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = (
            "00001A  ACME CORP    00100000\n"
            "00002A  WIDGET MAKERS 00050000"
        )
        record = get_customer_record("00002A")
        self.assertEqual(record, "00002A  WIDGET MAKERS 00050000")

    @patch("harness.CUSTOUT_FILE")
    def test_get_customer_record_missing(self, mock_file):
        """Verify missing key returns None."""
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = "00001A  ACME CORP    00100000"
        self.assertIsNone(get_customer_record("99999Z"))


if __name__ == "__main__":
    unittest.main()