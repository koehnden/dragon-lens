---
id: text_translation_user_prompt
version: v1
description: User prompt for translating general text
requires:
  - source_lang
  - target_lang
  - text
---
Translate from {{ source_lang }} to {{ target_lang }}:
{{ text }}
