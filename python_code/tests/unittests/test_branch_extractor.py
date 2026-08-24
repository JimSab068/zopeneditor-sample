import unittest
from branch_extractor import (
    Line, 
    split_procedure_division, 
    parse_statements, 
    enumerate_branches,
    StatementNode, 
    IfNode, 
    PerformNode, 
    EvaluateNode
)

class TestBranchExtractor(unittest.TestCase):

    def test_split_procedure_division(self):
        lines = [
            Line(1, "PROCEDURE DIVISION."),
            Line(2, "000-MAIN."),
            Line(3, "    MOVE 'Y' TO FLAG."),
            Line(4, "    PERFORM 100-SUB."),
            Line(5, "100-SUB."),
            Line(6, "    DISPLAY 'HELLO'.")
        ]
        paras, order = split_procedure_division(lines)
        self.assertEqual(order, ["000-MAIN", "100-SUB"])
        self.assertEqual(len(paras["000-MAIN"]), 2)
        self.assertEqual(len(paras["100-SUB"]), 1)

    def test_parse_if_statement(self):
        lines = [
            Line(1, "IF A = B"),
            Line(2, "    MOVE 1 TO X"),
            Line(3, "ELSE"),
            Line(4, "    MOVE 2 TO X"),
            Line(5, "END-IF.")
        ]
        ast, _ = parse_statements(lines)
        self.assertEqual(len(ast), 1)
        self.assertIsInstance(ast[0], IfNode)
        self.assertEqual(ast[0].condition, "A = B")
        self.assertEqual(len(ast[0].then_branch), 1)
        self.assertEqual(len(ast[0].else_branch), 1)
        self.assertIsInstance(ast[0].then_branch[0], StatementNode)

    def test_parse_nested_if(self):
        lines = [
            Line(1, "IF A = B"),
            Line(2, "    IF C = D"),
            Line(3, "        MOVE 1 TO X"),
            Line(4, "    END-IF"),
            Line(5, "END-IF.")
        ]
        ast, _ = parse_statements(lines)
        self.assertEqual(len(ast), 1)
        self.assertIsInstance(ast[0].then_branch[0], IfNode)
        self.assertEqual(ast[0].then_branch[0].condition, "C = D")

    def test_parse_perform_until(self):
        lines = [Line(1, "PERFORM 700-READ UNTIL EOF = 'Y'.")]
        ast, _ = parse_statements(lines)
        self.assertIsInstance(ast[0], PerformNode)
        self.assertEqual(ast[0].target, "700-READ")
        self.assertEqual(ast[0].until_condition, "EOF = 'Y'")

    def test_parse_evaluate_grouping(self):
        lines = [
            Line(1, "EVALUATE STATUS"),
            Line(2, "WHEN '00'"),
            Line(3, "WHEN '04'"),
            Line(4, "    MOVE 'Y' TO OK"),
            Line(5, "WHEN OTHER"),
            Line(6, "    MOVE 'N' TO OK"),
            Line(7, "END-EVALUATE.")
        ]
        ast, _ = parse_statements(lines)
        self.assertEqual(len(ast), 1)
        self.assertIsInstance(ast[0], EvaluateNode)
        self.assertEqual(ast[0].subject, "STATUS")
        self.assertEqual(len(ast[0].when_clauses), 2)
        self.assertEqual(ast[0].when_clauses[0].values, ["'00'", "'04'"])
        self.assertEqual(ast[0].when_clauses[1].values, ["OTHER"])

    def test_enumerate_branches_simple_if(self):
        lines = [
            Line(1, "IF A = B"),
            Line(2, "    MOVE 1 TO X"),
            Line(3, "ELSE"),
            Line(4, "    MOVE 2 TO X"),
            Line(5, "END-IF.")
        ]
        parsed_nodes, _ = parse_statements(lines)
        ast = {"000-MAIN": parsed_nodes}
        
        branches = enumerate_branches(ast, "000-MAIN")
        self.assertEqual(len(branches), 2)
        
        self.assertIn("A = B", branches[0]["conditions"])
        self.assertIn("MOVE 1 TO X", branches[0]["path"])
        
        self.assertIn("NOT (A = B)", branches[1]["conditions"])
        self.assertIn("MOVE 2 TO X", branches[1]["path"])

    def test_enumerate_branches_cross_paragraph(self):
        main_lines = [
            Line(1, "PERFORM 100-SUB"),
            Line(2, "MOVE 'Y' TO DONE")
        ]
        sub_lines = [
            Line(3, "DISPLAY 'HELLO'")
        ]
        main_nodes, _ = parse_statements(main_lines)
        sub_nodes, _ = parse_statements(sub_lines)
        
        ast = {
            "000-MAIN": main_nodes,
            "100-SUB": sub_nodes
        }
        
        branches = enumerate_branches(ast, "000-MAIN")
        self.assertEqual(len(branches), 1)
        
        path = branches[0]["path"]
        self.assertIn("PERFORM 100-SUB", path)
        self.assertIn("DISPLAY 'HELLO'", path)
        self.assertIn("MOVE 'Y' TO DONE", path)

if __name__ == '__main__':
    unittest.main()