---
id: qwen_item_extraction
version: v5
requires:
  - vertical
  - items_json
---
You are an entity extractor for the {{ vertical }} industry.

Extract brand/product pairs from the provided items. Prefer recall over precision — when in doubt, include the entity. A later validation step will filter out incorrect extractions.

{{ intro_context_section }}
Language and market context:
- The item text is usually in Chinese or mixed Chinese/English.
- The items come from Chinese-market consumer recommendations and discussions.
- Extract entity names exactly as they appear in the item text.
- Do not translate, romanize, or normalize brand or product names.
- If the same entity appears in Chinese, English, or mixed form, keep the form used in that item.
- Chinese aliases, joint-venture names, and mixed Chinese-English product names are valid when they are the consumer-facing names used in the item text.

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
- The item text is the primary evidence. Use context only to disambiguate the item; do not extract any entity that appears only in the context and not in the item itself.
- Do not guess or fill in missing entities from world knowledge. Extract only entities explicitly supported by the item text.
- A brand is a consumer-facing company/manufacturer relevant to this vertical.
- A product is a specific consumer-facing end product or product line relevant to this vertical.
- Keep product names concise: preserve identifiers that are required to identify the product (for example `DM-i`, `EV`, `PLUS`, `Pro`, `Max`) when they are part of the full product name; drop standalone trim/year/edition suffixes like `2024款`, `冠军版`, `旗舰版` unless they are required to distinguish the product.
- Reject generic categories and general feature phrases.
- Reject single-character tokens and tokens that are just a number or size code (e.g., "S", "M", "L", "XL", "3", "42").
- Reject standalone variant/configuration tokens that are not a full product by themselves, such as isolated sizes, colors, capacities, pack counts, years, trims, editions, or style markers.
- Reject words or phrases that clearly name attributes, benefits, or ingredients rather than a brand or product.
- If unsure whether something is a material/technology brand or a consumer-facing brand, include it.
- Extract the longest valid consumer-facing brand/product span present in the item. If a token is only one part of a longer product name, extract the full product name instead of the partial token by itself.
- For ranked, bulleted, or table items, extract the main recommended end product(s) for that item.
- Extract all brand/product entities mentioned in the item, including those mentioned for comparison, as alternatives, or as secondary recommendations.
- Only ignore entities mentioned purely as accessories, compatibility notes, or background context that are clearly not products in this vertical.
- If only a product is clearly present, return the product with `"brand": null`.
- If only a brand is clearly present, return the brand with `"product": null`.
- Do not output duplicate pairs.
- Do not output both a full product name and one of its partial substrings unless both are independently mentioned as products.

Examples:
- Item: "宝马 X5"
  Output: {"item_index": 0, "pairs": [{"brand": "宝马", "product": "X5"}]}
- Item: "推荐丰田 RAV4，比本田 CR-V 更省油"
  Output: {"item_index": 0, "pairs": [{"brand": "丰田", "product": "RAV4"}, {"brand": "本田", "product": "CR-V"}]}
- Item: "采用 Vibram 大底，防水透气面料"
  Output: {"item_index": 0, "pairs": []}
- Item: "花王 妙而舒 M 64片"
  Output: {"item_index": 0, "pairs": [{"brand": "花王", "product": "妙而舒"}]}
- Item: "推荐 Model Y"
  Output: {"item_index": 0, "pairs": [{"brand": null, "product": "Model Y"}]}

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
