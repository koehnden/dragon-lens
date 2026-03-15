#!/usr/bin/env python3
"""Evaluate the extraction pipeline against gold-standard labels.

Feeds LLM response texts through the actual ExtractionPipeline and compares
the extracted brand/product pairs against human/AI-labeled gold pairs.

Requires:
  - Ollama running with the configured NER model
  - Knowledge DB (auto-created as temporary SQLite)

Usage (from project root):
    PYTHONPATH=src python scripts/evaluate_extraction.py
    PYTHONPATH=src python scripts/evaluate_extraction.py --verbose
    PYTHONPATH=src python scripts/evaluate_extraction.py --csv data/gold_pairs_chatgpt.csv
    PYTHONPATH=src python scripts/evaluate_extraction.py --model qwen3.5:9b-q4_K_M
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Add src to path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CSV = DATA_DIR / "gold_pairs_chatgpt.csv"

VERTICAL_DESCRIPTIONS = {
    "SUV Cars": "Sport utility vehicles for family and personal use",
    "Hiking Shoes": "Hiking boots, trail shoes, and outdoor footwear",
    "Diapers": "Baby diapers, pull-ups, and related baby care products",
}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# String matching
# ---------------------------------------------------------------------------

def normalize(name: str) -> str:
    name = name.strip()
    # Extract English from parenthetical: "大王 (Taiwang)" -> "taiwang"
    paren = re.search(r"\(([^)]+)\)", name)
    if paren:
        eng = paren.group(1).strip()
        if re.match(r"[A-Za-z]", eng):
            name = eng
    name = re.sub(r"[''\"\"()]", "", name)
    return name.strip().lower()


def fuzzy_match(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 3 and len(nb) >= 3 and (na in nb or nb in na):
        return True
    return False


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_gold_pairs(text: str) -> list[tuple[str, str]]:
    """Parse 'Brand1/Product1; Brand2/Product2; ...'"""
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


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare_sets(extracted: list[str], gold: list[str]) -> Metrics:
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


def compare_pairs(
    extracted_pairs: list[tuple[str, str]],
    gold_pairs: list[tuple[str, str]],
) -> Metrics:
    metrics = Metrics()
    gold_matched = [False] * len(gold_pairs)
    extracted_matched = [False] * len(extracted_pairs)

    for i, (eb, ep) in enumerate(extracted_pairs):
        for j, (gb, gp) in enumerate(gold_pairs):
            if gold_matched[j]:
                continue
            brand_ok = fuzzy_match(eb, gb) if eb and gb else (not eb and not gb)
            product_ok = fuzzy_match(ep, gp) if ep and gp else (not ep and not gp)
            if brand_ok and product_ok:
                gold_matched[j] = True
                extracted_matched[i] = True
                break

    metrics.tp = sum(extracted_matched)
    metrics.fp = sum(1 for m in extracted_matched if not m)
    metrics.fn = sum(1 for m in gold_matched if not m)
    metrics.unmatched_extracted = [
        f"{extracted_pairs[i][0]}/{extracted_pairs[i][1]}"
        for i, m in enumerate(extracted_matched) if not m
    ]
    metrics.unmatched_gold = [
        f"{gold_pairs[i][0]}/{gold_pairs[i][1]}"
        for i, m in enumerate(gold_matched) if not m
    ]
    return metrics


def print_metrics(label: str, m: Metrics) -> None:
    total_extracted = m.tp + m.fp
    total_gold = m.tp + m.fn
    print(f"  {label}:")
    print(f"    Precision: {m.precision:.1%} ({m.tp}/{total_extracted} extracted)")
    print(f"    Recall:    {m.recall:.1%} ({m.tp}/{total_gold} gold)")
    print(f"    F1:        {m.f1:.1%}")


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def run_evaluation(
    csv_path: Path, verbose: bool, model_override: str | None, use_deepseek: bool = False,
) -> None:
    # Override model before importing pipeline (settings read at import time)
    if model_override:
        os.environ["OLLAMA_MODEL_NER"] = model_override
        print(f"Model override: {model_override}")

    # Use a temporary knowledge DB so benchmark runs are isolated
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    os.environ["KNOWLEDGE_DATABASE_URL"] = f"sqlite:///{tmp_db.name}"

    if not use_deepseek:
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ["DEEPSEEK_API_KEY"] = ""
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ["OPENROUTER_API_KEY"] = ""

    from services.extraction.pipeline import ExtractionPipeline

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    labeled = [r for r in rows if r.get("gold_pairs", "").strip()]
    print(f"Evaluating {len(labeled)} labeled responses from {csv_path.name}")
    print(f"Remote validation (DeepSeek/OpenRouter): {'ENABLED' if use_deepseek else 'DISABLED'}")
    if model_override:
        print(f"NER model: {model_override}")
    print(f"Temp knowledge DB: {tmp_db.name}\n")

    by_vertical: dict[str, list[dict]] = defaultdict(list)
    for row in labeled:
        by_vertical[row["vertical"]].append(row)

    overall_brand = Metrics()
    overall_product = Metrics()
    overall_pair = Metrics()
    vertical_metrics: dict[str, dict[str, Metrics]] = {}
    total_start = time.time()

    for vertical in sorted(by_vertical):
        vert_rows = by_vertical[vertical]
        description = VERTICAL_DESCRIPTIONS.get(vertical, vertical)

        print(f"{'=' * 55}")
        print(f"{vertical} ({len(vert_rows)} responses)")
        print("=" * 55)

        pipeline = ExtractionPipeline(
            vertical=vertical,
            vertical_description=description,
            db=None,
            run_id=None,
        )

        try:
            for i, row in enumerate(vert_rows):
                response_id = f"{vertical}-{i}"
                print(
                    f"  [{i+1}/{len(vert_rows)}] {row['model'][:35]}",
                    end="",
                    flush=True,
                )
                start = time.time()
                await pipeline.process_response(
                    row["response_en_full"],
                    response_id=response_id,
                    user_brands=[],
                )
                print(f" ({time.time() - start:.1f}s)")

            print(f"  Finalizing...", end="", flush=True)
            start = time.time()
            batch = await pipeline.finalize()
            print(f" ({time.time() - start:.1f}s)\n")

            if vertical not in vertical_metrics:
                vertical_metrics[vertical] = {
                    "brand": Metrics(),
                    "product": Metrics(),
                    "pair": Metrics(),
                }

            for i, row in enumerate(vert_rows):
                response_id = f"{vertical}-{i}"
                extraction = batch.response_results.get(response_id)
                if not extraction:
                    print(f"  WARNING: No result for {response_id}")
                    continue

                # Collect extracted brands, products, and pairs
                extracted_brands = list(extraction.brands.keys())
                extracted_products = list(extraction.products.keys())

                extracted_pairs: list[tuple[str, str]] = []
                paired_brands: set[str] = set()
                paired_products: set[str] = set()
                for product, brand in extraction.product_brand_relationships.items():
                    extracted_pairs.append((brand, product))
                    paired_brands.add(brand)
                    paired_products.add(product)
                # Add unpaired brands/products
                for b in extracted_brands:
                    if b not in paired_brands:
                        extracted_pairs.append((b, ""))
                for p in extracted_products:
                    if p not in paired_products:
                        extracted_pairs.append(("", p))

                gold_pairs = parse_gold_pairs(row["gold_pairs"])
                gold_brands = [b for b, _ in gold_pairs if b]
                gold_products = [p for _, p in gold_pairs if p]

                brand_m = compare_sets(extracted_brands, gold_brands)
                product_m = compare_sets(extracted_products, gold_products)
                pair_m = compare_pairs(extracted_pairs, gold_pairs)

                if verbose and (brand_m.fp or brand_m.fn or
                                product_m.fp or product_m.fn):
                    print(f"  --- {row['model'][:35]} ---")
                    print(f"    Extracted: {[f'{b}/{p}' for b, p in extracted_pairs]}")
                    print(f"    Gold:      {[f'{b}/{p}' for b, p in gold_pairs]}")
                    if brand_m.unmatched_extracted:
                        print(f"    FP brands:     {brand_m.unmatched_extracted}")
                    if brand_m.unmatched_gold:
                        print(f"    Missed brands: {brand_m.unmatched_gold}")
                    if product_m.unmatched_extracted:
                        print(f"    FP products:     {product_m.unmatched_extracted}")
                    if product_m.unmatched_gold:
                        print(f"    Missed products: {product_m.unmatched_gold}")
                    print()

                vertical_metrics[vertical]["brand"].add(brand_m)
                vertical_metrics[vertical]["product"].add(product_m)
                vertical_metrics[vertical]["pair"].add(pair_m)
                overall_brand.add(brand_m)
                overall_product.add(product_m)
                overall_pair.add(pair_m)

        finally:
            pipeline.close()

    total_elapsed = time.time() - total_start

    # Print summary
    print(f"\n{'=' * 55}")
    print(f"OVERALL RESULTS ({total_elapsed:.0f}s)")
    print("=" * 55)
    print_metrics("Brands", overall_brand)
    print_metrics("Products", overall_product)
    print_metrics("Pairs (brand+product)", overall_pair)

    for vertical in sorted(vertical_metrics):
        print(f"\n{'=' * 55}")
        print(f"{vertical.upper()}")
        print("=" * 55)
        print_metrics("Brands", vertical_metrics[vertical]["brand"])
        print_metrics("Products", vertical_metrics[vertical]["product"])
        print_metrics("Pairs", vertical_metrics[vertical]["pair"])

    # Top unmatched
    print(f"\n{'=' * 55}")
    print("TOP UNMATCHED")
    print("=" * 55)
    for label, metrics in [("Brands", overall_brand), ("Products", overall_product)]:
        ext = Counter(metrics.unmatched_extracted)
        if ext:
            print(f"\n  Extracted {label.lower()} not in gold (top 10):")
            for name, count in ext.most_common(10):
                print(f"    {name}: {count}x")
        gold = Counter(metrics.unmatched_gold)
        if gold:
            print(f"\n  Gold {label.lower()} not extracted (top 10):")
            for name, count in gold.most_common(10):
                print(f"    {name}: {count}x")

    # Cleanup temp DB
    try:
        os.unlink(tmp_db.name)
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate extraction pipeline against gold labels"
    )
    parser.add_argument(
        "--csv", type=Path, default=DEFAULT_CSV,
        help="Path to labeled CSV (default: data/gold_pairs_chatgpt.csv)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override NER model (e.g., qwen3.5:9b-q4_K_M)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show per-response mismatches",
    )
    parser.add_argument(
        "--deepseek", action="store_true",
        help="Enable DeepSeek normalization/validation (uses API key from .env)",
    )
    parser.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Pipeline log level (default: WARNING)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level))

    asyncio.run(run_evaluation(args.csv, args.verbose, args.model, args.deepseek))


if __name__ == "__main__":
    main()
