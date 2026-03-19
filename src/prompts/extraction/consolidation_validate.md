---
id: consolidation_validate
version: v2
requires:
  - vertical
  - brands_json
  - products_json
---
You are a strict validator for extracted brands and products in the {{ vertical }} industry.

Vertical description: {{ vertical_description }}

For each candidate, classify it into exactly one category:
- **consumer_brand**: A company that sells finished end products to consumers in this vertical.
- **consumer_product**: A specific end product or product line that consumers buy in this vertical.
- **material_or_technology**: A raw material, fabric, chemical compound, technology, or technical standard (e.g., GORE-TEX, Vibram, NFC, OLED, Lycra, Cordura).
- **component_or_supplier**: A company that makes parts, components, or materials used inside end products but does not sell the end product itself.
- **generic_category**: A category name, product type, or descriptive phrase rather than a specific brand or product (e.g., SUV, 纸尿裤, running shoes).
- **attribute_or_feature**: An adjective, benefit claim, specification, size, color, edition, or configuration token (e.g., "breathable", "soft", "lightweight", "waterproof", "suitable", "comfortable").
- **common_word**: A common vocabulary word (noun, verb, adjective, adverb) that is not a proper noun or named entity (e.g., "design", "value", "use", "fit", "skin", "babies", "long", "one", "without", "after").
- **retailer_or_channel**: A store, marketplace, or sales channel rather than a product brand.
- **misclassified_type**: A brand appearing in the products list or a product appearing in the brands list.
- **off_vertical**: A real brand or product, but not relevant to this vertical.

{% if known_brands or known_products %}
PREVIOUSLY VALIDATED ENTITIES FOR THIS VERTICAL (use as calibration):
{% if known_brands %}
Known brands: {{ known_brands | join(', ') }}
{% endif %}
{% if known_products %}
Known products: {{ known_products | join(', ') }}
{% endif %}
{% endif %}

{% if known_rejected %}
PREVIOUSLY REJECTED ENTITIES:
{% for item in known_rejected %}
- {{ item.name }} — {{ item.reason }}
{% endfor %}
{% endif %}

CANDIDATES TO VALIDATE:

Brands:
{{ brands_json }}

Products:
{{ products_json }}

Return JSON only with this shape:
{
  "valid_brands": ["Volkswagen", "BYD"],
  "valid_products": ["RAV4荣放", "宋PLUS DM-i"],
  "rejected": [
    {"name": "SUV", "entity_type": "product", "category": "generic_category", "reason": "generic vehicle category, not a product"},
    {"name": "GORE-TEX", "entity_type": "brand", "category": "material_or_technology", "reason": "waterproof membrane technology, not a consumer brand"},
    {"name": "比亚迪", "entity_type": "product", "category": "misclassified_type", "reason": "this is a brand, not a product"}
  ]
}

Rules:
- Classify every candidate. Place it in valid_brands/valid_products only if it is a consumer_brand or consumer_product respectively.
- Reject everything that is not a consumer-facing brand or consumer-facing end product for this vertical.
- Brands and products are always proper nouns — named companies and named products. Common vocabulary words (nouns, verbs, adjectives, adverbs, prepositions) are never brands or products. Reject them as common_word.
- Materials, technologies, fabrics, and technical standards are never consumer brands or products — always reject them.
- Component suppliers and ingredient suppliers are not consumer brands — reject them.
- Generic categories and product types are not products — reject them.
- If a brand appears in the products list or vice versa, reject it as misclassified_type.
- When in doubt about whether something is a material/technology or a consumer brand, reject it.
- Use the previously validated entities as calibration for what belongs in this vertical.
- Include a reason for every rejection.
