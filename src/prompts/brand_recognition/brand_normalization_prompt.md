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
You are a brand normalization expert for the {{ vertical }}{% if vertical_description %} ({{ vertical_description }}){% endif %} industry in China.

TASK: Normalize and canonicalize this list of brand names. Do NOT reject any brands - just normalize them.
USE THE BRANDS FROM THE FOLLOWING JSON ONLY
BRANDS TO PROCESS:
{{ brands_json }}

FOR EACH BRAND, DO THE FOLLOWING:

1. JV/OWNER NORMALIZATION: Extract the consumer-facing brand (do NOT translate meaning)
   - Chinese JV format: "中方+外方" -> Extract the consumer-facing brand part WITHOUT inventing a new English label
   - Examples: 长安福特 -> 福特, 华晨宝马 -> 宝马, 一汽大众 -> 大众, 东风日产 -> 日产
   - Owner+Brand format: "集团+品牌" -> Extract the brand part
   - Examples: 上汽名爵 -> 名爵, 广汽传祺 -> 传祺, 上汽通用别克 -> 别克

2. ALIAS DEDUPLICATION: Merge duplicates to ONE canonical label (choose from the provided strings)
   - If BOTH Chinese and English forms exist in the provided list, prefer the English form as canonical.
   - If only Chinese forms exist, keep Chinese as canonical (do NOT translate).
   - If only English forms exist, keep English as canonical.
   - Examples:
     - Huggies + 好奇 -> Huggies
     - BMW + 宝马 -> BMW
     - 好奇 (only) -> 好奇 (NOT "Curiosity")
     - 妙而舒 (only) -> 妙而舒 (NOT pinyin)

3. KEEP ALL BRANDS: Do not reject any brand. If unsure about canonicalization, keep the original name.

4. DO NOT MAKE UP ANY BRAND! ONLY USE THE BRANDS GIVEN TO YOU AND NORMALIZE THEM!
5. DO NOT TRANSLATE MEANING: Never translate Chinese words into English meanings (e.g., 好奇 -> Curiosity is WRONG).
6. DO NOT ROMANIZE: Never output pinyin or invented Latin spellings for Chinese brands (e.g., 妙而舒 -> Moyi Shu is WRONG).
7. CANONICAL OUTPUT MUST BE TRACEABLE: The "canonical" field MUST be one of:
   - an input brand string from BRANDS TO PROCESS, OR
   - a substring extracted from an input brand string (e.g., "一汽大众" -> "大众"), OR
   - a canonical_name from the reference examples below (if provided).

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
    {"canonical": "Canonical Label", "chinese": "中文名", "original_forms": ["form1", "form2"]}
  ],
  "rejected": []
}

IMPORTANT:
- canonical MUST be a canonical label chosen using the rules above (do not invent)
- chinese should be the Chinese name if known, or empty string if not
- original_forms lists all input forms that map to this brand
- rejected should ALWAYS be an empty array - do not reject any brands
- Be thorough: normalize ALL JVs, merge ALL duplicates
