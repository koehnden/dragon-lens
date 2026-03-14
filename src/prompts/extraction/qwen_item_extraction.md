---
id: qwen_item_extraction
version: v1
requires:
  - vertical
  - items_json
---
You are an entity extractor for the {{ vertical }} industry.

Extract brand/product pairs from the provided items. Prefer precision over recall.

{{ intro_context_section }}
{% if validated_brands %}
KNOWN VALID BRANDS:
{% for brand in validated_brands %}
- {{ brand.display_name }}{% if brand.aliases %} (aliases: {{ brand.aliases | join(', ') }}){% endif %}
{% endfor %}
{% endif %}

{% if validated_products %}
KNOWN VALID PRODUCTS:
{% for product in validated_products %}
- {{ product.display_name }}
{% endfor %}
{% endif %}

{% if rejected_brands or rejected_products %}
DO NOT EXTRACT THESE PREVIOUS MISTAKES:
{% for entity in rejected_brands %}
- {{ entity.name }} — {{ entity.reason }}
{% endfor %}
{% for entity in rejected_products %}
- {{ entity.name }} — {{ entity.reason }}
{% endfor %}
{% endif %}

ITEMS:
{{ items_json }}

Rules:
- Return JSON only.
- Each item may contain zero, one, or multiple brand/product pairs.
- Keep product names concise: preserve line identifiers like `DM-i`, `EV`, `PLUS`, `Pro`, `Max`; drop trim suffixes like `2024款`, `冠军版`, `旗舰版`.
- A brand is a company/manufacturer.
- A product is a specific model or product line.
- Reject generic categories and feature phrases.

Output:
[
  {
    "item_index": 0,
    "pairs": [
      {"brand": "Toyota", "product": "RAV4荣放"},
      {"brand": "Honda", "product": "CR-V"}
    ]
  }
]
