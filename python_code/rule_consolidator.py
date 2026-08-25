"""
rule_consolidator.py — Consolidates micro-branch rules into high-level business rules.
"""

def consolidate_rules(promoted_rules: list[dict]) -> list[dict]:
    """
    Groups promoted micro-branch rules by description/intent.
    
    Aggregates covered AST branch IDs and calculates the union 
    of all executed COBOL source lines across merged branches.
    """
    grouped = {}

    for rule in promoted_rules:
        desc = rule.get("description", "Unclassified Rule")
        
        if desc not in grouped:
            grouped[desc] = {
                "consolidated_rule_id": f"CR-{len(grouped) + 1:03d}",
                "description": desc,
                "covered_branch_ids": [],
                "micro_rule_ids": [],
                "aggregated_source_lines": set(),
                "sample_input_transactions": rule.get("input_transactions", []),
                "observed_outcome": rule.get("observed_outcome"),
            }
        
        grouped[desc]["covered_branch_ids"].append(rule.get("branch_id"))
        if rule.get("rule_id"):
            grouped[desc]["micro_rule_ids"].append(rule["rule_id"])
        
        lines = rule.get("source_lines", [])
        grouped[desc]["aggregated_source_lines"].update(lines)

    consolidated = []
    for item in grouped.values():
        item["aggregated_source_lines"] = sorted(list(item["aggregated_source_lines"]))
        item["total_branches_consolidated"] = len(item["covered_branch_ids"])
        consolidated.append(item)

    return consolidated


def build_consolidated_ledger(ledger_data: dict) -> dict:
    """
    Processes a full ledger payload and attaches consolidated rules.
    """
    promoted = ledger_data.get("business_rules", [])
    consolidated = consolidate_rules(promoted)
    
    return {
        "summary": {
            **ledger_data.get("summary", {}),
            "consolidated_rules_count": len(consolidated),
        },
        "consolidated_rules": consolidated,
        "raw_business_rules": promoted,
        "findings": ledger_data.get("findings", []),
    }