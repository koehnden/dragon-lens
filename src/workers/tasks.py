import asyncio
import logging
from datetime import datetime
from typing import List

from celery import Task
from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandMention,
    LLMAnswer,
    Prompt,
    Run,
    Vertical,
)
from models.database import SessionLocal
from models.domain import EntityType, PromptLanguage, RunStatus, Sentiment
from services.brand_discovery import (
    EntityTarget,
    build_entity_targets,
    discover_all_brands,
)
from services.brand_recognition import extract_entities
from services.translater import TranslaterService
from services.metrics_service import calculate_and_save_metrics
from services.ollama import OllamaService
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    _db: Session | None = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


def _target_alias(target: EntityTarget, brands: dict[int, Brand]) -> list[str]:
    if target.entity_type != EntityType.BRAND:
        return []
    brand = brands.get(target.brand_id)
    if not brand:
        return []
    return brand.aliases.get("zh", []) + brand.aliases.get("en", [])


def _prepare_targets(
    brands: list[Brand], products: list
) -> tuple[list[str], list[list[str]], list[EntityTarget]]:
    targets = build_entity_targets(brands, products)
    lookup = {brand.id: brand for brand in brands}
    names = [target.name for target in targets]
    aliases = [_target_alias(target, lookup) for target in targets]
    return names, aliases, targets


@celery_app.task(base=DatabaseTask, bind=True)
def run_vertical_analysis(self: DatabaseTask, vertical_id: int, model_name: str, run_id: int):
    logger.info(f"Starting vertical analysis: vertical={vertical_id}, model={model_name}, run={run_id}")

    try:
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise ValueError(f"Run {run_id} not found")

        run.status = RunStatus.IN_PROGRESS
        self.db.commit()

        vertical = self.db.query(Vertical).filter(Vertical.id == vertical_id).first()
        if not vertical:
            raise ValueError(f"Vertical {vertical_id} not found")

        prompts = self.db.query(Prompt).filter(Prompt.vertical_id == vertical_id).all()
        if not prompts:
            raise ValueError(f"No prompts found for vertical {vertical_id}")

        brands = self.db.query(Brand).filter(Brand.vertical_id == vertical_id).all()
        if not brands:
            raise ValueError(f"No brands found for vertical {vertical_id}")

        ollama_service = OllamaService()
        translator = TranslaterService(ollama_service)
        _apply_brand_translations(brands, translator, self.db)

        for prompt in prompts:
            logger.info(f"Processing prompt {prompt.id}")

            prompt_text_zh = prompt.text_zh
            prompt_text_en = prompt.text_en

            if not prompt_text_zh and prompt_text_en:
                logger.info(f"Translating English prompt to Chinese: {prompt_text_en[:50]}...")
                prompt_text_zh = translator.translate_text_sync(prompt_text_en, "English", "Chinese")
                logger.info(f"Translated to Chinese: {prompt_text_zh[:50]}...")

            if not prompt_text_zh:
                logger.warning(f"Prompt {prompt.id} has no text, skipping")
                continue

            logger.info(f"Querying Qwen with prompt: {prompt_text_zh[:100]}...")
            answer_zh, tokens_in, tokens_out = asyncio.run(
                ollama_service.query_main_model(prompt_text_zh)
            )
            logger.info(f"Received answer: {answer_zh[:100]}...")

            answer_en = None
            if answer_zh:
                logger.info("Translating answer to English...")
                answer_en = translator.translate_text_sync(answer_zh, "Chinese", "English")
                logger.info(f"Translated answer: {answer_en[:100]}...")

            llm_answer = LLMAnswer(
                run_id=run_id,
                prompt_id=prompt.id,
                raw_answer_zh=answer_zh,
                raw_answer_en=answer_en,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_estimate=0.0,
            )
            self.db.add(llm_answer)
            self.db.flush()

            logger.info("Discovering all brands in response...")
            entities = discover_all_brands(answer_zh, vertical_id, brands, self.db)
            discovered_count = len(entities.brands) - len(brands)
            logger.info(
                f"Found {len(entities.brands)} brands ({len(brands)} user-input, {discovered_count} discovered)"
            )

            _apply_brand_translations(entities.brands, translator, self.db)
            brand_names, brand_aliases, targets = _prepare_targets(
                entities.brands, entities.products
            )
            brand_lookup = {brand.id: brand for brand in entities.brands}

            logger.info(f"Extracting brand mentions for {len(targets)} entities...")
            mentions = asyncio.run(
                ollama_service.extract_brands(answer_zh, brand_names, brand_aliases)
            )

            for mention_data in mentions:
                if not mention_data["mentioned"]:
                    continue

                target = targets[mention_data["brand_index"]]
                brand = brand_lookup.get(target.brand_id)
                brand_label = brand.display_name if brand else target.name

                sentiment_str = "neutral"
                if mention_data["snippets"]:
                    snippet = mention_data["snippets"][0]
                    sentiment_str = asyncio.run(ollama_service.classify_sentiment(snippet))
                    logger.info(f"Brand {brand_label} sentiment: {sentiment_str}")

                sentiment = Sentiment.POSITIVE if sentiment_str == "positive" else (
                    Sentiment.NEGATIVE if sentiment_str == "negative" else Sentiment.NEUTRAL
                )

                en_snippets = []
                for snippet in mention_data["snippets"]:
                    en_snippet = translator.translate_text_sync(snippet, "Chinese", "English")
                    en_snippets.append(en_snippet)

                mention = BrandMention(
                    llm_answer_id=llm_answer.id,
                    brand_id=target.brand_id,
                    mentioned=True,
                    rank=mention_data["rank"],
                    sentiment=sentiment,
                    evidence_snippets={"zh": mention_data["snippets"], "en": en_snippets},
                )
                self.db.add(mention)

            self.db.commit()

        logger.info(f"Calculating metrics for run {run_id}...")
        calculate_and_save_metrics(self.db, run_id)
        logger.info(f"Metrics calculated and saved for run {run_id}")

        run.status = RunStatus.COMPLETED
        run.completed_at = datetime.utcnow()
        self.db.commit()

        logger.info(f"Completed vertical analysis: run={run_id}")

    except Exception as e:
        logger.error(f"Error in vertical analysis: {e}", exc_info=True)

        run = self.db.query(Run).filter(Run.id == run_id).first()
        if run:
            run.status = RunStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            self.db.commit()

        raise


@celery_app.task
def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    logger.info(f"Translating from {source_lang} to {target_lang}")
    return f"[TODO: Translation of: {text}]"


@celery_app.task
def extract_brand_mentions(answer_text: str, brands: List[dict]) -> List[dict]:
    logger.info("Extracting brand mentions")
    if not brands:
        return []
    primary = brands[0]
    aliases = primary.get("aliases") or {"zh": [], "en": []}
    canonical = extract_entities(answer_text, primary.get("display_name", ""), aliases)
    mentions = []
    for name, surfaces in canonical.items():
        mentions.append({"canonical": name, "mentions": surfaces})
    return mentions


@celery_app.task
def classify_sentiment(text: str) -> str:
    logger.info("Classifying sentiment")
    return "neutral"


def _apply_brand_translations(brands: List[Brand], translator: TranslaterService, db: Session) -> None:
    updated = False
    for brand in brands:
        if brand.translated_name:
            continue
        brand.original_name = brand.display_name
        brand.translated_name = translator.translate_entity_sync(brand.display_name)
        updated = True
    if updated:
        db.commit()


def _detect_mentions(answer_text: str, brands: List[Brand]) -> dict[int, List[str]]:
    if not brands:
        return {}
    primary = brands[0]
    canonical = extract_entities(answer_text, primary.display_name, primary.aliases)
    mention_map: dict[int, List[str]] = {}
    for canonical_name, surfaces in canonical.items():
        brand = _ensure_brand(primary.vertical_id, canonical_name, primary.aliases)
        mention_map[brand.id] = surfaces
    return mention_map


def _ensure_brand(vertical_id: int, canonical_name: str, aliases: dict) -> Brand:
    session = SessionLocal()
    brand = session.query(Brand).filter(Brand.vertical_id == vertical_id, Brand.display_name == canonical_name).first()
    brand = brand or Brand(
        vertical_id=vertical_id,
        display_name=canonical_name,
        original_name=canonical_name,
        translated_name=None,
        aliases=aliases or {"zh": [], "en": []},
    )
    if brand.id is None:
        session.add(brand)
        session.commit()
        session.refresh(brand)
    session.close()
    return brand
