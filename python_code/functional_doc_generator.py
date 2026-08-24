import json
import re
from typing import Callable
from conjecture_validator import ValidationResult

DOC_SYSTEM_PROMPT = """You are an expert technical writer and legacy mainframe system analyst.
Given a list of verified COBOL execution branches and their validated runtime results, produce a clear, professional Functional Specification Document in Markdown.

Include:
1. Executive Summary
2. Core Business Rules (translated from technical field updates to business domain logic)
3. Transaction Field Specification Table
4. Branch Coverage & Verification Status
"""


def generate_functional_doc(
    results: list[ValidationResult],
    llm_client: Callable[[str, str], str] | None = None
) -> str:
    """Consolidates verified conjecture results and generates a Markdown functional doc."""
    passed_results = [r for r in results if r.passed]
    
    summary_data = []
    for r in passed_results:
        summary_data.append({
            "branch_id": r.conjecture.branch_id,
            "description": r.conjecture.description,
            "input_transaction": r.conjecture.input_transactions[0] if r.conjecture.input_transactions else "",
            "expected_record": r.conjecture.expected.customer_record_contains
        })

    user_prompt = f"Verified Execution Evidence ({len(passed_results)} branches passed):\n" + json.dumps(summary_data, indent=2)

    if not llm_client:
        # Fallback offline document template
        doc = "# Functional Specification Document: SAM1 / SAM2\n\n"
        doc += "## Verified Business Rules\n\n"
        for item in summary_data:
            doc += f"- **Branch {item['branch_id']}**: {item['description']}\n"
            doc += f"  - *Verified Output*: `{item['expected_record']}`\n"
        return doc

    return llm_client(DOC_SYSTEM_PROMPT, user_prompt)