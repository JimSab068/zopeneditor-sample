"""
harness.py — mechanical execution layer for the SAM1 conjecture-validation loop.

This module wraps the compiled SAM1 binary so an agent (or a test script) can:
  1. write a transaction file targeting a specific branch,
  2. run SAM1 against it,
  3. read back the resulting customer file + report,
  4. hand structured, parsed evidence to a validator.

Nothing here is LLM-generated or LLM-assessed — this is the ground-truth
oracle the conjecture agent's claims get checked against.
"""

import subprocess
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SAM1_BINARY = REPO_ROOT / "SAM1"
BASELINE_CUSTFILE = REPO_ROOT / "custfile.txt"     # never modified by SAM1 itself (input-only)
TRAN_FILE = REPO_ROOT / "tranfile.txt"             # rewritten per test case
CUSTOUT_FILE = REPO_ROOT / "custout.txt"           # overwritten fresh on every run
REPORT_FILE = REPO_ROOT / "custrpt.txt"            # overwritten fresh on every run


@dataclass
class RunResult:
    """Everything observed from one SAM1 execution — the mechanical evidence."""
    returncode: int
    stdout: str
    stderr: str
    custout_contents: str
    report_contents: str
    # Parsed per-transaction outcomes, pulled from the report's
    # "Transaction processed: ..." lines and the stats table at the bottom.
    transactions_processed: list = field(default_factory=list)
    transactions_in_error: int = 0


def write_transaction_file(transaction_lines: list[str]) -> None:
    """
    Write one or more pre-built, fixed-width transaction record lines to
    tranfile.txt. Each line must already be built to TRANREC.cpy's exact
    column layout — this function does no formatting, just writes what
    it's given.
    """
    TRAN_FILE.write_text("\n".join(transaction_lines) + "\n")


def run_sam1() -> RunResult:
    """
    Execute the compiled SAM1 binary against the current tranfile.txt and
    the fixed custfile.txt baseline, then read back both output files.
    Each call is a fresh subprocess — SAM1's working-storage (including
    WS-PREV-TRAN-KEY, used for the out-of-sequence check) resets every
    time, so test cases are naturally isolated from each other without
    needing to reset any state by hand.
    """
    env = os.environ.copy()
    env["COB_LIBRARY_PATH"] = str(REPO_ROOT)  # so the SAM2 module resolves

    proc = subprocess.run(
        [str(SAM1_BINARY)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    custout = CUSTOUT_FILE.read_text() if CUSTOUT_FILE.exists() else ""
    report = REPORT_FILE.read_text() if REPORT_FILE.exists() else ""

    result = RunResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        custout_contents=custout,
        report_contents=report,
    )
    _parse_report(result)
    return result


def _parse_report(result: RunResult) -> None:
    """
    Extract structured evidence from custrpt.txt's human-readable output.
    The report already gives us per-transaction lines like:
        "Transaction processed:  UPDATE 00001A        REPLACE  NAME       01 IBM-RTP"
    and a stats table with Processed/In Error counts per transaction type.
    This is close to free evidence for the validator/ledger — worth
    parsing structurally rather than re-deriving everything from a raw
    file diff.
    """
    for line in result.report_contents.splitlines():
        stripped = line.strip()
        if stripped.startswith("Transaction processed:"):
            result.transactions_processed.append(
                stripped.removeprefix("Transaction processed:").strip()
            )
    # TODO once we confirm exact report column layout: parse the
    # "Transaction Totals" table at the bottom for per-type
    # Processed / In Error counts, rather than just counting processed
    # lines above. Low priority — the processed-lines list is enough
    # to start validating individual conjectures against.


def get_customer_record(key: str) -> str | None:
    """
    Look up a single customer record from custout.txt by its key
    (e.g. "00001A"). Returns the raw line, or None if not found —
    useful for the validator to check "was this record actually
    changed/removed/added as claimed."
    """
    if not CUSTOUT_FILE.exists():
        return None
    for line in CUSTOUT_FILE.read_text().splitlines():
        if line.startswith(key):
            return line
    return None


# TRANREC.cpy fixed-width layout (0-indexed byte offsets), 80 bytes total —
# cross-checked against RPT-TRAN-RECORD PIC X(80) in SAM1's report section,
# which matches exactly:
#   TRAN-CODE            [0:6]    also TRAN-COMMENT = char[0] (redefine)
#   FILLER                [6:7]
#   TRAN-KEY              [7:13]
#   FILLER                [13:21]
#   TRAN-ACTION           [21:29]
#   FILLER                [29:30]
#   TRAN-FIELD-NAME       [30:40]
#   FILLER                [40:41]
#   TRAN-FIELD-SS         [41:43]
#   FILLER                [43:44]
#   TRAN-UPDATE-DATA      [44:80]  (36 chars)
#     -> NAME field: raw text, left-justified, space-padded, full 36 chars
#     -> BALANCE/ORDERS: sign[44] + 6 integer digits[45:51] + 2 cent digits[51:53],
#        remaining [53:80] unused. Per SAM2's 100-VALIDATE-TRAN: a '-'/'+' at
#        offset 44 gets replaced with '0' before the whole 9(7)V99 field is
#        read as an unsigned magnitude — so a *signed* value effectively caps
#        at 6 integer digits, not 7. We always write an explicit sign to stay
#        consistent with that path rather than relying on the unsigned case.
RECORD_LENGTH = 80


def build_transaction_line(
    tran_code: str,
    tran_key: str,
    tran_action: str = "",
    tran_field_name: str = "",
    tran_field_ss: str = "00",
    name_value: str = "",
    numeric_value: str | None = None,  # e.g. "150.00" or "-25.50"
    comment: bool = False,
) -> str:
    """
    Build one fixed-width, 80-byte TRANREC.cpy-compatible transaction line.

    tran_code: 'UPDATE', 'ADD', or 'DELETE' (auto-padded to 6 chars)
    tran_key: the 6-char customer key, e.g. "00001A"
    tran_action: 'REPLACE' or 'ADD' (UPDATE only; auto-padded to 8 chars)
    tran_field_name: 'NAME', 'BALANCE', or 'ORDERS' (auto-padded to 10 chars)
    name_value: text to write when tran_field_name == 'NAME'
    numeric_value: decimal string when tran_field_name in ('BALANCE', 'ORDERS')
    comment: if True, marks the line as a comment (SAM1 skips it, per
             TRAN-COMMENT = '*' check) — useful for building adversarial/
             edge-case test files without a real transaction firing
    """
    rec = [" "] * RECORD_LENGTH

    def put(offset: int, value: str, width: int) -> None:
        value = value[:width].ljust(width)
        for i, ch in enumerate(value):
            rec[offset + i] = ch

    put(0, "*" if comment else tran_code.upper(), 6)
    put(7, tran_key.upper(), 6)
    put(21, tran_action.upper(), 8)
    put(30, tran_field_name.upper(), 10)
    put(41, tran_field_ss, 2)

    field = tran_field_name.strip().upper()
    if field == "NAME":
        put(44, name_value, 36)
    elif field in ("BALANCE", "ORDERS") and numeric_value is not None:
        negative = numeric_value.strip().startswith("-")
        clean = numeric_value.strip().lstrip("+-")
        integer_part, _, decimal_part = clean.partition(".")
        integer_part = integer_part.zfill(6)[-6:]       # 6 digits, per the sign-slot cap above
        decimal_part = (decimal_part or "00").ljust(2, "0")[:2]
        put(44, "-" if negative else "+", 1)
        put(45, integer_part, 6)
        put(51, decimal_part, 2)

    return "".join(rec)


if __name__ == "__main__":
    # Smoke test: build a small batch of real transactions covering a few
    # branches from the enumeration in the compatibility checklist, run
    # SAM1 against them, and print what came back. Uses record 00002
    # ("WIDGET MAKERS") since 00001 and 99999 were already touched by the
    # manual test run — keeps this run's evidence independently readable.
    lines = [
        build_transaction_line(
            tran_code="UPDATE", tran_key="00002A",
            tran_action="REPLACE", tran_field_name="NAME",
            name_value="RENAMED CO",
        ),
        build_transaction_line(
            tran_code="UPDATE", tran_key="00002A",
            tran_action="ADD", tran_field_name="BALANCE",
            numeric_value="100.00",
        ),
    ]
    write_transaction_file(lines)
    result = run_sam1()
    print(f"Return code: {result.returncode}")
    print(f"Transactions processed: {result.transactions_processed}")
    print(f"--- custout.txt ---\n{result.custout_contents}")