---
id: entity_name_en_batch_retry_user_prompt
version: v1
description: Retry user prompt for batch translating brand/product names to English when first attempt fails
requires:
  - vertical_name
  - vertical_description
  - items_json
  - override_examples_json
---
Vertical: {{ vertical_name }}
Vertical description: {{ vertical_description }}

{% if override_examples_json %}
Known translation corrections from previous feedback (JSON array items have canonical_name, override_text, reason, vertical_name, same_vertical):
{{ override_examples_json }}
If same_vertical is false, the example is from a different vertical and should be treated as a weak hint.
{% endif %}

Input JSON array (each item has keys: type, name):
{{ items_json }}

Return ONLY a JSON array of the same length and order, where each item has keys: type, name, english.
