#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CSV = DATA_DIR / "gold_pairs_chatgpt.csv"

VERTICAL_DESCRIPTIONS = {
    "SUV Cars": "Sport utility vehicles for family and personal use",
    "Hiking Shoes": "Hiking boots, trail shoes, and outdoor footwear",
    "Diapers": "Baby diapers, pull-ups, and related baby care products",
}


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


def extract_english_from_parenthetical(name: str) -> str:
    paren = re.search(r"\(([^)]+)\)", name)
    if paren:
        eng = paren.group(1).strip()
        if re.match(r"[A-Za-z]", eng):
            return eng
    return name


def normalize(name: str) -> str:
    name = extract_english_from_parenthetical(name.strip())
    name = re.sub(r"[''\"\"()]", "", name)
    return name.strip().lower()


def fuzzy_match(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return len(na) >= 3 and len(nb) >= 3 and (na in nb or nb in na)


def parse_gold_pairs(text: str) -> list[tuple[str, str]]:
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


def match_extracted_against_gold(extracted: list, gold: list, match_fn) -> tuple[list[bool], list[bool]]:
    gold_matched = [False] * len(gold)
    extracted_matched = [False] * len(extracted)
    for i, e in enumerate(extracted):
        for j, g in enumerate(gold):
            if not gold_matched[j] and match_fn(e, g):
                gold_matched[j] = True
                extracted_matched[i] = True
                break
    return extracted_matched, gold_matched


def build_metrics_from_matches(
    extracted_matched: list[bool],
    gold_matched: list[bool],
    extracted_labels: list[str],
    gold_labels: list[str],
) -> Metrics:
    return Metrics(
        tp=sum(extracted_matched),
        fp=sum(1 for m in extracted_matched if not m),
        fn=sum(1 for m in gold_matched if not m),
        unmatched_extracted=[extracted_labels[i] for i, m in enumerate(extracted_matched) if not m],
        unmatched_gold=[gold_labels[i] for i, m in enumerate(gold_matched) if not m],
    )


def compare_sets(extracted: list[str], gold: list[str]) -> Metrics:
    extracted_matched, gold_matched = match_extracted_against_gold(extracted, gold, fuzzy_match)
    return build_metrics_from_matches(extracted_matched, gold_matched, extracted, gold)


def pairs_match(pair_a: tuple[str, str], pair_b: tuple[str, str]) -> bool:
    eb, ep = pair_a
    gb, gp = pair_b
    brand_ok = fuzzy_match(eb, gb) if eb and gb else (not eb and not gb)
    product_ok = fuzzy_match(ep, gp) if ep and gp else (not ep and not gp)
    return brand_ok and product_ok


def compare_pairs(
    extracted_pairs: list[tuple[str, str]],
    gold_pairs: list[tuple[str, str]],
) -> Metrics:
    extracted_matched, gold_matched = match_extracted_against_gold(
        extracted_pairs, gold_pairs, pairs_match,
    )
    extracted_labels = [f"{b}/{p}" for b, p in extracted_pairs]
    gold_labels = [f"{b}/{p}" for b, p in gold_pairs]
    return build_metrics_from_matches(extracted_matched, gold_matched, extracted_labels, gold_labels)


def print_metrics(label: str, m: Metrics) -> None:
    print(f"  {label}:")
    print(f"    Precision: {m.precision:.1%} ({m.tp}/{m.tp + m.fp} extracted)")
    print(f"    Recall:    {m.recall:.1%} ({m.tp}/{m.tp + m.fn} gold)")
    print(f"    F1:        {m.f1:.1%}")


def serialize_item_result(ir) -> dict:
    return {
        "item": {"text": ir.item.text, "position": ir.item.position, "response_id": ir.item.response_id},
        "pairs": [
            {"brand": p.brand, "product": p.product, "brand_source": p.brand_source, "product_source": p.product_source}
            for p in ir.pairs
        ],
    }


def serialize_response_results(response_results: dict) -> list[dict]:
    return [
        {"response_id": response_id, "items": [serialize_item_result(ir) for ir in item_results]}
        for response_id, item_results in response_results.items()
    ]


def deserialize_pair(p: dict):
    from services.extraction.models import BrandProductPair
    return BrandProductPair(
        brand=p.get("brand"),
        product=p.get("product"),
        brand_source=p.get("brand_source", ""),
        product_source=p.get("product_source", ""),
    )


def deserialize_item_result(item_data: dict):
    from services.extraction.models import ItemExtractionResult, ResponseItem
    item = ResponseItem(
        text=item_data["item"]["text"],
        position=item_data["item"]["position"],
        response_id=item_data["item"].get("response_id"),
    )
    pairs = [deserialize_pair(p) for p in item_data["pairs"]]
    return ItemExtractionResult(item=item, pairs=pairs)


def deserialize_response_results(data: list[dict]) -> dict:
    return {
        entry["response_id"]: [deserialize_item_result(item) for item in entry["items"]]
        for entry in data
    }


def save_extraction_cache(cache_path: Path, pipelines: dict) -> None:
    cache = {vertical: serialize_response_results(p._response_results) for vertical, p in pipelines.items()}
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"Extraction cache saved to {cache_path}")


def load_extraction_cache(cache_path: Path) -> dict[str, dict]:
    with open(cache_path, encoding="utf-8") as f:
        cache = json.load(f)
    result = {vertical: deserialize_response_results(data) for vertical, data in cache.items()}
    print(f"Loaded extraction cache from {cache_path}")
    return result


def create_isolated_knowledge_db() -> tempfile.NamedTemporaryFile:
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    os.environ["KNOWLEDGE_DATABASE_URL"] = f"sqlite:///{tmp_db.name}"
    return tmp_db


def disable_remote_validation():
    os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ["OPENROUTER_API_KEY"] = ""


def load_labeled_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r.get("gold_pairs", "").strip()]


def group_by_vertical(rows: list[dict]) -> dict[str, list[dict]]:
    by_vertical: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_vertical[row["vertical"]].append(row)
    return by_vertical


def collect_extracted_pairs(extraction) -> list[tuple[str, str]]:
    extracted_pairs: list[tuple[str, str]] = []
    paired_brands: set[str] = set()
    paired_products: set[str] = set()
    for product, brand in extraction.product_brand_relationships.items():
        extracted_pairs.append((brand, product))
        paired_brands.add(brand)
        paired_products.add(product)
    for b in extraction.brands:
        if b not in paired_brands:
            extracted_pairs.append((b, ""))
    for p in extraction.products:
        if p not in paired_products:
            extracted_pairs.append(("", p))
    return extracted_pairs


def print_verbose_mismatches(row, extracted_pairs, gold_pairs, brand_m, product_m):
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


def evaluate_response(extraction, row, verbose) -> tuple[Metrics, Metrics, Metrics]:
    extracted_brands = list(extraction.brands.keys())
    extracted_products = list(extraction.products.keys())
    extracted_pairs = collect_extracted_pairs(extraction)
    gold_pairs = parse_gold_pairs(row["gold_pairs"])
    gold_brands = [b for b, _ in gold_pairs if b]
    gold_products = [p for _, p in gold_pairs if p]

    brand_m = compare_sets(extracted_brands, gold_brands)
    product_m = compare_sets(extracted_products, gold_products)
    pair_m = compare_pairs(extracted_pairs, gold_pairs)

    if verbose and (brand_m.fp or brand_m.fn or product_m.fp or product_m.fn):
        print_verbose_mismatches(row, extracted_pairs, gold_pairs, brand_m, product_m)

    return brand_m, product_m, pair_m


async def run_extraction_for_vertical(pipeline, vert_rows, vertical):
    for i, row in enumerate(vert_rows):
        response_id = f"{vertical}-{i}"
        print(f"  [{i+1}/{len(vert_rows)}] {row['model'][:35]}", end="", flush=True)
        start = time.time()
        await pipeline.process_response(row["response_en_full"], response_id=response_id, user_brands=[])
        print(f" ({time.time() - start:.1f}s)")


async def finalize_and_evaluate_vertical(
    pipeline, vert_rows, vertical, verbose,
) -> tuple[Metrics, Metrics, Metrics]:
    print("  Finalizing...", end="", flush=True)
    start = time.time()
    batch = await pipeline.finalize()
    print(f" ({time.time() - start:.1f}s)\n")

    brand_total, product_total, pair_total = Metrics(), Metrics(), Metrics()
    for i, row in enumerate(vert_rows):
        response_id = f"{vertical}-{i}"
        extraction = batch.response_results.get(response_id)
        if not extraction:
            print(f"  WARNING: No result for {response_id}")
            continue
        brand_m, product_m, pair_m = evaluate_response(extraction, row, verbose)
        brand_total.add(brand_m)
        product_total.add(product_m)
        pair_total.add(pair_m)
    return brand_total, product_total, pair_total


def print_overall_summary(total_elapsed, overall_brand, overall_product, overall_pair):
    print(f"\n{'=' * 55}")
    print(f"OVERALL RESULTS ({total_elapsed:.0f}s)")
    print("=" * 55)
    print_metrics("Brands", overall_brand)
    print_metrics("Products", overall_product)
    print_metrics("Pairs (brand+product)", overall_pair)


def print_vertical_summary(vertical_metrics):
    for vertical in sorted(vertical_metrics):
        print(f"\n{'=' * 55}")
        print(f"{vertical.upper()}")
        print("=" * 55)
        print_metrics("Brands", vertical_metrics[vertical]["brand"])
        print_metrics("Products", vertical_metrics[vertical]["product"])
        print_metrics("Pairs", vertical_metrics[vertical]["pair"])


def print_top_unmatched(overall_brand, overall_product):
    print(f"\n{'=' * 55}")
    print("TOP UNMATCHED")
    print("=" * 55)
    for label, metrics in [("Brands", overall_brand), ("Products", overall_product)]:
        fp_counts = Counter(metrics.unmatched_extracted)
        if fp_counts:
            print(f"\n  Extracted {label.lower()} not in gold (top 10):")
            for name, count in fp_counts.most_common(10):
                print(f"    {name}: {count}x")
        fn_counts = Counter(metrics.unmatched_gold)
        if fn_counts:
            print(f"\n  Gold {label.lower()} not extracted (top 10):")
            for name, count in fn_counts.most_common(10):
                print(f"    {name}: {count}x")


def print_run_header(labeled, csv_path, use_deepseek, load_extraction, save_extraction, model_override, tmp_db):
    print(f"Evaluating {len(labeled)} labeled responses from {csv_path.name}")
    print(f"Remote validation (DeepSeek/OpenRouter): {'ENABLED' if use_deepseek else 'DISABLED'}")
    if load_extraction:
        print(f"Mode: consolidation-only (loading extraction from {load_extraction})")
    elif save_extraction:
        print(f"Mode: extraction + save (will save to {save_extraction})")
    if model_override:
        print(f"NER model: {model_override}")
    print(f"Temp knowledge DB: {tmp_db.name}\n")


async def run_evaluation(
    csv_path: Path, verbose: bool, model_override: str | None, use_deepseek: bool = False,
    save_extraction: Path | None = None, load_extraction: Path | None = None,
) -> None:
    if model_override:
        os.environ["OLLAMA_MODEL_NER"] = model_override

    tmp_db = create_isolated_knowledge_db()
    if not use_deepseek:
        disable_remote_validation()

    from services.extraction.pipeline import ExtractionPipeline

    labeled = load_labeled_rows(csv_path)
    print_run_header(labeled, csv_path, use_deepseek, load_extraction, save_extraction, model_override, tmp_db)

    by_vertical = group_by_vertical(labeled)
    cached_extraction = load_extraction_cache(load_extraction) if load_extraction else None

    overall_brand, overall_product, overall_pair = Metrics(), Metrics(), Metrics()
    vertical_metrics: dict[str, dict[str, Metrics]] = {}
    pipelines_for_cache: dict[str, ExtractionPipeline] = {}
    total_start = time.time()

    for vertical in sorted(by_vertical):
        vert_rows = by_vertical[vertical]
        description = VERTICAL_DESCRIPTIONS.get(vertical, vertical)

        print(f"{'=' * 55}")
        print(f"{vertical} ({len(vert_rows)} responses)")
        print("=" * 55)

        pipeline = ExtractionPipeline(vertical=vertical, vertical_description=description, db=None, run_id=None)
        try:
            if cached_extraction and vertical in cached_extraction:
                pipeline._response_results = cached_extraction[vertical]
                print(f"  Loaded {len(pipeline._response_results)} cached responses")
            else:
                await run_extraction_for_vertical(pipeline, vert_rows, vertical)

            if save_extraction:
                pipelines_for_cache[vertical] = pipeline

            brand_m, product_m, pair_m = await finalize_and_evaluate_vertical(pipeline, vert_rows, vertical, verbose)
            vertical_metrics[vertical] = {"brand": brand_m, "product": product_m, "pair": pair_m}
            overall_brand.add(brand_m)
            overall_product.add(product_m)
            overall_pair.add(pair_m)
        finally:
            pipeline.close()

    if save_extraction and pipelines_for_cache:
        save_extraction_cache(save_extraction, pipelines_for_cache)

    total_elapsed = time.time() - total_start
    print_overall_summary(total_elapsed, overall_brand, overall_product, overall_pair)
    print_vertical_summary(vertical_metrics)
    print_top_unmatched(overall_brand, overall_product)

    try:
        os.unlink(tmp_db.name)
    except OSError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate extraction pipeline against gold labels")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--deepseek", action="store_true")
    parser.add_argument("--save-extraction", type=Path, default=None)
    parser.add_argument("--load-extraction", type=Path, default=None)
    parser.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))
    asyncio.run(run_evaluation(
        args.csv, args.verbose, args.model, args.deepseek,
        save_extraction=args.save_extraction,
        load_extraction=args.load_extraction,
    ))


if __name__ == "__main__":
    main()
