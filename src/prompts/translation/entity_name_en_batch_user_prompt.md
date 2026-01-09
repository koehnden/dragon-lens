---
id: entity_name_en_batch_user_prompt
version: v1
description: User prompt for batch translating brand/product names to English with vertical context
requires:
  - vertical_name
  - vertical_description
  - items_json
---
Vertical: {{ vertical_name }}
Vertical description: {{ vertical_description }}

Input JSON array (each item has keys: type, name):
{{ items_json }}

Return a JSON array of the same length and order, where each item has keys: type, name, english.

