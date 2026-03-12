"""Export LLM responses as CSV for gold set labeling.

Two modes:
  1. From existing run:  python scripts/export_gold_set_csv.py --run-id 5
  2. From API (latest):  python scripts/export_gold_set_csv.py --vertical "SUV Cars"

Outputs a CSV with one row per parsed list item, ready for manual labeling
in Google Sheets. Pre-fills the pipeline's current extraction as a starting
point (columns prefixed with `pred_`), so you only need to correct mistakes.

Usage:
  python scripts/export_gold_set_csv.py --run-id 5 --output gold_set.csv
  python scripts/export_gold_set_csv.py --vertical "SUV Cars" --output gold_set.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import settings
from services.brand_recognition.list_processor import (
    is_list_format,
    split_into_list_items,
)
from services.brand_recognition.markdown_table import (
    extract_markdown_table_row_items,
    markdown_table_has_min_data_rows,
)


API_BASE = f"http://localhost:{settings.api_port}/api/v1"


def fetch_run_details(run_id: int) -> dict:
    """Fetch full run details including answers."""
    resp = requests.get(f"{API_BASE}/tracking/runs/{run_id}/details")
    resp.raise_for_status()
    return resp.json()


def fetch_latest_run_for_vertical(vertical_name: str) -> dict:
    """Find the latest completed run for a vertical and fetch its details."""
    resp = requests.get(f"{API_BASE}/tracking/runs")
    resp.raise_for_status()
    runs = resp.json()

    matching = [
        r for r in runs
        if r.get("vertical_name") == vertical_name
        and r.get("status") == "completed"
    ]
    if not matching:
        print(f"No completed runs found for vertical '{vertical_name}'")
        print("Available verticals with completed runs:")
        seen = set()
        for r in runs:
            if r.get("status") == "completed":
                name = r.get("vertical_name", "?")
                if name not in seen:
                    print(f"  - {name} (run_id={r['id']})")
                    seen.add(name)
        sys.exit(1)

    latest = max(matching, key=lambda r: r.get("id", 0))
    return fetch_run_details(latest["id"])


def parse_items_from_response(text: str) -> list[str]:
    """Parse a response into individual list items."""
    if not text:
        return []

    if is_list_format(text):
        items = split_into_list_items(text)
        if items:
            return items

    # Fallback: return whole text as single item
    return [text.strip()] if text.strip() else []


def extract_current_predictions(answer: dict) -> dict[int, dict]:
    """Extract current pipeline predictions for pre-filling.

    Returns {item_position: {brand_zh, brand_en, product_zh, product_en}}.
    """
    preds = {}
    brands = answer.get("brands_extracted") or answer.get("mentions") or []

    for mention in brands:
        brand_zh = mention.get("brand_zh") or mention.get("original_name", "")
        brand_en = mention.get("brand_en") or mention.get("translated_name", "")
        rank = mention.get("rank")
        products_zh = mention.get("products_zh", [])
        products_en = mention.get("products_en", [])

        if rank is not None:
            preds[rank] = {
                "brand_zh": brand_zh,
                "brand_en": brand_en,
                "product_zh": products_zh[0] if products_zh else "",
                "product_en": products_en[0] if products_en else "",
            }
    return preds


def build_rows(run_data: dict) -> list[dict]:
    """Build CSV rows from run data."""
    rows = []
    run_id = run_data.get("id", "?")
    answers = run_data.get("answers", [])

    for answer in answers:
        prompt_text = answer.get("prompt_zh") or answer.get("prompt", {}).get("text_zh", "")
        response_text = answer.get("raw_answer_zh", "")
        prompt_id = answer.get("prompt_id", "?")

        items = parse_items_from_response(response_text)
        predictions = extract_current_predictions(answer)

        for pos, item_text in enumerate(items):
            item_text_clean = item_text.strip()
            if not item_text_clean:
                continue

            pred = predictions.get(pos + 1, {})

            rows.append({
                "run_id": run_id,
                "prompt_id": prompt_id,
                "prompt_text": prompt_text[:100] + "..." if len(prompt_text) > 100 else prompt_text,
                "item_position": pos + 1,
                "item_text": item_text_clean[:200],
                "gold_brand": "",       # <-- LABEL THIS
                "gold_product": "",     # <-- LABEL THIS
                "gold_brand_canonical": "",  # <-- LABEL THIS (English)
                "pred_brand_zh": pred.get("brand_zh", ""),
                "pred_brand_en": pred.get("brand_en", ""),
                "pred_product_zh": pred.get("product_zh", ""),
                "pred_product_en": pred.get("product_en", ""),
                "notes": "",
            })

    return rows


def build_rows_from_inspector(run_id: int) -> list[dict]:
    """Alternative: use inspector export endpoint."""
    resp = requests.get(f"{API_BASE}/tracking/runs/{run_id}/inspector-export")
    resp.raise_for_status()
    export_data = resp.json()

    rows = []
    for entry in export_data:
        response_text = entry.get("prompt_response_zh", "")
        prompt_text = entry.get("prompt_zh", "")
        brands = entry.get("brands_extracted", [])

        items = parse_items_from_response(response_text)

        # Build a rank -> brand/product lookup from extraction results
        preds_by_rank = {}
        for brand_info in brands:
            rank = brand_info.get("rank")
            if rank is not None:
                preds_by_rank[rank] = {
                    "brand_zh": brand_info.get("brand_zh", ""),
                    "brand_en": brand_info.get("brand_en", ""),
                    "product_zh": (brand_info.get("products_zh") or [""])[0],
                    "product_en": (brand_info.get("products_en") or [""])[0],
                }

        for pos, item_text in enumerate(items):
            item_text_clean = item_text.strip()
            if not item_text_clean:
                continue

            pred = preds_by_rank.get(pos + 1, {})

            rows.append({
                "run_id": run_id,
                "prompt_text": prompt_text[:100] + "..." if len(prompt_text) > 100 else prompt_text,
                "item_position": pos + 1,
                "item_text": item_text_clean[:200],
                "gold_brand": "",
                "gold_product": "",
                "gold_brand_canonical": "",
                "pred_brand_zh": pred.get("brand_zh", ""),
                "pred_brand_en": pred.get("brand_en", ""),
                "pred_product_zh": pred.get("product_zh", ""),
                "pred_product_en": pred.get("product_en", ""),
                "notes": "",
            })

    return rows


def write_csv(rows: list[dict], output_path: str) -> None:
    """Write rows to CSV file."""
    if not rows:
        print("No rows to write!")
        return

    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output_path}")
    print(f"Columns to label: gold_brand, gold_product, gold_brand_canonical")
    print(f"Pre-filled predictions in pred_* columns for reference")


def main():
    parser = argparse.ArgumentParser(
        description="Export LLM responses as CSV for gold set labeling"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", type=int, help="Specific run ID to export")
    group.add_argument("--vertical", type=str, help="Vertical name (uses latest completed run)")
    parser.add_argument(
        "--output", "-o",
        default="gold_set.csv",
        help="Output CSV file path (default: gold_set.csv)",
    )
    parser.add_argument(
        "--use-inspector",
        action="store_true",
        help="Use inspector export endpoint (includes brand extraction results)",
    )

    args = parser.parse_args()

    try:
        if args.use_inspector:
            if args.run_id:
                rid = args.run_id
            else:
                # Find latest run ID for vertical
                resp = requests.get(f"{API_BASE}/tracking/runs")
                resp.raise_for_status()
                runs = resp.json()
                matching = [
                    r for r in runs
                    if r.get("vertical_name") == args.vertical
                    and r.get("status") == "completed"
                ]
                if not matching:
                    print(f"No completed runs found for '{args.vertical}'")
                    sys.exit(1)
                rid = max(matching, key=lambda r: r.get("id", 0))["id"]
            rows = build_rows_from_inspector(rid)
        else:
            if args.run_id:
                run_data = fetch_run_details(args.run_id)
            else:
                run_data = fetch_latest_run_for_vertical(args.vertical)
            rows = build_rows(run_data)

        write_csv(rows, args.output)

    except requests.ConnectionError:
        print(f"Could not connect to API at {API_BASE}")
        print("Make sure the DragonLens server is running.")
        print(f"  Start it with: docker compose up  (or similar)")
        sys.exit(1)
    except requests.HTTPError as e:
        print(f"API error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
