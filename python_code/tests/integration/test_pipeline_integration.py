"""
test_pipeline_integration.py — Live integration test for the complete pipeline.
Covering: AST Parsing -> LLM Conjecture Generation -> Binary Harness Validation ->
          Ledger Consolidation -> Functional Doc Generation.
"""

import os
import unittest
from pathlib import Path
from branch_extractor import parse_cobol, enumerate_branches
from conjecture_generator import generate_conjecture_for_branch
from conjecture_validator import validate_conjecture
from ledger_builder import build_ledger
from rule_consolidator import build_consolidated_ledger
from functional_doc_generator import generate_functional_doc
from llm_clients import live_gemini_client, gemini_rate_limiter
from harness import REPO_ROOT


class TestPipelineIntegration(unittest.TestCase):

    @unittest.skipUnless(
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
        "GEMINI_API_KEY or GOOGLE_API_KEY environment variable required for live LLM integration test."
    )
    def test_full_pipeline_with_llm(self):
        # Enforce rate limit strictly below 5 RPM (4.0 RPM = 15 seconds per request)
        gemini_rate_limiter.interval = 60.0 / 4.0

        # Dynamic COBOL path resolution regardless of working directory
        cobol_path = REPO_ROOT / "COBOL" / "SAM1.cbl"
        if not cobol_path.exists():
            cobol_path = REPO_ROOT.parent / "COBOL" / "SAM1.cbl"

        # Step 1: Parse COBOL source AST
        ast, order = parse_cobol(str(cobol_path))
        self.assertIn("100-PROCESS-TRANSACTIONS", ast)

        # Step 2: Extract reachable branches
        branches = enumerate_branches(ast, "100-PROCESS-TRANSACTIONS")
        self.assertGreater(len(branches), 0)

        # Restrict to 2 branches to minimize API quota usage
        sample_branches = branches[:2]
        validation_results = []

        # Step 3: LLM Conjecture Generation & Binary Harness Validation
        for branch in sample_branches:
            conjecture = generate_conjecture_for_branch(
                branch, 
                llm_client=live_gemini_client
            )
            self.assertIsNotNone(conjecture)
            self.assertGreater(len(conjecture.input_transactions), 0)

            result = validate_conjecture(conjecture)
            self.assertIsNotNone(result)
            validation_results.append(result)

        self.assertEqual(len(validation_results), 2)

        # Step 4: Build Ledger & Consolidate Business Rules
        raw_ledger = build_ledger(validation_results)
        self.assertEqual(raw_ledger["summary"]["total_branches_tested"], 2)

        consolidated_ledger = build_consolidated_ledger(raw_ledger)
        self.assertIn("consolidated_rules", consolidated_ledger)
        self.assertIn("summary", consolidated_ledger)

        # Step 5: Generate Functional Specification via LLM
        doc = generate_functional_doc(
            validation_results, 
            llm_client=live_gemini_client
        )
        self.assertIsInstance(doc, str)
        self.assertIn("# Functional Specification Document", doc)


if __name__ == "__main__":
    unittest.main()