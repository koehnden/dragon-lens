# Extraction Improvements

## Goal
Improve the current brand/product extraction performance. 
- The extraction must work for any arbitrary vertical. Hardcoding rule and vertical specific fixes are useless!
- Performance is measure by Precision, Recall and F-Beta score (beta=0.5)
- Precision is more important than recall
- We aim for at least 70% recall and 90% precision!
- The pipeline is slow already. We should not make it much slower and ideally speed it up.

## Evaluation
- we use `scripts/benchmark_extraction.py` to evaluate the extraction using the gold data set `data/gold_pairs_chatgpt.csv`

## Current Issues
- Recall way too low around 50% 
- Precision also to low around 70%
- Materials/Technologies are often confused with products, e.g. GORTEX
- DeepSeek is often unreliable, we are using now the big Qwen-3.5 via Openrouter for consolidation as default 

## Improvement ideas
- focus on getting high recall in the main extraction phase and evaluate brands and product for high precision in the consulidation step
- use a more capable remote model instead of Qwen-2.5-7b, e.g. DeepSeek. More capable model needs to be cheap!
- tweaking consolidation prompt
- Addition extraction steps for higher recall, e.g. NER model as first step or extracting all strings with Latin alphabeth (the input is in Chinese)
- Additional consolidation step for higher precision

## Things we already tried
- tweaking the main extraction prompt `src/prompts/extraction/qwen_item_extraction.md`
- adding negative example to `src/prompts/extraction/qwen_item_extraction.md` with seeding results (materials/technologies)