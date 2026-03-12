---
id: deepseek_validate
version: v1
requires:
  - vertical
  - brands_json
  - products_json
---
You validate whether extracted brands and products are relevant to the {{ vertical }} industry.

Vertical description: {{ vertical_description }}

Brands:
{{ brands_json }}

Products:
{{ products_json }}

Return JSON only with this shape:
{
  "valid_brands": ["Volkswagen", "BYD"],
  "valid_products": ["RAV4荣放", "宋PLUS DM-i"],
  "rejected": [
    {"name": "SUV", "entity_type": "product", "reason": "generic category"},
    {"name": "比亚迪", "entity_type": "product", "reason": "brand, not product"}
  ]
}

Rules:
- Reject generic categories, adjectives, features, and off-vertical entities.
- Include a reason for every rejection.
