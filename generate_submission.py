import json
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from store import store
from composer import compose

load_dotenv()

def process_pair(pair):
    test_id = pair["test_id"]
    tid = pair["trigger_id"]
    mid = pair["merchant_id"]
    cid = pair.get("customer_id")

    trigger = store.get_trigger(tid)
    merchant = store.get_merchant(mid)
    category = store.get_category_for_merchant(mid)
    customer = store.get_customer(cid) if cid else None

    if not trigger or not merchant or not category:
        print(f"Warning: missing context for test pair {test_id} (trg={tid}, mer={mid})")
        return None

    composed = compose(category, merchant, trigger, customer)

    return {
        "test_id": test_id,
        "body": composed.body,
        "cta": composed.cta,
        "send_as": composed.send_as,
        "suppression_key": composed.suppression_key,
        "rationale": composed.rationale
    }

def main():
    expanded_dir = Path(__file__).parent / "dataset" / "expanded"
    test_pairs_path = expanded_dir / "test_pairs.json"
    
    if not test_pairs_path.exists():
        print(f"Error: {test_pairs_path} not found. Run generate_dataset.py first.")
        return

    with open(test_pairs_path) as f:
        test_pairs = json.load(f).get("pairs", [])

    print(f"Loaded {len(test_pairs)} test pairs from {test_pairs_path}")

    # Load and push category contexts
    cat_dir = expanded_dir / "categories"
    for cat_file in cat_dir.glob("*.json"):
        with open(cat_file) as f:
            cat_data = json.load(f)
            slug = cat_data.get("slug", cat_file.stem)
            store.push_context("category", slug, 1, cat_data)

    # Load and push merchant contexts
    mer_dir = expanded_dir / "merchants"
    for mer_file in mer_dir.glob("*.json"):
        with open(mer_file) as f:
            mer_data = json.load(f)
            mid = mer_data["merchant_id"]
            store.push_context("merchant", mid, 1, mer_data)

    # Load and push customer contexts
    cus_dir = expanded_dir / "customers"
    for cus_file in cus_dir.glob("*.json"):
        with open(cus_file) as f:
            cus_data = json.load(f)
            cid = cus_data["customer_id"]
            store.push_context("customer", cid, 1, cus_data)

    # Load and push trigger contexts
    trg_dir = expanded_dir / "triggers"
    for trg_file in trg_dir.glob("*.json"):
        with open(trg_file) as f:
            trg_data = json.load(f)
            tid = trg_data["id"]
            store.push_context("trigger", tid, 1, trg_data)

    print("Generating real OpenAI messages for submission...")
    submission_lines = []
    
    for idx, pair in enumerate(test_pairs, 1):
        res = process_pair(pair)
        if res:
            submission_lines.append(res)
            print(f"[{idx}/{len(test_pairs)}] Processed {pair['test_id']}")

    # Sort by test_id
    submission_lines.sort(key=lambda x: x["test_id"])

    out_file = Path(__file__).parent / "submission.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for line in submission_lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    print(f"Successfully generated {len(submission_lines)} real Gemini records in {out_file}")

if __name__ == "__main__":
    main()
