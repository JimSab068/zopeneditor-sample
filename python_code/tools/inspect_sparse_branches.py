from python_code.branch_extractor import parse_cobol, enumerate_branches

ast, order = parse_cobol("COBOL/SAM1.cbl")
branches = enumerate_branches(ast, "100-PROCESS-TRANSACTIONS")

WANTED = {
    "BR-0090", "BR-0112", "BR-0114", "BR-0274", "BR-0276",
    "BR-0278", "BR-0474", "BR-0638", "BR-0640",
}

for b in branches:
    if b["branch_id"] in WANTED:
        print(f"{b['branch_id']}")
        print(f"  path ({len(b['path'])} steps): {b['path']}")
        print(f"  conditions ({len(b['conditions'])}): {b['conditions']}")
        print(f"  source_lines: {b['source_lines']}")
        print()