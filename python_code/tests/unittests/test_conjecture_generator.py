import unittest
from conjecture_generator import generate_conjecture_for_branch, build_prompt_for_branch

class TestConjectureGenerator(unittest.TestCase):

    def test_build_prompt_for_branch(self):
        branch = {
            "conditions": ["TRAN-ACTION = 'REPLACE'"],
            "path": ["000-MAIN", "IF TRAN-ACTION = 'REPLACE'"]
        }
        prompt = build_prompt_for_branch(branch)
        self.assertIn("TRAN-ACTION = 'REPLACE'", prompt)

    def test_generate_conjecture_heuristic(self):
        branch = {
            "conditions": ["TRAN-FIELD-NAME = 'BALANCE'"],
            "path": ["200-PROCESS-TRAN", "WHEN BALANCE"]
        }
        conj = generate_conjecture_for_branch(branch)
        self.assertEqual(len(conj.input_transactions), 1)
        self.assertIn("00002A", conj.expected.customer_record_contains)

    def test_generate_conjecture_with_mock_llm(self):
        mock_json = """
        {
            "tran_code": "UPDATE",
            "tran_key": "00002A",
            "tran_action": "REPLACE",
            "tran_field_name": "NAME",
            "name_value": "MOCK CORP",
            "numeric_value": null,
            "expected_report": "UPDATE 00002A",
            "expected_record_sub": "MOCK CORP"
        }
        """
        def mock_llm(sys_prompt: str, user_prompt: str) -> str:
            return mock_json

        branch = {"conditions": [], "path": ["000-MAIN"]}
        conj = generate_conjecture_for_branch(branch, llm_client=mock_llm)
        
        self.assertEqual(conj.branch_id, "BR-LLM")
        self.assertEqual(conj.expected.customer_record_contains["00002A"], "MOCK CORP")

if __name__ == "__main__":
    unittest.main()