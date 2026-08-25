import json
import re
from typing import Callable
from sanity_checker import check_conjecture_sanity
from harness import build_transaction_line
from conjecture_validator import Conjecture, ExpectedOutcome


SYSTEM_PROMPT = """You are a COBOL reverse-engineering assistant.
Given an AST branch execution path and copybook layout, generate a valid JSON object containing test parameters.

Output JSON format:
{
  "tran_code": "UPDATE",
  "tran_key": "00002A",
  "tran_action": "REPLACE",
  "tran_field_name": "NAME",
  "name_value": "NEW NAME",
  "numeric_value": null,
  "expected_report": "UPDATE 00002A",
  "expected_record_sub": "NEW NAME"
}

Rules:
- Return JSON only.
- tran_code must be one of UPDATE, ADD, DELETE.
- tran_key must be a 6-character customer key.
- For UPDATE, tran_action must normally be REPLACE or ADD.
- tran_field_name must be one of NAME, BALANCE, ORDERS.
- If tran_field_name is NAME, provide name_value.
- If tran_field_name is BALANCE or ORDERS, provide numeric_value.
- Never return null for tran_field_name.
- Never return null for tran_code or tran_key.
"""


# Known-existing keys in the shipped sample custfile.txt.
# 00003A was deleted during the manual verification run earlier —
# do not reuse it as an existing-key fixture.
EXISTING_KEY = "00002A"
NONEXISTENT_KEY = "00077A"


VALID_TRAN_CODES = {"UPDATE", "ADD", "DELETE"}
VALID_TRAN_ACTIONS = {"REPLACE", "ADD"}
VALID_TRAN_FIELDS = {"NAME", "BALANCE", "ORDERS"}


def build_prompt_for_branch(branch: dict) -> str:
    path_str = " -> ".join(branch.get("path", []))
    cond_str = " AND ".join(branch.get("conditions", []))
    return f"Execution Path: {path_str}\nConditions: {cond_str}"


def _branch_paragraph_names(branch: dict) -> set[str]:
    """
    Pull out paragraph-name tokens from the branch path.

    Paragraph names are used for structural classification instead of
    fragile substring matching against arbitrary condition text.
    """
    names = set()

    for step in branch.get("path", []):
        for token in step.replace("PERFORM", "").split():
            token = token.strip()

            if re.match(r"^\d[0-9A-Za-z-]*$", token):
                names.add(token)

    return names


def _condition_polarity(branch: dict, needle: str) -> bool | None:
    """
    Returns:
        True  -> needle appears as a positive condition
        False -> needle appears inside NOT (...)
        None  -> needle is absent
    """
    for cond in branch.get("conditions", []):
        if needle in cond:
            return not cond.strip().upper().startswith("NOT (")

    return None


def _path_contains(branch: dict, text: str) -> bool:
    """Case-insensitive search through the branch path."""
    needle = text.upper()

    return any(
        needle in step.upper()
        for step in branch.get("path", [])
    )


def _conditions_contain(branch: dict, text: str) -> bool:
    """Case-insensitive search through branch conditions."""
    needle = text.upper()

    return any(
        needle in condition.upper()
        for condition in branch.get("conditions", [])
    )


def _is_update_branch(branch: dict, paras: set[str]) -> bool:
    """
    Determine whether a branch represents UPDATE processing.

    The sample tests use both:
        200-PROCESS-UPDATE-TRAN
    and:
        200-PROCESS-TRAN

    Support both forms.
    """
    if "200-PROCESS-UPDATE-TRAN" in paras:
        return True

    if "200-PROCESS-TRAN" in paras:
        return True

    if any(
        name.startswith("200-PROCESS-UPDATE")
        for name in paras
    ):
        return True

    return (
        _path_contains(branch, "UPDATE")
        and (
            _path_contains(branch, "PROCESS")
            or _conditions_contain(branch, "UPDATE")
        )
    )


def _is_add_branch(branch: dict, paras: set[str]) -> bool:
        """Determine whether a branch represents ADD processing."""
        if "210-PROCESS-ADD-TRAN" in paras:
            return True

        if any(name.startswith("210-PROCESS-ADD") for name in paras):
            return True

        return (
            _conditions_contain(branch, "TRAN-CODE = 'ADD'")
            or _path_contains(branch, "PROCESS-ADD")
        )


def _is_delete_branch(branch: dict, paras: set[str]) -> bool:
    """Determine whether a branch represents DELETE processing."""
    if "220-PROCESS-DELETE-TRAN" in paras:
        return True

    if any(name.startswith("220-PROCESS-DELETE") for name in paras):
        return True

    return (
        _path_contains(branch, "DELETE")
        and _path_contains(branch, "PROCESS")
    )


def _field_from_branch(branch: dict) -> str | None:
    """
    Infer the transaction field from the branch.

    This is intentionally conservative. It only recognizes the three
    fields understood by SAM1's transaction record.
    """
    text_parts = [
        *branch.get("path", []),
        *branch.get("conditions", []),
    ]

    text = " ".join(text_parts).upper()

    # Prefer the more specific field names first.
    if "TRAN-FIELD-NAME = 'BALANCE'" in text:
        return "BALANCE"

    if 'TRAN-FIELD-NAME = "BALANCE"' in text:
        return "BALANCE"

    if "TRAN-FIELD-NAME = 'ORDERS'" in text:
        return "ORDERS"

    if 'TRAN-FIELD-NAME = "ORDERS"' in text:
        return "ORDERS"

    if "TRAN-FIELD-NAME = 'NAME'" in text:
        return "NAME"

    if 'TRAN-FIELD-NAME = "NAME"' in text:
        return "NAME"

    # Also support compact branch paths such as:
    # ["200-PROCESS-TRAN", "WHEN BALANCE"]
    for field in VALID_TRAN_FIELDS:
        if re.search(rf"\b{field}\b", text):
            return field

    return None


def _heuristic_generator(branch: dict) -> Conjecture:
    """
    Deterministic, free, no-LLM conjecture generator.

    Classifies branches primarily by paragraph routing:
        200 -> UPDATE
        210 -> ADD
        220 -> DELETE

    It also understands the shorter sample/test paragraph name
    200-PROCESS-TRAN.
    """
    paras = _branch_paragraph_names(branch)
    path_str = " ".join(branch.get("path", []))

    branch_id = (
        branch.get("branch_id")
        or f"BR-{abs(hash(str(branch.get('conditions', [])))) % 100000}"
    )
    source_lines = branch.get("source_lines", [])

    # ------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------
    if _is_update_branch(branch, paras):
        matched = _condition_polarity(
            branch,
            "CUST-KEY NOT = TRAN-KEY OR WS-CUST-FILE-EOF",
        )

        # No matching key.
        if matched is True:
            tx = build_transaction_line(
                tran_code="UPDATE",
                tran_key=NONEXISTENT_KEY,
                tran_action="REPLACE",
                tran_field_name="NAME",
                name_value="SHOULD NOT APPLY",
            )

            return Conjecture(
                branch_id=branch_id,
                source_lines=source_lines,
                description=(
                    "UPDATE against a non-existent key is rejected "
                    "with no output change."
                ),
                input_transactions=[tx],
                expected=ExpectedOutcome(
                    returncode=0,
                    report_contains=["NO MATCHING KEY"],
                ),
            )

        # Normal/update branch.
        field = _field_from_branch(branch) or "NAME"

        if field == "BALANCE":
            tx = build_transaction_line(
                tran_code="UPDATE",
                tran_key=EXISTING_KEY,
                tran_action="REPLACE",
                tran_field_name="BALANCE",
                numeric_value="100.00",
            )

            expected_sub = "100"

            description = (
                "UPDATE against an existing key replaces the "
                "BALANCE field."
            )

        elif field == "ORDERS":
            tx = build_transaction_line(
                tran_code="UPDATE",
                tran_key=EXISTING_KEY,
                tran_action="REPLACE",
                tran_field_name="ORDERS",
                numeric_value="10.00",
            )

            expected_sub = "10"

            description = (
                "UPDATE against an existing key replaces the "
                "ORDERS field."
            )

        else:
            tx = build_transaction_line(
                tran_code="UPDATE",
                tran_key=EXISTING_KEY,
                tran_action="REPLACE",
                tran_field_name="NAME",
                name_value="HEURISTIC UPDATE",
            )

            expected_sub = "HEURISTIC UPDATE"

            description = (
                "UPDATE against an existing key replaces the "
                "NAME field via SAM2."
            )

        return Conjecture(
            branch_id=branch_id,
            source_lines=source_lines,
            description=description,
            input_transactions=[tx],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=[f"UPDATE {EXISTING_KEY}"],
                customer_record_contains={
                    EXISTING_KEY: expected_sub
                },
            ),
        )

    # ------------------------------------------------------------
    # ADD
    # ------------------------------------------------------------
    if _is_add_branch(branch, paras):
        duplicate = _condition_polarity(
            branch,
            "CUST-KEY = TRAN-KEY",
        )

        if duplicate is True:
            tx = build_transaction_line(
                tran_code="ADD",
                tran_key=EXISTING_KEY,
            )

            return Conjecture(
                branch_id=branch_id,
                source_lines=source_lines,
                description=(
                    "ADD against a key that already exists is "
                    "rejected as a duplicate."
                ),
                input_transactions=[tx],
                expected=ExpectedOutcome(
                    returncode=0,
                    report_contains=["DUPLICATE KEY"],
                ),
            )

        tx = build_transaction_line(
            tran_code="ADD",
            tran_key=NONEXISTENT_KEY,
        )

        return Conjecture(
            branch_id=branch_id,
            source_lines=source_lines,
            description=(
                "ADD against a new key creates a blank record "
                "with zeroed balances."
            ),
            input_transactions=[tx],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=[f"ADD    {NONEXISTENT_KEY}"],
                customer_record_contains={
                    NONEXISTENT_KEY: NONEXISTENT_KEY
                },
            ),
        )

    # ------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------
    if _is_delete_branch(branch, paras):
        matched = _condition_polarity(
            branch,
            "CUST-KEY NOT = TRAN-KEY OR WS-CUST-FILE-EOF",
        )

        if matched is True:
            tx = build_transaction_line(
                tran_code="DELETE",
                tran_key=NONEXISTENT_KEY,
            )

            return Conjecture(
                branch_id=branch_id,
                source_lines=source_lines,
                description=(
                    "DELETE against a non-existent key is rejected "
                    "with no output change."
                ),
                input_transactions=[tx],
                expected=ExpectedOutcome(
                    returncode=0,
                    report_contains=["NO MATCHING KEY"],
                ),
            )

        tx = build_transaction_line(
            tran_code="DELETE",
            tran_key=EXISTING_KEY,
        )

        return Conjecture(
            branch_id=branch_id,
            source_lines=source_lines,
            description=(
                "DELETE against an existing key removes it from "
                "the output file."
            ),
            input_transactions=[tx],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=[f"DELETE {EXISTING_KEY}"],
            ),
        )

    # ------------------------------------------------------------
    # Invalid transaction code
    # ------------------------------------------------------------
    if (
        "TRAN-CODE = OTHER" in path_str.upper()
        or "INVALID TRAN CODE" in path_str.upper()
    ):
        tx = build_transaction_line(
            tran_code="XXXXXX",
            tran_key=EXISTING_KEY,
        )

        return Conjecture(
            branch_id=branch_id,
            source_lines=source_lines,
            description=(
                "An unrecognized transaction code is rejected "
                "and logged as invalid."
            ),
            input_transactions=[tx],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=["INVALID TRAN CODE"],
            ),
        )

    # ------------------------------------------------------------
    # Out-of-sequence
    # ------------------------------------------------------------
    if "TRANSACTION OUT OF SEQUENCE" in path_str.upper():
        tx1 = build_transaction_line(
            tran_code="DELETE",
            tran_key="00050A",
        )

        tx2 = build_transaction_line(
            tran_code="DELETE",
            tran_key="00001A",
        )

        return Conjecture(
            branch_id=branch_id,
            source_lines=source_lines,
            description=(
                "A transaction with a key lower than the previous "
                "one is rejected as out of sequence."
            ),
            input_transactions=[tx1, tx2],
            expected=ExpectedOutcome(
                returncode=0,
                report_contains=[
                    "TRANSACTION OUT OF SEQUENCE"
                ],
            ),
        )

    # ------------------------------------------------------------
    # Safe fallback
    # ------------------------------------------------------------
    tx = build_transaction_line(
        tran_code="UPDATE",
        tran_key=EXISTING_KEY,
        tran_action="REPLACE",
        tran_field_name="NAME",
        name_value="FALLBACK CASE",
    )

    return Conjecture(
        branch_id=branch_id,
        source_lines=source_lines,
        description=(
            f"Unclassified branch (path starts: "
            f"{path_str[:60]}...) — generic UPDATE exercised "
            f"as a smoke case."
        ),
        input_transactions=[tx],
        expected=ExpectedOutcome(
            returncode=0,
            customer_record_contains={
                EXISTING_KEY: "FALLBACK CASE"
            },
        ),
    )


def _normalize_llm_data(data: dict) -> dict | None:
    """
    Normalize and validate the JSON object returned by Gemini.

    Important:
        dict.get("field", default) does NOT protect against JSON null.

    Example:
        {"tran_field_name": null}

    produces:
        data.get("tran_field_name", "NAME") == None

    This function explicitly handles both missing and null values.
    Invalid LLM output returns None so the caller can use the
    deterministic heuristic generator instead.
    """
    if not isinstance(data, dict):
        return None

    tran_code = data.get("tran_code") or "UPDATE"
    tran_key = data.get("tran_key") or EXISTING_KEY
    tran_action = data.get("tran_action") or "REPLACE"
    tran_field_name = data.get("tran_field_name") or "NAME"
    name_value = data.get("name_value") or ""
    numeric_value = data.get("numeric_value")

    # Convert expected string-like values to strings safely.
    if not isinstance(tran_code, str):
        return None

    if not isinstance(tran_key, str):
        return None

    if not isinstance(tran_action, str):
        return None

    if not isinstance(tran_field_name, str):
        return None

    if not isinstance(name_value, str):
        return None

    if numeric_value is not None and not isinstance(
        numeric_value,
        (str, int, float),
    ):
        return None

    tran_code = tran_code.strip().upper()
    tran_key = tran_key.strip().upper()
    tran_action = tran_action.strip().upper()
    tran_field_name = tran_field_name.strip().upper()

    # ------------------------------------------------------------
    # Validate transaction code.
    # ------------------------------------------------------------
    if tran_code not in VALID_TRAN_CODES:
        return None

    # ------------------------------------------------------------
    # Validate customer key.
    #
    # SAM1's transaction layout expects a six-character key.
    # ------------------------------------------------------------
    if len(tran_key) != 6:
        return None

    # Keep the expected key format conservative.
    if not re.fullmatch(r"[0-9A-Z]{6}", tran_key):
        return None

    # ------------------------------------------------------------
    # Validate action.
    # ------------------------------------------------------------
    if tran_action not in VALID_TRAN_ACTIONS:
        return None

    # ------------------------------------------------------------
    # Validate field name.
    # ------------------------------------------------------------
    if tran_field_name not in VALID_TRAN_FIELDS:
        return None

    # ------------------------------------------------------------
    # Field-specific validation.
    # ------------------------------------------------------------
    if tran_field_name == "NAME":
        if not name_value:
            name_value = "LLM GENERATED NAME"

    elif tran_field_name in ("BALANCE", "ORDERS"):
        if numeric_value is None:
            return None

        numeric_value = str(numeric_value).strip()

        if not re.fullmatch(
            r"[+-]?\d+(?:\.\d{1,2})?",
            numeric_value,
        ):
            return None

    return {
        "tran_code": tran_code,
        "tran_key": tran_key,
        "tran_action": tran_action,
        "tran_field_name": tran_field_name,
        "name_value": name_value,
        "numeric_value": numeric_value,
        "expected_report": (
            data.get("expected_report")
            or f"{tran_code} {tran_key}"
        ),
        "expected_record_sub": (
            data.get("expected_record_sub")
            or (
                name_value
                if tran_field_name == "NAME"
                else ""
            )
        ),
    }


def _extract_json_object(response_text: str) -> dict | None:
    """
    Extract the first JSON object from an LLM response.

    Gemini sometimes returns surrounding prose or markdown despite
    being instructed to return JSON only.
    """
    if not response_text or not isinstance(response_text, str):
        return None

    json_match = re.search(
        r"\{.*\}",
        response_text,
        re.DOTALL,
    )

    if not json_match:
        return None

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    return data


# conjecture_generator.py — add near the other classification helpers

def classify_branch_confidence(branch: dict) -> tuple[str, str]:
    paras = _branch_paragraph_names(branch)
    path_str = " ".join(branch.get("path", []))

    if _is_update_branch(branch, paras):
        matched = _condition_polarity(branch, "CUST-KEY NOT = TRAN-KEY OR WS-CUST-FILE-EOF")
        if matched is None:
            return ("UPDATE", "low")           # can't tell if the key matched at all
        if matched is True:
            return ("UPDATE", "high")          # no-matching-key path — field is irrelevant here, heuristic handles it cleanly
        # matched is False -> normal update path, field actually matters
        if _field_from_branch(branch) is None:
            return ("UPDATE", "low")           # genuinely can't tell which field this branch updates
        return ("UPDATE", "high")

    if _is_add_branch(branch, paras):
        duplicate = _condition_polarity(branch, "CUST-KEY = TRAN-KEY")
        return ("ADD", "low" if duplicate is None else "high")

    if _is_delete_branch(branch, paras):
        matched = _condition_polarity(branch, "CUST-KEY NOT = TRAN-KEY OR WS-CUST-FILE-EOF")
        return ("DELETE", "low" if matched is None else "high")

    if "TRAN-CODE = OTHER" in path_str.upper() or "INVALID TRAN CODE" in path_str.upper():
        return ("INVALID_CODE", "high")

    if "TRANSACTION OUT OF SEQUENCE" in path_str.upper():
        return ("OUT_OF_SEQUENCE", "high")

    return ("UNCLASSIFIED", "low")


def generate_conjecture_for_branch(
    branch: dict,
    llm_client: Callable[[str, str], str] | None = None,
) -> Conjecture:
    category, confidence = classify_branch_confidence(branch)
    routing_reason = f"{category}/{confidence}"

    if not llm_client:
        conj = _heuristic_generator(branch)
        conj.generation_source = "heuristic"
        conj.routing_reason = routing_reason
        return conj

    llm_conjecture = _llm_conjecture(branch, llm_client)
    if llm_conjecture is not None:
        llm_conjecture.generation_source = "llm"
        llm_conjecture.routing_reason = routing_reason
        return llm_conjecture

    conj = _heuristic_generator(branch)
    conj.generation_source = "llm_fallback_to_heuristic"  # LLM call happened but validation/sanity rejected it
    conj.routing_reason = routing_reason
    return conj

def _llm_conjecture(
    branch: dict,
    llm_client: Callable[[str, str], str],
) -> Conjecture | None:
    """
    Attempt to create a conjecture using the live LLM.

    Returns None when the LLM response cannot safely be converted
    into a transaction. The caller then falls back to the heuristic
    generator.
    """
    prompt = build_prompt_for_branch(branch)

    try:
        response_text = llm_client(
            SYSTEM_PROMPT,
            prompt,
        )
    except Exception:
        return None

    data = _extract_json_object(response_text)

    if data is None:
        return None

    normalized = _normalize_llm_data(data)

    if normalized is None:
        return None

    tx_line = build_transaction_line(
        tran_code=normalized["tran_code"],
        tran_key=normalized["tran_key"],
        tran_action=normalized["tran_action"],
        tran_field_name=normalized["tran_field_name"],
        name_value=normalized["name_value"],
        numeric_value=normalized["numeric_value"],
    )

    expected_record_sub = normalized["expected_record_sub"]

    customer_record_contains = {}

    if expected_record_sub:
        customer_record_contains[
            normalized["tran_key"]
        ] = expected_record_sub

    branch_id = branch.get("branch_id") or "BR-LLM"
    source_lines = branch.get("source_lines", [])

    conjecture = Conjecture(
        branch_id=branch_id,
        source_lines=source_lines,
        description="LLM generated hypothesis",
        input_transactions=[tx_line],
        expected=ExpectedOutcome(
            returncode=0,
            report_contains=[
                normalized["expected_report"]
            ],
            customer_record_contains=customer_record_contains,
        ),
    )

    is_sane, sanity_reason = check_conjecture_sanity(conjecture)
    if not is_sane:
        return None
    
    return conjecture