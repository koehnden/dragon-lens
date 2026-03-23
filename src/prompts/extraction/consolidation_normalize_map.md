---
id: deepseek_normalize_map
version: v1
requires:
  - vertical
  - brands_json
  - products_json
  - item_pairs_json
---
You normalize brand and product names for the {{ vertical }} industry.

Vertical description: {{ vertical_description }}

Brands:
{{ brands_json }}

Products:
{{ products_json }}

Observed item-level brand/product pairs:
{{ item_pairs_json }}

Existing product-brand map from deterministic rules:
{{ existing_product_brand_map_json }}

Return JSON only with this shape:
{
  "brand_aliases": {
    "大众": "Volkswagen"
  },
  "product_aliases": {
    "宋PLUS DM-i 冠军版": "宋PLUS DM-i"
  },
  "product_brand_map": {
    "宋PLUS DM-i": "BYD"
  }
}

Rules:
- Keep canonical brand names stable across aliases and JV naming.
- Keep canonical product names concise.
- Do not invent products or brands not supported by the inputs.
