# complexity_router.py — now just imports the classifier, no duplication
from conjecture_generator import classify_branch_confidence

def route_branches(branches: list[dict], llm_budget: int) -> tuple[list[dict], list[dict]]:
    low, high = [], []
    for b in branches:
        _, confidence = classify_branch_confidence(b)
        (low if confidence == "low" else high).append(b)
    llm_branches = low[:llm_budget]
    heuristic_branches = low[llm_budget:] + high
    return llm_branches, heuristic_branches