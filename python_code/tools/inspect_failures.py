import json

WANTED = {
    "BR-0090", "BR-0112", "BR-0114", "BR-0274", "BR-0276",
    "BR-0278", "BR-0474", "BR-0638", "BR-0640",
}

with open("pipeline_checkpoint.jsonl") as f:
    for line in f:
        rec = json.loads(line)
        if rec["branch_id"] in WANTED:
            print(f"{rec['branch_id']} [{rec['generation_source']}, {rec['routing_reason']}]")
            print(f"  description: {rec['description']}")
            print(f"  input_transactions: {rec['input_transactions']}")
            print(f"  claimed: {rec['claimed']}")
            print(f"  reason: {rec['reason']}")
            print()