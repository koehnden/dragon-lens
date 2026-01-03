We need to review the brand extraction as we still have some critical errors. 
Recall seems to be ok, but precision is not good enough. 
One common error category is 

## Off-vertical entities (real brands, but not brands for this category)
Symptom: The model mentions adjacent products/retailers/partners, and your extractor accepts them as “Brand”.

Errors in Diapers Example:
- Aptamil / 爱他美 is infant formula, not diapers.
- Kleenex / 舒洁 is tissue/paper, not diapers. 
- Laurier / 乐而雅 and Kotex / 高洁丝 are feminine hygiene brands, not diapers.
- Mothercare is a baby-products retailer (not a diaper brand)

Errors Hiking shoes Example:
- Dick’s Sporting Goods = retailer.

SUV: (less frequent in this file, but same pattern when it happens)

Fix idea: reintroduce a vertical gate, but at the end of each job run in the consolidation step: 
only accept an extracted “brand” if the evidence snippet contains a category keyword near the mention 
(e.g., diapers: 纸尿裤/尿不湿/拉拉裤/训练裤; hiking: 徒步鞋/登山鞋/hiking shoes; SUV: SUV/中型SUV/紧凑型SUV).


## Bad EN ↔ ZH translation
Symptom: The English label and Chinese label don’t match the same brand.
Diapers (big one):
- Pampers’ Chinese name is 帮宝适.
- Huggies’ Chinese name is 好奇 (Kimberly-Clark China uses 好奇®HUGGIES®).
- The extraction currently has “Huggies (帮宝适)” and “Curiosity (好奇)” — that’s a mapping failure (and “Curiosity” is an odd translation choice; you want “Huggies / 好奇”).

SUV:
- “Modern (现代)” should be Hyundai (现代). 
- “Beyke (别克)” should be Buick (别克).
- “Qize (极氪)” should be ZEEKR (极氪).

Fix idea: maintain a small canonical alias dictionary per vertical (or global) for the top 200 entities you expect, and run a post-pass:
(en, zh) must match a known alias pair; otherwise mark needs_review.

## Alias duplication / near-duplicates (inflates competitors and splits SoV)
Symptom: Same brand appears multiple times under slight variants.
Examples I saw:

### Diapers:
- Babycare vs Baby Care
- Goon vs Goo.n
- Unicharm (尤妮佳) vs Unicharm
- Curiosity (好奇) vs Curiosity (好奇心) (plus the bigger issue that it should be Huggies/好奇)

### SUV: 
- multiple repeated 0% rows for the same strings (Cadillac, Ford Motor Company of Canada), plus standalone “VW” even though Volkswagen (大众) is already present.

Fix ideas: canonicalize before scoring:
- nomalize brand text for deduplication: strip punctuation + whitespace + parenthetical text, lower-case latin,
- prefer using shorter name for merging (avoid things like "Ford Motor Company of Canada")
- check of substrings in a longer brand string -> finding "Ford" in "Ford Motor Company of Canada"/
- compute embeddings for brands and re-check merging brand with high cosine similarity -> "VW" and "Volkswagen" 

Contraints:
- The brand and product extraction need to work for any arbitrary brand. We are just using the car vertical as an example. DO NOT HARDCODE ANY RULES. THEY ARE USELESS!
- Everything need to work locally using a MacBook Pro M1 16GB. So a much bigger model than Qwen 7b might not fit our requirements 
- Every filtering brand fix should happen after a job has finished in the consolidation step. We want to maximize recall when running the extraction within runs and maximize the precision at the end of the job in the consolidation step


Can you have a look at the current code and brand extraction logic and evaluate a fix. Do not code anything yet. 
Let's brainstorm a fix instead! 