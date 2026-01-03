---
id: product_brand_mapping_prompt
version: v1
description: User prompt for mapping product to brand with guardrails
requires:
  - product
  - candidate_brands
  - evidence_snippets
  - known_mappings
---
You map a product to its brand using evidence only.

Rules:
- Return a brand only if it is in the candidate list
- If unsure, return "unknown"
- Do not invent brands or use outside knowledge

Known mappings for this vertical:
{{ known_mappings }}

Product:
{{ product }}

Candidate brands:
{{ candidate_brands }}

Evidence snippets:
{{ evidence_snippets }}

Return JSON only:
{
  "mappings": [
    {"product": "{{ product }}", "brand": "BrandNameOrUnknown"}
  ]
}
