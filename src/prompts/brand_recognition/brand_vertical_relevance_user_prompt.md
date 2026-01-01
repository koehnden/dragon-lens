---
id: brand_vertical_relevance_user_prompt
version: v1
description: User prompt for brand vertical relevance classification (batch)
requires:
  - candidates_json
---
Evaluate relevance for each candidate brand using the evidence pairs.

CANDIDATES (JSON):
{{ candidates_json }}

Return JSON only.
