import json
from dataclasses import asdict
from conjecture_validator import ValidationResult


def build_ledger(results: list[ValidationResult]) -> dict:
    business_rules = []
    findings = []

    for i, r in enumerate(results, start=1):
        item = {
            "branch_id": r.conjecture.branch_id,
            "source_lines": r.conjecture.source_lines,
            "description": r.conjecture.description,
            "input_transactions": r.conjecture.input_transactions,
            "claimed_outcome": asdict(r.claimed),
            "observed_outcome": asdict(r.observed) if r.observed else None,
        }

        if r.passed:
            item["rule_id"] = f"R-{i:03d}"
            item["status"] = "promoted"
            business_rules.append(item)
        else:
            item["reason"] = r.reason
            item["status"] = "unresolved"
            findings.append(item)

    return {
        "summary": {
            "total_branches_tested": len(results),
            "rules_promoted": len(business_rules),
            "unresolved_findings": len(findings),
        },
        "business_rules": business_rules,
        "findings": findings,
    }


def write_ledger(ledger: dict, json_path: str = "business_rule_ledger.json") -> None:
    with open(json_path, "w") as f:
        json.dump(ledger, f, indent=2)


def render_markdown(ledger: dict) -> str:
    """Renders either a raw or consolidated ledger dictionary into Markdown format."""
    # Support both raw ("business_rules") and consolidated ("consolidated_rules") dictionaries
    rules = ledger.get("business_rules") or ledger.get("consolidated_rules", [])
    
    lines = []
    lines.append("# Business Rule Ledger\n")
    
    # Render summary block
    summary = ledger.get("summary", {})
    lines.append(f"**Total Branches Tested:** {summary.get('total_branches_tested', summary.get('total_branches_consolidated', 0))}")
    lines.append(f"**Rules Promoted:** {summary.get('rules_promoted', 0)}")
    lines.append(f"**Unresolved Findings:** {summary.get('unresolved_findings', 0)}\n")
    lines.append("---\n")
    
    for rule in rules:
        rule_id = rule.get("rule_id") or rule.get("consolidated_rule_id", "N/A")
        description = rule.get("description") or rule.get("macro_description", "No description provided.")
        status = rule.get("status", "UNCONFIRMED")
        
        lines.append(f"### {rule_id}: {description}")
        lines.append(f"**Status:** {status}\n")
        
        if "branches_covered" in rule:
            lines.append(f"**Covered Branches:** {', '.join(rule['branches_covered'])}\n")
        elif "branch_id" in rule:
            lines.append(f"**Branch ID:** {rule['branch_id']}\n")
            
        lines.append("---\n")
        
    return "\n".join(lines)


def write_markdown(ledger: dict, md_path: str = "business_rule_ledger.md") -> None:
    with open(md_path, "w") as f:
        f.write(render_markdown(ledger))