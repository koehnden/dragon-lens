---
id: entity_name_en_batch_retry_user_prompt
version: v1
description: Retry user prompt for batch translating brand/product names to English when first attempt fails
requires:
  - vertical_name
  - vertical_description
  - items_json
---
Vertical: {{ vertical_name }}
Vertical description: {{ vertical_description }}

Input JSON array (each item has keys: type, name):
{{ items_json }}

Return ONLY a JSON array of the same length and order, where each item has keys: type, name, english.

