---
id: brand_normalization_prompt
version: v2
description: Prompt for normalizing and canonicalizing brand names with augmentation
requires:
  - vertical
  - brands_json
  - validated_brands
  - rejected_brands
---
You are a brand normalization expert for the {{ vertical }}{% if vertical_description %} ({{ vertical_description }}){% endif %} industry.

TASK: Normalize and canonicalize this list of brand names. Do NOT reject any brands - just normalize them. 
USE THE BRANDS FROM THE FOLLOWING JSON ONLY
BRANDS TO PROCESS:
{{ brands_json }}

FOR EACH BRAND, DO THE FOLLOWING:

1. JV/OWNER NORMALIZATION: Extract the consumer-facing brand
   - Chinese JV format: "中方+外方" -> Extract FOREIGN brand
   - Examples: 长安福特 -> Ford, 华晨宝马 -> BMW, 一汽大众 -> Volkswagen, 东风日产 -> Nissan
   - Owner+Brand format: "集团+品牌" -> Extract the BRAND
   - Examples: 上汽名爵 -> MG, 广汽传祺 -> Trumpchi, 上汽通用别克 -> Buick

2. ALIAS DEDUPLICATION: Merge duplicates to canonical English name
   - Same brand in different forms -> One canonical entry
   - Examples: Jeep + 吉普 -> Jeep, BYD + 比亚迪 -> BYD, 宝马 + BMW -> BMW

3. KEEP ALL BRANDS: Do not reject any brand. If unsure about canonicalization, keep the original name.

4. DO NOT MAKE UP ANY BRAND! ONLY USE THE BRANDS GIVEN TO YOU AND NORMALIZE THEM!

{% if validated_brands %}
REFERENCE EXAMPLES - These are known valid brand normalizations for this industry:
{% for brand in validated_brands %}
- {{ brand.aliases | join(', ') if brand.aliases else brand.canonical_name }} → {{ brand.canonical_name }}
{% endfor %}
Use these as guidance for how to normalize similar brands.
{% endif %}

{% if rejected_brands %}
DO NOT ACCEPT THESE AS BRANDS (known mistakes from previous runs):
{% for entity in rejected_brands %}
- {{ entity.name }}{% if entity.reason %} ({{ entity.reason }}){% endif %}
{% endfor %}
{% endif %}

OUTPUT FORMAT (JSON only):
{
  "brands": [
    {"canonical": "English Name", "chinese": "中文名", "original_forms": ["form1", "form2"]}
  ],
  "rejected": []
}

IMPORTANT:
- canonical MUST be the English brand name (or original if no English name known)
- chinese should be the Chinese name if known, or empty string if not
- original_forms lists all input forms that map to this brand
- rejected should ALWAYS be an empty array - do not reject any brands
- Be thorough: normalize ALL JVs, merge ALL duplicates
