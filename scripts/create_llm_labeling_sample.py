"""Create a larger labeling sample for LLM-based labeling.

Includes all unique responses NOT already in labeling_sample.csv,
to be labeled by an LLM using human-labeled samples as few-shot examples.
"""

import csv
import hashlib
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

GOLD_FILES = [
    ("SUV Cars", DATA_DIR / "suv_cars_gold.csv"),
    ("Hiking Shoes", DATA_DIR / "hiking_shoes_gold.csv"),
    ("Diapers", DATA_DIR / "diapers_gold.csv"),
]

HUMAN_SAMPLE = DATA_DIR / "labeling_sample.csv"


def response_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def load_human_sample_hashes() -> set[str]:
    """Load response hashes from the human labeling sample to exclude."""
    hashes = set()
    with open(HUMAN_SAMPLE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hashes.add(response_hash(row["response_en_full"]))
    return hashes


def main():
    exclude = load_human_sample_hashes()
    print(f"Excluding {len(exclude)} responses from human sample")

    all_responses: list[dict] = []
    seen: set[str] = set()

    for vertical, path in GOLD_FILES:
        if not path.exists():
            print(f"WARNING: {path} not found, skipping", file=sys.stderr)
            continue

        count = 0
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                resp = row["response_en_full"]
                h = response_hash(resp)

                if h in exclude or h in seen:
                    continue
                seen.add(h)

                all_responses.append({
                    "vertical": vertical,
                    "model": row["model"],
                    "response_en_full": resp,
                    "extracted_brands": row["extracted_brands"],
                    "extracted_products": row["extracted_products"],
                    "gold_pairs": "",
                    "notes": "",
                })
                count += 1

        print(f"{vertical}: {count} responses (after excluding human sample)")

    all_responses.sort(key=lambda x: (x["vertical"], x["model"]))

    output_path = DATA_DIR / "llm_labeling_sample.csv"
    fieldnames = [
        "vertical",
        "model",
        "response_en_full",
        "extracted_brands",
        "extracted_products",
        "gold_pairs",
        "notes",
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_responses:
            writer.writerow(row)

    print(f"\nWrote {len(all_responses)} responses to {output_path}")


if __name__ == "__main__":
    main()
