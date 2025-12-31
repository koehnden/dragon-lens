---
id: extraction_user_prompt
version: v1
description: User prompt for entity extraction containing the text to analyze
requires:
  - text
---
Extract ALL brand names and product names from this text.

TEXT TO ANALYZE:
{{ text }}

Remember:
- Extract COMPLETE entity names (e.g., "Model Y" not just "Y")
- Separate brands from products
- Include parent_brand for products when known
- Output valid JSON only
