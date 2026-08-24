import json
import re
from typing import Callable
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
"""


def build_prompt_for_branch(branch: dict) -> str:
    path_str = " -> ".join(branch.get("path", []))
    cond_str = " AND ".join(branch.get("conditions", []))
    return f"Execution Path: {path_str}\nConditions: {cond_str}"


def _heuristic_generator(branch: dict) -> Conjecture:
    """Fallback generator for offline testing and initial pass before LLM wiring."""
    path_str = " ".join(branch.get("path", []))
    cond_str = " ".join(branch.get("conditions", []))
    
    key = "00002A"
    
    if "BALANCE" in cond_str or "BALANCE" in path_str:
        field = "BALANCE"
        action = "ADD"
        val = "100.00"
        tx_line = build_transaction_line(
            tran_code="UPDATE", tran_key=key, tran_action=action, 
            tran_field_name=field, numeric_value=val
        )
        sub = key
    else:
        field = "NAME"
        action = "REPLACE"
        val = "LLM TEST CORP"
        tx_line = build_transaction_line(
            tran_code="UPDATE", tran_key=key, tran_action=action, 
            tran_field_name=field, name_value=val
        )
        sub = val

    return Conjecture(
        branch_id="BR-AUTO",
        description=f"Generated for path: {path_str[:40]}...",
        input_transactions=[tx_line],
        expected=ExpectedOutcome(
            returncode=0,
            report_contains=[f"UPDATE {key}"],
            customer_record_contains={key: sub}
        )
    )


def generate_conjecture_for_branch(
    branch: dict, 
    llm_client: Callable[[str, str], str] | None = None
) -> Conjecture:
    """
    Generates a Conjecture from an AST branch dict. 
    If llm_client is provided, calls the LLM; otherwise uses heuristic generator.
    """
    if not llm_client:
        return _heuristic_generator(branch)

    prompt = build_prompt_for_branch(branch)
    response_text = llm_client(SYSTEM_PROMPT, prompt)
    
    # Parse JSON block from response
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if not json_match:
        return _heuristic_generator(branch)
        
    data = json.loads(json_match.group(0))
    
    tx_line = build_transaction_line(
        tran_code=data.get("tran_code", "UPDATE"),
        tran_key=data.get("tran_key", "00002A"),
        tran_action=data.get("tran_action", "REPLACE"),
        tran_field_name=data.get("tran_field_name", "NAME"),
        name_value=data.get("name_value", ""),
        numeric_value=data.get("numeric_value")
    )
    
    return Conjecture(
        branch_id="BR-LLM",
        description="LLM generated hypothesis",
        input_transactions=[tx_line],
        expected=ExpectedOutcome(
            returncode=0,
            report_contains=[data.get("expected_report", "UPDATE")],
            customer_record_contains={
                data.get("tran_key", "00002A"): data.get("expected_record_sub", "")
            }
        )
    )