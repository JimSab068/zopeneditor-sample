# inspect_conditions.py
from branch_extractor import parse_cobol, enumerate_branches
from conjecture_generator import _is_add_branch, _branch_paragraph_names

ast, order = parse_cobol("COBOL/SAM1.cbl")
branches = enumerate_branches(ast, "100-PROCESS-TRANSACTIONS")

add_branches = [b for b in branches if _is_add_branch(b, _branch_paragraph_names(b))]
print(f"{len(add_branches)} ADD branches total\n")

for b in add_branches[:5]:
    print(b["branch_id"])
    for c in b["conditions"]:
        print(f"    {c!r}")
    print()