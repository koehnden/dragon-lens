import logging
from typing import Optional, Dict, Any
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

logger = logging.getLogger(__name__)

_sentiment_service_instance: Optional["ErlangshenSentimentService"] = None


def get_sentiment_service() -> "ErlangshenSentimentService":
    global _sentiment_service_instance
    if _sentiment_service_instance is None:
        _sentiment_service_instance = ErlangshenSentimentService()
    return _sentiment_service_instance

class ErlangshenSentimentService:
    def __init__(self, model_name: str = "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment"):
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self.pipeline = None
        self._load_model()

    def _load_model(self) -> None:
        try:
            logger.info(f"Loading Erlangshen sentiment model: {self.model_name}")
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self.model = self.model.to(torch.device("cpu"))
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.pipeline = pipeline(
                "text-classification",
                model=self.model,
                tokenizer=self.tokenizer,
                device=torch.device("cpu")
            )
            logger.info("Erlangshen sentiment model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Erlangshen sentiment model: {e}")
            raise RuntimeError(f"Could not load sentiment model {self.model_name}: {e}")

    def classify_sentiment(self, text: str) -> str:
        if not text or not text.strip():
            logger.warning("Empty text provided for sentiment analysis, returning neutral")
            return "neutral"

        if self.pipeline is None:
            raise RuntimeError("Sentiment analysis pipeline not initialized")

        try:
            results = self.pipeline(text)
            if results and len(results) > 0:
                predicted_label = results[0]['label'].lower()
                confidence = results[0]['score']
                logger.debug(f"Sentiment analysis: text='{text[:50]}...' -> label='{predicted_label}' (confidence={confidence:.3f})")

                if predicted_label in ['positive', 'pos']:
                    return 'positive'
                elif predicted_label in ['negative', 'neg']:
                    return 'negative'
                else:
                    return 'neutral'
            else:
                logger.warning(f"No sentiment analysis results for text: {text[:100]}")
                return "neutral"
        except Exception as e:
            logger.error(f"Sentiment analysis failed for text '{text[:50]}...': {e}")
            return "neutral"

    def get_model_info(self) -> Dict[str, Any]:
        if self.model is None:
            return {"status": "not_loaded"}

        return {
            "status": "loaded",
            "model_name": self.model_name,
            "model_type": self.model.__class__.__name__,
            "has_pipeline": self.pipeline is not None,
            "has_tokenizer": self.tokenizer is not None
        }

    def health_check(self) -> bool:
        try:
            if self.model is None or self.tokenizer is None or self.pipeline is None:
                return False
            test_result = self.classify_sentiment("测试句子")
            return test_result in ["positive", "negative", "neutral"]
        except Exception:
            return False
