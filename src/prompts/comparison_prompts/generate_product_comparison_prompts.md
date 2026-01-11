---
version: v1
requires: [pairs_json]
---

You generate “product vs product” user questions for a Chinese LLM sentiment comparison task.

The input is a JSON array (do not modify it). Each element contains:
- primary_brand
- primary_product
- competitor_brand
- competitor_product
- aspect_zh

Input:
{{ pairs_json }}

Output must be a JSON array with the exact same length as the input.
Each array element is an object with:
- text_zh: a Chinese question (Chinese only)

Hard rules:
1) Output JSON array only. No explanation, no markdown, no code fences.
2) Each text_zh must include the full names of both primary_product and competitor_product.
3) Each text_zh must explicitly compare the characteristic in aspect_zh and encourage an answer that includes pros/cons, common issues, or “when not recommended”.
4) Each text_zh must be Chinese only.
