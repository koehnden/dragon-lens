#!/usr/bin/env python3
"""Benchmark the NER pipeline performance."""

import asyncio
import time
import logging
import os

os.environ.setdefault("ENABLE_QWEN_FILTERING", "true")
os.environ.setdefault("ENABLE_EMBEDDING_CLUSTERING", "false")
os.environ.setdefault("ENABLE_LLM_CLUSTERING", "false")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def benchmark_extract_entities_sync():
    """Benchmark the extract_entities function synchronously."""
    from services.brand_recognition import extract_entities

    test_text = """
    在中国市场，家庭用户对SUV的需求主要集中在空间、舒适性和性价比。
    以下是几款值得推荐的SUV：
    1. 比亚迪宋PLUS DM-i - 插电混动，油耗低
    2. 特斯拉Model Y - 纯电动，智能化高
    3. 大众ID.4 - 德系品质，空间大
    4. 丰田汉兰达 - 可靠性强，保值率高
    5. 理想L7 - 增程式，家庭首选
    这些车型在安全性、舒适性和智能化方面都表现出色。
    """

    brand = "比亚迪"
    aliases = {"zh": ["BYD"], "en": ["BYD"]}

    logger.info("Starting entity extraction benchmark...")
    start = time.perf_counter()

    result = extract_entities(test_text, brand, aliases)

    elapsed = time.perf_counter() - start

    logger.info(f"Extract entities completed in {elapsed:.2f}s")
    logger.info(f"Extracted {len(result)} entities: {list(result.keys())}")

    return elapsed, result


async def benchmark_ollama_calls():
    """Benchmark individual Ollama API calls."""
    from services.ollama import OllamaService

    ollama = OllamaService()
    timings = {}

    prompt_zh = "推荐几款适合家庭的SUV汽车"

    # 1. Query main model
    logger.info("Step 1: Querying main model...")
    start = time.perf_counter()
    response, _, _ = await ollama.query_main_model(prompt_zh)
    timings['query_model'] = time.perf_counter() - start
    logger.info(f"  -> {timings['query_model']:.2f}s (response length: {len(response)} chars)")

    # 2. Translate to English
    logger.info("Step 2: Translating to English...")
    start = time.perf_counter()
    await ollama.translate_to_english(response[:500])
    timings['translate'] = time.perf_counter() - start
    logger.info(f"  -> {timings['translate']:.2f}s")

    # 3. Multiple sentiment calls (simulating per-entity sentiment)
    logger.info("Step 3: 5x Sentiment classification...")
    start = time.perf_counter()
    for i in range(5):
        await ollama.classify_sentiment(f"比亚迪宋PLUS是一款好车")
    timings['sentiment_5x'] = time.perf_counter() - start
    logger.info(f"  -> {timings['sentiment_5x']:.2f}s ({timings['sentiment_5x']/5:.2f}s each)")

    return timings, response


def benchmark_full_pipeline_sync():
    """Benchmark full pipeline in sync context."""
    from services.brand_recognition import extract_entities

    async def run_ollama():
        return await benchmark_ollama_calls()

    # Run Ollama parts
    timings, response = asyncio.run(run_ollama())

    # Run entity extraction (sync)
    brand = "比亚迪"
    aliases = {"zh": ["BYD"], "en": ["BYD"]}

    logger.info("Step 4: Entity extraction with Qwen filtering...")
    start = time.perf_counter()
    entities = extract_entities(response, brand, aliases)
    timings['extract_entities'] = time.perf_counter() - start
    logger.info(f"  -> {timings['extract_entities']:.2f}s")
    logger.info(f"  -> Extracted {len(entities)} entities")

    total = sum(timings.values())

    logger.info("\n" + "=" * 50)
    logger.info("BENCHMARK RESULTS")
    logger.info("=" * 50)
    for step, duration in timings.items():
        pct = 100 * duration / total
        logger.info(f"{step:20s}: {duration:6.2f}s ({pct:5.1f}%)")
    logger.info("-" * 50)
    logger.info(f"{'TOTAL':20s}: {total:6.2f}s")
    logger.info(f"\nExtracted entities: {list(entities.keys())}")

    return timings


if __name__ == "__main__":
    print("=" * 60)
    print("PIPELINE BENCHMARK")
    print("=" * 60)
    benchmark_full_pipeline_sync()
