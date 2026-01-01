---
id: brand_verification_user_prompt
version: v1
description: User prompt for brand verification with candidates
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

For EACH candidate above, determine if it is a BRAND (company/manufacturer) selling in the Chinese market.
Output JSON array only:
