---
id: product_validation_user_prompt
version: v1
description: User prompt for product validation with candidates
requires:
  - products_json
  - text
---
Source text for context:
{{ text }}

Product candidates to validate:
{{ products_json }}

For EACH candidate, determine if it is a genuine PRODUCT.
- ACCEPT: Specific product models (RAV4, Model Y, iPhone 15)
- REJECT: Brands, categories, features, descriptors

Output JSON with "valid" and "invalid" arrays only:
