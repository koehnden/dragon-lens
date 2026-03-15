"""Create a stratified labeling sample from gold CSV files.

Samples ~80 unique responses (by response_en_full), equally distributed
across verticals and LLM models, for human labeling of brand/product pairs.
"""

import csv
import hashlib
import random
import sys
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

GOLD_FILES = [
    ("SUV Cars", DATA_DIR / "suv_cars_gold.csv"),
    ("Hiking Shoes", DATA_DIR / "hiking_shoes_gold.csv"),
    ("Diapers", DATA_DIR / "diapers_gold.csv"),
]

RESPONSES_PER_MODEL = 5
SEED = 42


def response_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def load_responses(vertical: str, path: Path) -> dict[str, dict]:
    """Load unique responses grouped by model.

    Returns {model: {resp_hash: {vertical, model, response_en_full,
    extracted_brands, extracted_products}}}
    """
    model_responses: dict[str, dict[str, dict]] = defaultdict(dict)

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row["model"]
            resp = row["response_en_full"]
            h = response_hash(resp)

            if h not in model_responses[model]:
                model_responses[model][h] = {
                    "vertical": vertical,
                    "model": model,
                    "response_en_full": resp,
                    "extracted_brands": row["extracted_brands"],
                    "extracted_products": row["extracted_products"],
                }

    return model_responses


def sample_responses(
    model_responses: dict[str, dict[str, dict]],
    per_model: int,
) -> list[dict]:
    """Sample `per_model` responses from each model."""
    rng = random.Random(SEED)
    sampled = []

    for model in sorted(model_responses):
        hashes = sorted(model_responses[model].keys())
        chosen = rng.sample(hashes, min(per_model, len(hashes)))
        for h in chosen:
            sampled.append(model_responses[model][h])

    return sampled


def main():
    all_samples: list[dict] = []

    for vertical, path in GOLD_FILES:
        if not path.exists():
            print(f"WARNING: {path} not found, skipping", file=sys.stderr)
            continue

        model_responses = load_responses(vertical, path)
        samples = sample_responses(model_responses, RESPONSES_PER_MODEL)
        all_samples.extend(samples)

        models_str = ", ".join(
            f"{m}({len(r)})" for m, r in sorted(model_responses.items())
        )
        print(f"{vertical}: {len(samples)} responses sampled from {models_str}")

    # Sort by vertical then model for organized labeling
    all_samples.sort(key=lambda x: (x["vertical"], x["model"]))

    output_path = DATA_DIR / "labeling_sample.csv"
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
        for row in all_samples:
            row.setdefault("gold_pairs", "")
            row.setdefault("notes", "")
            writer.writerow(row)

    print(f"\nWrote {len(all_samples)} responses to {output_path}")


if __name__ == "__main__":
    main()
