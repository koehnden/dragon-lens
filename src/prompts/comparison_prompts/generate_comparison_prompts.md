---
version: v1
requires: [context_json, requested_count]
---

你将为一个“品牌/产品对比情绪分析”任务生成对比型用户提问（comparison prompts）。

输入上下文（JSON）如下，请勿修改其内容：
{{ context_json }}

请生成 {{ requested_count }} 条 prompts，并严格输出一个 JSON 数组，数组元素是对象，字段如下：
- text_zh: 中文 prompt（必须为中文）
- text_en: 英文 prompt（必须为英文）
- prompt_type: "brand_vs_brand" 或 "product_vs_product"
- primary_brand: 主品牌名称（字符串）
- competitor_brand: 竞品品牌名称（字符串）
- primary_product: 主产品名称（字符串，可为空）
- competitor_product: 竞品产品名称（字符串，可为空）
- aspects: 需要比较的维度列表（数组，可为空）

硬性规则：
1) 只输出 JSON 数组，不要输出任何解释、markdown、代码块标记。
2) 每条 prompt 必须明确对比主品牌与竞品（或主产品与竞品产品），且包含“推荐/选择/对比/优缺点/常见投诉”等要求，使模型更可能给出负面与中性信息。
3) 生成的 prompts 需要覆盖不同场景与不同维度（例如：质量、耐用性、性价比、售后、舒适度、可靠性、缺点、适用人群、何时不推荐等）。
4) 使用输入中的 user_prompts 作为风格参考，但不要复用同一条 prompt 的同一组维度组合，尽量变化维度与场景。
5) 如果上下文中提供了 user_competitor_brands 与 min_prompts_per_user_competitor，请确保每个 user_competitor_brands 至少出现 min_prompts_per_user_competitor 次（prompt_type 允许混合）。
6) 若上下文中某个竞品没有可用产品列表，则不要为其生成 product_vs_product（只生成 brand_vs_brand）。
