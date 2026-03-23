---
id: consolidation_group_variants
version: v2
requires:
  - vertical
  - vertical_description
  - products_by_brand_json
  - unmapped_products_json
---
You consolidate product variants for the {{ vertical }} industry.

Vertical description: {{ vertical_description }}

Products grouped by brand:
{{ products_by_brand_json }}

Unmapped products (no brand assigned yet):
{{ unmapped_products_json }}

Return JSON only with this shape:
{
  "product_aliases": {
    "Moab 3 Waterproof": "Moab 3",
    "Moab 3 GTX": "Moab 3",
    "X Ultra 4 GTX": "X Ultra 4",
    "Anacapa Mid GTX": "Anacapa",
    "Anacapa 2 GTX": "Anacapa",
    "Free Hiker 2 GTX": "Free Hiker"
  },
  "product_brand_map": {
    "Moab 3": "Merrell"
  }
}

Rules:
- AGGRESSIVELY group product variants. Products differing only by suffix (GTX, Waterproof, Mid, Low, WP, ALL-WTHR, DM-i, EV, Pro, Plus, Max) are the SAME base product.
- Products differing only by generation number (e.g. "Anacapa GTX", "Anacapa 2 GTX", "Anacapa Mid GTX") are variants of the same base product line.
- Pick the shortest, most recognizable name as canonical (strip suffixes).
- When a brand has multiple variants of the same product line, consolidate them ALL into one canonical name.
- Map unmapped products to their brand if you can identify it.
- Do not invent products or brands not in the inputs.
- Return empty dicts if no grouping is needed.
