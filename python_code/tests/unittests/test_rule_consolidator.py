"""
test_rule_consolidator.py — Unit test for rule consolidation.
"""

import unittest
from rule_consolidator import consolidate_rules, build_consolidated_ledger


class TestRuleConsolidator(unittest.TestCase):

    def setUp(self):
        self.sample_promoted_rules = [
            {
                "rule_id": "R-001",
                "branch_id": "BR-0001",
                "source_lines": [266, 268, 276],
                "description": "UPDATE against an existing key replaces NAME",
                "input_transactions": ["UPDATE 00002A REPLACE NAME 00 NEW NAME"],
                "observed_outcome": {"returncode": 0},
            },
            {
                "rule_id": "R-002",
                "branch_id": "BR-0002",
                "source_lines": [266, 270, 280],
                "description": "UPDATE against an existing key replaces NAME",
                "input_transactions": ["UPDATE 00002A REPLACE NAME 00 NEW NAME"],
                "observed_outcome": {"returncode": 0},
            },
            {
                "rule_id": "R-003",
                "branch_id": "BR-0003",
                "source_lines": [300, 305],
                "description": "DELETE removes key from output",
                "input_transactions": ["DELETE 00002A"],
                "observed_outcome": {"returncode": 0},
            },
        ]

    def test_consolidate_duplicate_descriptions(self):
        result = consolidate_rules(self.sample_promoted_rules)

        # 3 micro-rules with 2 unique descriptions should produce 2 consolidated rules
        self.assertEqual(len(result), 2)

        # Verify first consolidated rule
        cr1 = result[0]
        self.assertEqual(cr1["consolidated_rule_id"], "CR-001")
        self.assertEqual(cr1["description"], "UPDATE against an existing key replaces NAME")
        self.assertEqual(cr1["covered_branch_ids"], ["BR-0001", "BR-0002"])
        self.assertEqual(cr1["micro_rule_ids"], ["R-001", "R-002"])
        self.assertEqual(cr1["total_branches_consolidated"], 2)
        # Source lines should be sorted union of [266, 268, 276] and [266, 270, 280]
        self.assertEqual(cr1["aggregated_source_lines"], [266, 268, 270, 276, 280])

        # Verify second consolidated rule
        cr2 = result[1]
        self.assertEqual(cr2["consolidated_rule_id"], "CR-002")
        self.assertEqual(cr2["description"], "DELETE removes key from output")
        self.assertEqual(cr2["covered_branch_ids"], ["BR-0003"])
        self.assertEqual(cr2["total_branches_consolidated"], 1)
        self.assertEqual(cr2["aggregated_source_lines"], [300, 305])

    def test_build_consolidated_ledger(self):
        raw_ledger = {
            "summary": {"total_branches_tested": 3, "rules_promoted": 3, "unresolved_findings": 0},
            "business_rules": self.sample_promoted_rules,
            "findings": [],
        }

        consolidated_ledger = build_consolidated_ledger(raw_ledger)

        self.assertEqual(consolidated_ledger["summary"]["consolidated_rules_count"], 2)
        self.assertIn("consolidated_rules", consolidated_ledger)
        self.assertEqual(len(consolidated_ledger["consolidated_rules"]), 2)


if __name__ == "__main__":
    unittest.main()