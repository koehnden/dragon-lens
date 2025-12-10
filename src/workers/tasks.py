import logging
from datetime import datetime
from typing import List

from celery import Task
from sqlalchemy.orm import Session

from src.models import (
    Brand,
    BrandMention,
    LLMAnswer,
    Prompt,
    Run,
    Vertical,
)
from src.models.database import SessionLocal
from src.models.domain import PromptLanguage, RunStatus, Sentiment
from src.workers.celery_app import celery_app

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

            for brand in brands:
                mention = BrandMention(
                    llm_answer_id=llm_answer.id,
                    brand_id=brand.id,
                    mentioned=False,  # TODO: detect actual mention
                    rank=None,
                    sentiment=Sentiment.NEUTRAL,
                    evidence_snippets={"zh": [], "en": []},
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
    return []


@celery_app.task
def classify_sentiment(text: str) -> str:
    logger.info("Classifying sentiment")
    return "neutral"
