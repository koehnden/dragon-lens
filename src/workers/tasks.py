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
from models.domain import PromptLanguage, RunStatus, Sentiment
from services.brand_recognition import extract_entities
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

        for prompt in prompts:
            logger.info(f"Processing prompt {prompt.id}")

            prompt_text_zh = prompt.text_zh or prompt.text_en
            if not prompt_text_zh:
                logger.warning(f"Prompt {prompt.id} has no text, skipping")
                continue

            answer_zh = "[TODO: LLM answer will be here]"
            tokens_in = 0
            tokens_out = 0

            llm_answer = LLMAnswer(
                run_id=run_id,
                prompt_id=prompt.id,
                raw_answer_zh=answer_zh,
                raw_answer_en=None,  # TODO: translate
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_estimate=0.0,
            )
            self.db.add(llm_answer)
            self.db.flush()

            canonical_mentions = _detect_mentions(answer_zh, brands)
            for brand_id, snippets in canonical_mentions.items():
                mention = BrandMention(
                    llm_answer_id=llm_answer.id,
                    brand_id=brand_id,
                    mentioned=True,
                    rank=None,
                    sentiment=Sentiment.NEUTRAL,
                    evidence_snippets={"zh": snippets, "en": []},
                )
                self.db.add(mention)

            self.db.commit()

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
    brand = brand or Brand(vertical_id=vertical_id, display_name=canonical_name, aliases=aliases or {"zh": [], "en": []})
    if brand.id is None:
        session.add(brand)
        session.commit()
        session.refresh(brand)
    session.close()
    return brand
