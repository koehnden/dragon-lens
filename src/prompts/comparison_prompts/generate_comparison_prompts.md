---
version: v1
requires: [context_json, requested_count]
---

You generate comparison-style user questions for a “brand/product comparison sentiment analysis” task.

The input context (JSON) is below (do not modify it):
{{ context_json }}

Generate {{ requested_count }} prompts and output a JSON array only. Each element is an object with:
- text_zh: Chinese prompt (Chinese only)
- text_en: English prompt (English only)
- prompt_type: "brand_vs_brand" or "product_vs_product"
- primary_brand: primary brand name (string)
- competitor_brand: competitor brand name (string)
- primary_product: primary product name (string, can be empty)
- competitor_product: competitor product name (string, can be empty)
- aspects: a list of characteristics to compare (array, can be empty)

Hard rules:
1) Output JSON array only. No explanation, no markdown, no code fences.
2) Each prompt must explicitly compare the primary vs competitor (brand or product), and include guidance like “recommend/choose/compare/pros&cons/common complaints” to increase neutral/negative coverage.
3) Prompts should cover different scenarios and characteristics (e.g., quality, durability, value, after-sales service, comfort, reliability, drawbacks, target users, when not recommended).
4) Use user_prompts as style inspiration, but avoid reusing the exact same characteristic combination; vary aspects and scenarios.
5) If user_competitor_brands and min_prompts_per_user_competitor are provided, ensure each user competitor appears at least that many times (prompt_type can be mixed).
6) If a competitor has no available product list in the context, do not generate product_vs_product for it (generate brand_vs_brand only).
