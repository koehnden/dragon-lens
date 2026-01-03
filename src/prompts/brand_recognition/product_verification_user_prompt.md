---
id: product_verification_user_prompt
version: v1
description: User prompt for product verification with candidates
requires:
  - vertical
  - text
  - candidates_json
---
Industry: {{ vertical or 'General' }}
{% if vertical_description %}
Description: {{ vertical_description }}
{% endif %}

Source text for context:
{{ text }}

Candidates to evaluate:
{{ candidates_json }}

For EACH candidate above, determine if it is a PRODUCT (specific model/item).
Output JSON array only:
