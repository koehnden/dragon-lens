#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.constants.wikidata_industries import PREDEFINED_INDUSTRIES, get_all_industry_keys
from src.models.wikidata_cache import clear_wikidata_cache, get_cache_stats
from src.services.wikidata_loader import (
    get_load_status,
    load_all_predefined_industries,
    load_custom_industry,
    load_industry,
    search_wikidata_industries,
)


def print_progress(message: str):
    print(message)


def cmd_load_all(args):
    print("Loading all predefined industries from Wikidata...")
    print("This may take several minutes due to rate limiting.\n")

    results = load_all_predefined_industries(progress_callback=print_progress)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    total_brands = 0
    total_products = 0

    for industry_key, result in results.items():
        if result["success"]:
            print(f"  {result['industry']}: {result['brands_count']} brands, {result['products_count']} products")
            total_brands += result["brands_count"]
            total_products += result["products_count"]
        else:
            print(f"  {industry_key}: FAILED - {result['error']}")

    print(f"\nTotal: {total_brands} brands, {total_products} products")


def cmd_load_predefined(args):
    industry_key = args.industry

    if industry_key not in PREDEFINED_INDUSTRIES:
        print(f"Error: Unknown industry '{industry_key}'")
        print(f"Available industries: {', '.join(get_all_industry_keys())}")
        sys.exit(1)

    print(f"Loading {industry_key} from Wikidata...")
    result = load_industry(industry_key, progress_callback=print_progress)

    if result["success"]:
        print(f"\nSuccess! Loaded {result['brands_count']} brands, {result['products_count']} products")
    else:
        print(f"\nFailed: {result['error']}")
        sys.exit(1)


def cmd_load_custom(args):
    print(f"Loading custom industry {args.wikidata_id} from Wikidata...")

    keywords = args.keywords.split(",") if args.keywords else []

    result = load_custom_industry(
        wikidata_id=args.wikidata_id,
        name_en=args.name,
        name_zh=args.name_zh or "",
        keywords=keywords,
        progress_callback=print_progress,
    )

    if result["success"]:
        print(f"\nSuccess! Loaded {result['brands_count']} brands")
    else:
        print(f"\nFailed: {result['error']}")
        sys.exit(1)


def cmd_search(args):
    print(f"Searching Wikidata for industries matching '{args.query}'...\n")

    results = search_wikidata_industries(args.query)

    if not results:
        print("No matching industries found.")
        return

    print("Found matching industries:")
    print("-" * 60)

    for i, result in enumerate(results, 1):
        print(f"{i}. {result['wikidata_id']} - {result['name_en']}")
        if result.get("description"):
            print(f"   {result['description'][:80]}...")
        print()

    print("\nTo load an industry:")
    print(f"  python scripts/load_wikidata.py --load <WIKIDATA_ID> --name '<NAME>'")


def cmd_status(args):
    print("Wikidata Cache Status")
    print("=" * 60)

    stats = get_cache_stats()
    print(f"\nCache file: {stats['cache_path']}")
    print(f"Cache exists: {stats['cache_exists']}")
    print(f"Total industries: {stats['industries']}")
    print(f"Total brands: {stats['brands']}")
    print(f"Total products: {stats['products']}")

    print("\n" + "-" * 60)
    print("Industry Details:")
    print("-" * 60)

    statuses = get_load_status()

    for status in statuses:
        status_icon = {
            "complete": "[OK]",
            "loading": "[...]",
            "error": "[ERR]",
            "not_loaded": "[ ]",
        }.get(status["status"], "[?]")

        print(f"  {status_icon} {status['industry']}")
        print(f"      Status: {status['status']}")
        print(f"      Brands: {status['brands_count']}, Products: {status['products_count']}")
        if status["completed_at"]:
            print(f"      Loaded: {status['completed_at']}")
        if status["error_message"]:
            print(f"      Error: {status['error_message']}")
        print()


def cmd_clear(args):
    if not args.force:
        confirm = input("Are you sure you want to clear all Wikidata cache? [y/N] ")
        if confirm.lower() != "y":
            print("Cancelled.")
            return

    print("Clearing Wikidata cache...")
    clear_wikidata_cache()
    print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Load and manage Wikidata cache for entity recognition"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    all_parser = subparsers.add_parser("all", help="Load all predefined industries")
    all_parser.set_defaults(func=cmd_load_all)

    predefined_parser = subparsers.add_parser("predefined", help="Load a specific predefined industry")
    predefined_parser.add_argument("industry", choices=get_all_industry_keys())
    predefined_parser.set_defaults(func=cmd_load_predefined)

    load_parser = subparsers.add_parser("load", help="Load a custom industry by Wikidata ID")
    load_parser.add_argument("wikidata_id", help="Wikidata ID (e.g., Q1420)")
    load_parser.add_argument("--name", required=True, help="Industry name in English")
    load_parser.add_argument("--name-zh", help="Industry name in Chinese")
    load_parser.add_argument("--keywords", help="Comma-separated keywords for matching")
    load_parser.set_defaults(func=cmd_load_custom)

    search_parser = subparsers.add_parser("search", help="Search Wikidata for industries")
    search_parser.add_argument("query", help="Search term")
    search_parser.set_defaults(func=cmd_search)

    status_parser = subparsers.add_parser("status", help="Show cache status")
    status_parser.set_defaults(func=cmd_status)

    clear_parser = subparsers.add_parser("clear", help="Clear all cached data")
    clear_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation")
    clear_parser.set_defaults(func=cmd_clear)

    if len(sys.argv) == 1:
        parser.print_help()
        print("\nExamples:")
        print("  python scripts/load_wikidata.py all                     # Load all predefined industries")
        print("  python scripts/load_wikidata.py predefined automotive   # Load automotive industry")
        print("  python scripts/load_wikidata.py search 'luxury'         # Search for industries")
        print("  python scripts/load_wikidata.py status                  # Show cache status")
        print("  python scripts/load_wikidata.py clear                   # Clear cache")
        sys.exit(0)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
