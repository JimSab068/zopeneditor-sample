import unittest
from harness import RunResult
from conjecture_validator import (
    Conjecture,
    ExpectedOutcome,
    ObservedOutcome,
    ValidationResult,
)
from functional_doc_generator import generate_functional_doc


class TestFunctionalDocGenerator(unittest.TestCase):

    def setUp(self):
        conj = Conjecture(
            branch_id="BR-001",
            description="Update customer name",
            input_transactions=["UPDATE 00002A        REPLACE  NAME        TEST NAME"],
            expected=ExpectedOutcome(customer_record_contains={"00002A": "TEST NAME"}),
        )
        run_res = RunResult(0, "", "", "", "", [])
        obs = ObservedOutcome(
            returncode=0,
            report_contents="",
            transactions_processed=[],
            customer_records={"00002A": "TEST NAME"},
        )
        self.sample_results = [
            ValidationResult(
                conjecture=conj,
                passed=True,
                claimed=conj.expected,
                observed=obs,
                actual_run=run_res,
            )
        ]

    def test_generate_doc_fallback(self):
        doc = generate_functional_doc(self.sample_results)
        self.assertIn("# Functional Specification Document", doc)
        self.assertIn("BR-001", doc)

    def test_generate_doc_mock_llm(self):
        def mock_llm(sys_prompt: str, user_prompt: str) -> str:
            return "# Mocked Functional Specification\n\n- Rule 1: Name Update Verified"

        doc = generate_functional_doc(self.sample_results, llm_client=mock_llm)
        self.assertIn("Mocked Functional Specification", doc)


if __name__ == "__main__":
    unittest.main()