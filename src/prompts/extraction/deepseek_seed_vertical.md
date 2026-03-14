You are a market research expert for the Chinese consumer market.

For the following industry vertical:
Vertical: {{ vertical }}
Description: {{ vertical_description }}

List the top 30-50 brands and their key products that a Chinese consumer
would likely encounter or ask about in this vertical.

IMPORTANT:
- Include BOTH Chinese names (name_zh) and English names (name_en)
- Include Chinese aliases: JV names (e.g. 一汽丰田, 广汽丰田), colloquial names, etc.
- Include product aliases: Chinese names (e.g. 凯美瑞 for Camry), model variants
- Focus on brands/products that appear in Chinese LLM responses
- Cover mainstream, premium, and budget segments

OUTPUT (JSON only, no other text):
{
  "brands": [
    {
      "name_en": "Toyota",
      "name_zh": "丰田",
      "aliases": ["一汽丰田", "广汽丰田", "TOYOTA"],
      "products": [
        {"name": "RAV4", "aliases": ["RAV4荣放", "荣放"]},
        {"name": "Camry", "aliases": ["凯美瑞"]},
        {"name": "Highlander", "aliases": ["汉兰达"]}
      ]
    }
  ]
}
