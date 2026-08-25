from branch_extractor import parse_cobol, enumerate_branches

ast, order = parse_cobol("COBOL/SAM1.cbl")
branches = enumerate_branches(ast, "100-PROCESS-TRANSACTIONS")

WANTED = {
    "BR-0090", "BR-0112", "BR-0114", "BR-0274", "BR-0276",
    "BR-0278", "BR-0474", "BR-0638", "BR-0640",
}

NEEDLE = "CUSTOMER OUTPUT FILE I/O ERROR"

for b in branches:
    if b["branch_id"] in WANTED:
        found_path = any(NEEDLE in step.upper() for step in b["path"])
        found_cond = any(NEEDLE in c.upper() for c in b["conditions"])
        print(f"{b['branch_id']}: in path={found_path}, in conditions={found_cond}")
        if found_path:
            matches = [s for s in b["path"] if NEEDLE in s.upper()]
            print(f"    path text: {matches}")
        if found_cond:
            matches = [c for c in b["conditions"] if NEEDLE in c.upper()]
            print(f"    condition text: {matches}")