"""Evaluate extraction quality against gold-standard labels.

Compares extracted_brands/extracted_products against gold_pairs
from a labeled CSV. Reports precision, recall, F1 at brand and product level.

Usage:
    python scripts/benchmark_extraction.py [--csv data/gold_pairs_chatgpt.csv] [--verbose]
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CSV = DATA_DIR / "gold_pairs_chatgpt.csv"


@dataclass
class Metrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    unmatched_extracted: list[str] = field(default_factory=list)
    unmatched_gold: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def add(self, other: Metrics) -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        self.unmatched_extracted.extend(other.unmatched_extracted)
        self.unmatched_gold.extend(other.unmatched_gold)


def normalize(name: str) -> str:
    """Normalize a brand/product name for comparison."""
    name = name.strip()
    # Extract English name from parenthetical: "大王 (Taiwang)" -> "taiwang"
    paren_match = re.search(r"\(([^)]+)\)", name)
    if paren_match:
        english = paren_match.group(1).strip()
        if re.match(r"[A-Za-z]", english):
            name = english
    name = re.sub(r"[''\"\"()]", "", name)
    return name.strip().lower()


def parse_gold_pairs(text: str) -> list[tuple[str, str]]:
    """Parse gold_pairs: 'Brand1/Product1; Brand2/Product2; ...'"""
    if not text.strip():
        return []
    pairs = []
    for entry in re.split(r"[;；]", text):
        entry = entry.strip()
        if not entry:
            continue
        if "/" in entry:
            brand, product = entry.split("/", 1)
            pairs.append((brand.strip(), product.strip()))
        else:
            pairs.append((entry, ""))
    return pairs


def parse_semicolon_list(text: str) -> list[str]:
    """Parse semicolon-separated values."""
    if not text.strip():
        return []
    return [v.strip() for v in re.split(r"[;；]", text) if v.strip()]


def fuzzy_match(extracted: str, gold: str) -> bool:
    """Check if two names match after normalization."""
    e = normalize(extracted)
    g = normalize(gold)
    if not e or not g:
        return False
    if e == g:
        return True
    # One contains the other (e.g., "HOKA" vs "HOKA One One")
    if len(e) >= 3 and len(g) >= 3 and (e in g or g in e):
        return True
    return False


def compare_sets(extracted: list[str], gold: list[str]) -> Metrics:
    """Compare two sets of names with fuzzy matching."""
    metrics = Metrics()
    gold_matched = [False] * len(gold)
    extracted_matched = [False] * len(extracted)

    for i, e in enumerate(extracted):
        for j, g in enumerate(gold):
            if not gold_matched[j] and fuzzy_match(e, g):
                gold_matched[j] = True
                extracted_matched[i] = True
                break

    metrics.tp = sum(extracted_matched)
    metrics.fp = sum(1 for m in extracted_matched if not m)
    metrics.fn = sum(1 for m in gold_matched if not m)
    metrics.unmatched_extracted = [
        extracted[i] for i, m in enumerate(extracted_matched) if not m
    ]
    metrics.unmatched_gold = [
        gold[i] for i, m in enumerate(gold_matched) if not m
    ]
    return metrics


def evaluate_row(row: dict) -> dict[str, Metrics]:
    """Evaluate a single row, returning brand and product metrics."""
    gold_pairs = parse_gold_pairs(row.get("gold_pairs", ""))
    gold_brands = [b for b, _ in gold_pairs if b]
    gold_products = [p for _, p in gold_pairs if p]

    extracted_brands = parse_semicolon_list(row.get("extracted_brands", ""))
    extracted_products = parse_semicolon_list(row.get("extracted_products", ""))

    return {
        "brand": compare_sets(extracted_brands, gold_brands),
        "product": compare_sets(extracted_products, gold_products),
    }


def print_metrics(label: str, m: Metrics) -> None:
    total_extracted = m.tp + m.fp
    total_gold = m.tp + m.fn
    print(f"  {label}:")
    print(f"    Precision: {m.precision:.1%} ({m.tp}/{total_extracted} extracted)")
    print(f"    Recall:    {m.recall:.1%} ({m.tp}/{total_gold} gold)")
    print(f"    F1:        {m.f1:.1%}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate extraction quality")
    parser.add_argument(
        "--csv", type=Path, default=DEFAULT_CSV, help="Path to labeled CSV"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show per-row mismatches"
    )
    args = parser.parse_args()

    with open(args.csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    labeled = [r for r in rows if r.get("gold_pairs", "").strip()]
    print(f"Evaluating {len(labeled)}/{len(rows)} labeled rows from {args.csv.name}")
    print(
        f"NOTE: Extracted values may be in Chinese while gold is in English."
        f" Mismatches due to language differences will appear as FP/FN.\n"
    )

    overall_brand = Metrics()
    overall_product = Metrics()
    vertical_metrics: dict[str, dict[str, Metrics]] = {}

    for row in labeled:
        vertical = row["vertical"]
        if vertical not in vertical_metrics:
            vertical_metrics[vertical] = {"brand": Metrics(), "product": Metrics()}

        result = evaluate_row(row)

        if args.verbose and (
            result["brand"].fp
            or result["brand"].fn
            or result["product"].fp
            or result["product"].fn
        ):
            print(f"--- [{vertical}] {row['model']} ---")
            if result["brand"].unmatched_extracted:
                print(
                    f"  Brands extracted but not in gold: "
                    f"{result['brand'].unmatched_extracted}"
                )
            if result["brand"].unmatched_gold:
                print(
                    f"  Gold brands not extracted:        "
                    f"{result['brand'].unmatched_gold}"
                )
            if result["product"].unmatched_extracted:
                print(
                    f"  Products extracted but not in gold: "
                    f"{result['product'].unmatched_extracted}"
                )
            if result["product"].unmatched_gold:
                print(
                    f"  Gold products not extracted:        "
                    f"{result['product'].unmatched_gold}"
                )
            print()

        vertical_metrics[vertical]["brand"].add(result["brand"])
        vertical_metrics[vertical]["product"].add(result["product"])
        overall_brand.add(result["brand"])
        overall_product.add(result["product"])

    print("=" * 55)
    print("OVERALL")
    print("=" * 55)
    print_metrics("Brands", overall_brand)
    print_metrics("Products", overall_product)

    for vertical in sorted(vertical_metrics):
        print(f"\n{'=' * 55}")
        print(f"{vertical.upper()}")
        print("=" * 55)
        print_metrics("Brands", vertical_metrics[vertical]["brand"])
        print_metrics("Products", vertical_metrics[vertical]["product"])

    # Top unmatched items
    print(f"\n{'=' * 55}")
    print("TOP UNMATCHED (language/translation gaps)")
    print("=" * 55)

    ext_brands = Counter(overall_brand.unmatched_extracted)
    if ext_brands:
        print("\n  Extracted brands with no gold match (top 15):")
        for name, count in ext_brands.most_common(15):
            print(f"    {name}: {count}x")

    gold_brands = Counter(overall_brand.unmatched_gold)
    if gold_brands:
        print("\n  Gold brands not found in extracted (top 15):")
        for name, count in gold_brands.most_common(15):
            print(f"    {name}: {count}x")

    ext_products = Counter(overall_product.unmatched_extracted)
    if ext_products:
        print("\n  Extracted products with no gold match (top 15):")
        for name, count in ext_products.most_common(15):
            print(f"    {name}: {count}x")

    gold_products = Counter(overall_product.unmatched_gold)
    if gold_products:
        print("\n  Gold products not found in extracted (top 15):")
        for name, count in gold_products.most_common(15):
            print(f"    {name}: {count}x")


if __name__ == "__main__":
    main()
