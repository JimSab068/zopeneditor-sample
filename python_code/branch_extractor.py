"""
branch_extractor.py — targeted parse of a COBOL PROCEDURE DIVISION into
reachable branch paths.

Not a full COBOL grammar. Scoped to this source's actual style: fixed-format
columns, one clause per line, explicit scope terminators (END-IF,
END-EVALUATE) rather than period-scoped nesting. That's a real constraint,
stated here rather than hidden — a program written with implicit
period-scoped nesting instead of explicit terminators would need a
different (harder) parser.
"""
import sys
from dataclasses import dataclass

@dataclass
class Line:
    number: int
    text: str

@dataclass
class PerformNode:
    target: str
    source_line: int
    until_condition: str | None = None

@dataclass
class IfNode:
    condition: str
    source_line: int
    then_branch: list
    else_branch: list

@dataclass
class WhenClause:
    values: list[str]
    source_line: int
    body: list

@dataclass
class EvaluateNode:
    subject: str
    source_line: int
    when_clauses: list[WhenClause]

@dataclass
class CallNode:
    target: str
    source_line: int
    arguments: str

@dataclass
class StatementNode:
    text: str
    source_line: int

# --- 1. COBOL Clean Up ---

def strip_fixed_format(cobol_path: str) -> list[Line]:
    lines = []
    with open(cobol_path, 'r') as f:
        for i, raw_line in enumerate(f, 1):
            if len(raw_line) > 6 and raw_line[6] in ('*', '/'):
                continue
            text = raw_line[6:72].strip() if len(raw_line) >= 72 else raw_line[6:].strip()
            if text:
                lines.append(Line(i, text))
    return lines

import re

PARA_HEADER_RE = re.compile(r'^(\d[0-9A-Za-z-]*)\.$')

def split_procedure_division(lines: list[Line]) -> tuple[dict[str, list[Line]], list[str]]:
    paragraphs = {}
    order = []
    current_para = None
    
    in_procedure = False
    for ln in lines:
        if ln.text.upper().startswith("PROCEDURE DIVISION"):
            in_procedure = True
            continue
        if not in_procedure:
            continue
            
        m = PARA_HEADER_RE.match(ln.text)
        if m:
            current_para = m.group(1)
            paragraphs[current_para] = []
            order.append(current_para)
        elif current_para:
            paragraphs[current_para].append(ln)
            
    return paragraphs, order
# --- 2. AST Parsing ---

def normalized_text(line: Line) -> str:
    text = line.text.strip()
    if text.endswith("."):
        text = text[:-1].rstrip()
    return text

def parse_statements(lines: list[Line]) -> tuple[list, int]:
    nodes = []
    i = 0
    n = len(lines)
    
    while i < n:
        ln = lines[i]
        t = normalized_text(ln)
        tu = t.upper()
        
        if tu == "ELSE" or tu == "END-IF" or tu == "END-EVALUATE" or tu.startswith("WHEN "):
            break

        if tu.startswith("IF "):
            condition = t[3:].strip()
            i += 1
            then_lines = []
            while i < n and normalized_text(lines[i]).upper() not in ("ELSE", "END-IF"):
                then_lines.append(lines[i])
                i += 1
                
            then_branch, _ = parse_statements(then_lines)
            else_branch = []
            
            if i < n and normalized_text(lines[i]).upper() == "ELSE":
                i += 1
                else_lines = []
                while i < n and normalized_text(lines[i]).upper() != "END-IF":
                    else_lines.append(lines[i])
                    i += 1
                else_branch, _ = parse_statements(else_lines)
                
            if i < n and normalized_text(lines[i]).upper() == "END-IF":
                i += 1
                
            nodes.append(IfNode(condition=condition, source_line=ln.number, then_branch=then_branch, else_branch=else_branch))
            continue
            
        elif tu.startswith("EVALUATE "):
            subject = t[9:].strip()
            i += 1
            when_clauses = []
            
            while i < n and normalized_text(lines[i]).upper() != "END-EVALUATE":
                # Handle multiple sequential WHENs
                values = []
                start_line = lines[i].number
                while i < n and normalized_text(lines[i]).upper().startswith("WHEN "):
                    val = normalized_text(lines[i])[5:].strip()
                    values.append(val)
                    i += 1
                    
                body_lines = []
                while i < n and not normalized_text(lines[i]).upper().startswith("WHEN ") and normalized_text(lines[i]).upper() != "END-EVALUATE":
                    body_lines.append(lines[i])
                    i += 1
                    
                if values:
                    body_nodes, _ = parse_statements(body_lines)
                    when_clauses.append(WhenClause(values=values, source_line=start_line, body=body_nodes))
                    
            if i < n and normalized_text(lines[i]).upper() == "END-EVALUATE":
                i += 1
                
            nodes.append(EvaluateNode(subject=subject, source_line=ln.number, when_clauses=when_clauses))
            continue
            
        elif tu.startswith("PERFORM "):
            target_str = t[8:].strip()
            until_cond = None
            
            # Check inline UNTIL
            if " UNTIL " in target_str.upper():
                idx = target_str.upper().find(" UNTIL ")
                until_cond = target_str[idx + 7:].strip()
                target_str = target_str[:idx].strip()
            # Check multiline UNTIL
            elif i + 1 < n and normalized_text(lines[i+1]).upper().startswith("UNTIL "):
                i += 1
                until_cond = normalized_text(lines[i])[6:].strip()
                
            nodes.append(PerformNode(target=target_str, source_line=ln.number, until_condition=until_cond))
            i += 1
            continue
            
        elif tu.startswith("CALL "):
            target = t[5:].split()[0].strip("'\"")
            args = t[t.upper().find("USING"):].strip() if "USING" in tu else ""
            nodes.append(CallNode(target=target, source_line=ln.number, arguments=args))
            i += 1
            continue
            
        else:
            nodes.append(StatementNode(text=t, source_line=ln.number))
            i += 1
            
    return nodes, i

def parse_cobol(cobol_path: str) -> tuple[dict[str, list], list[str]]:
    lines = strip_fixed_format(cobol_path)
    paragraphs_raw, order = split_procedure_division(lines)
    
    ast = {}
    for name, body in paragraphs_raw.items():
        nodes, _ = parse_statements(body)
        ast[name] = nodes
        
    return ast, order

# --- 3. Branch Enumeration ---

def enumerate_branches(ast: dict[str, list], entry_paragraph: str) -> list[dict]:
    branches = []
    
    def walk(nodes: list, conditions: list[str], path: list[str], visited: set, lines: list[int]):
        if not nodes:
            branches.append({
                "branch_id": f"BR-{len(branches)+1:04d}",
                "conditions": conditions,
                "path": path,
                "source_lines": sorted(list(set(lines))),
                "terminal": "END_OF_PARAGRAPH"
            })
            return
            
        node = nodes[0]
        rest = nodes[1:]
        node_line = getattr(node, "source_line", None)
        cur_lines = lines + ([node_line] if node_line is not None else [])
        
        if isinstance(node, IfNode):
            walk(node.then_branch + rest, conditions + [node.condition], path + [f"IF {node.condition}"], visited, cur_lines)
            walk(node.else_branch + rest, conditions + [f"NOT ({node.condition})"], path + [f"ELSE ({node.condition})"], visited, cur_lines)
            
        elif isinstance(node, EvaluateNode):
            for clause in node.when_clauses:
                cond_str = f"{node.subject} = " + " OR ".join(clause.values)
                clause_lines = cur_lines + ([clause.source_line] if hasattr(clause, "source_line") else [])
                walk(clause.body + rest, conditions + [cond_str], path + [f"WHEN {cond_str}"], visited, clause_lines)
                
        elif isinstance(node, PerformNode):
            step_desc = f"PERFORM {node.target}" + (f" UNTIL {node.until_condition}" if node.until_condition else "")
            if node.target in ast and node.target not in visited:
                walk(ast[node.target] + rest, conditions, path + [step_desc], visited | {node.target}, cur_lines)
            else:
                walk(rest, conditions, path + [step_desc], visited, cur_lines)
                
        elif isinstance(node, CallNode):
            branches.append({
                "branch_id": f"BR-{len(branches)+1:04d}",
                "conditions": conditions,
                "path": path + [f"CALL {node.target}"],
                "source_lines": sorted(list(set(cur_lines))),
                "terminal": f"CALL {node.target}"
            })
            
        elif isinstance(node, StatementNode):
            walk(rest, conditions, path + [node.text], visited, cur_lines)

    if entry_paragraph in ast:
        walk(ast[entry_paragraph], [], [entry_paragraph], {entry_paragraph}, [])
        
    return branches


if __name__ == "__main__":
    import json
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "COBOL/SAM1.cbl"
    
    try:
        ast, order = parse_cobol(path)
        print(f"Successfully parsed {len(order)} paragraphs.")
    except Exception as e:
        print(f"Failed to parse AST: {e}")
        sys.exit(1)

    # Automatically default to the first paragraph in the file if none is provided
    entry = sys.argv[2] if len(sys.argv) > 2 else order[0]

    if entry in ast:
        print(f"Nodes in {entry}: {len(ast[entry])}")
        branches = enumerate_branches(ast, entry)
        print(f"\nFound {len(branches)} branches from entry '{entry}':\n")
        for b in branches:
            print(json.dumps(b, indent=2))
    else:
        print(f"Entry paragraph '{entry}' not found in AST.")