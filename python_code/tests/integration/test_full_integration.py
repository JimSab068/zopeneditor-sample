import unittest
from harness import SAM1_BINARY
from conjecture_generator import generate_conjecture_for_branch
from conjecture_validator import validate_conjecture


class TestFullPipelineIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not SAM1_BINARY.exists():
            raise unittest.SkipTest(
                "SAM1 binary not found in python_code/. Compile SAM1 and SAM2 first."
            )

    def test_pipeline_name_branch_heuristic(self):
        """Pipeline test: AST branch -> Heuristic Generator -> Validator -> SAM1/SAM2 execution."""
        branch = {
            "conditions": ["TRAN-CODE = 'UPDATE'", "TRAN-FIELD-NAME = 'NAME'"],
            "path": ["000-MAIN", "200-PROCESS-TRAN", "IF TRAN-FIELD-NAME = 'NAME'"]
        }

        conj = generate_conjecture_for_branch(branch)
        result = validate_conjecture(conj)

        self.assertTrue(
            result.passed, 
            f"Pipeline validation failed for NAME branch: {result.reason}"
        )

    def test_pipeline_balance_branch_heuristic(self):
        """Pipeline test: AST branch for BALANCE -> Heuristic Generator -> Validator -> SAM1/SAM2 execution."""
        branch = {
            "conditions": ["TRAN-CODE = 'UPDATE'", "TRAN-FIELD-NAME = 'BALANCE'"],
            "path": ["000-MAIN", "200-PROCESS-TRAN", "WHEN BALANCE"]
        }

        conj = generate_conjecture_for_branch(branch)
        result = validate_conjecture(conj)

        self.assertTrue(
            result.passed, 
            f"Pipeline validation failed for BALANCE branch: {result.reason}"
        )

    def test_pipeline_with_mock_llm(self):
        """Pipeline test: AST branch -> Mock LLM Generator -> Validator -> SAM1/SAM2 execution."""
        mock_response = """
        {
            "tran_code": "UPDATE",
            "tran_key": "00002A",
            "tran_action": "REPLACE",
            "tran_field_name": "NAME",
            "name_value": "INTEGRATION CORP",
            "numeric_value": null,
            "expected_report": "UPDATE 00002A",
            "expected_record_sub": "INTEGRATION CORP"
        }
        """

        def mock_llm_client(sys_prompt: str, user_prompt: str) -> str:
            return mock_response

        branch = {
            "conditions": ["TRAN-CODE = 'UPDATE'"],
            "path": ["000-MAIN", "200-PROCESS-TRAN"]
        }

        conj = generate_conjecture_for_branch(branch, llm_client=mock_llm_client)
        result = validate_conjecture(conj)

        self.assertTrue(
            result.passed, 
            f"Mock LLM pipeline validation failed: {result.reason}"
        )


if __name__ == "__main__":
    unittest.main()