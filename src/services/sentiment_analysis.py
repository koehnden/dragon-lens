import logging
from typing import Optional, Dict, Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

_sentiment_client_instance: Optional["SentimentClient"] = None


def get_sentiment_service() -> "SentimentClient":
    global _sentiment_client_instance
    if _sentiment_client_instance is None:
        _sentiment_client_instance = SentimentClient()
    return _sentiment_client_instance


class SentimentClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.sentiment_service_url
        self._http_client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=30.0)
        return self._http_client

    def classify_sentiment(self, text: str) -> str:
        if not text or not text.strip():
            logger.warning("Empty text provided for sentiment analysis")
            return "neutral"

        try:
            response = self._get_client().post(
                f"{self.base_url}/sentiment",
                json={"text": text},
            )
            response.raise_for_status()
            result = response.json()
            sentiment = result.get("sentiment", "neutral")
            confidence = result.get("confidence", 0.0)
            logger.debug(f"Sentiment: {text[:50]}... -> {sentiment} ({confidence:.3f})")
            return sentiment
        except httpx.ConnectError:
            logger.error(f"Sentiment service unavailable at {self.base_url}")
            return "neutral"
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return "neutral"

    def health_check(self) -> bool:
        try:
            response = self._get_client().get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    def get_model_info(self) -> Dict[str, Any]:
        try:
            response = self._get_client().get(f"{self.base_url}/health")
            if response.status_code == 200:
                return {"status": "remote", **response.json()}
            return {"status": "unavailable"}
        except Exception:
            return {"status": "unavailable"}


class ErlangshenSentimentService:
    def __init__(self, model_name: str = "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment"):
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self.pipeline = None
        self._load_model()

    def _load_model(self) -> None:
        import torch
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            pipeline,
        )

        try:
            logger.info(f"Loading Erlangshen sentiment model: {self.model_name}")
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self.model = self.model.to(torch.device("cpu"))
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.pipeline = pipeline(
                "text-classification",
                model=self.model,
                tokenizer=self.tokenizer,
                device=torch.device("cpu"),
                truncation=True,
                max_length=512,
            )
            logger.info("Erlangshen sentiment model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Erlangshen sentiment model: {e}")
            raise RuntimeError(f"Could not load sentiment model {self.model_name}: {e}")

    def classify_sentiment(self, text: str) -> str:
        if not text or not text.strip():
            logger.warning("Empty text provided for sentiment analysis")
            return "neutral"

        if self.pipeline is None:
            raise RuntimeError("Sentiment analysis pipeline not initialized")

        try:
            results = self.pipeline(text)
            if results and len(results) > 0:
                predicted_label = results[0]['label'].lower()
                confidence = results[0]['score']
                logger.debug(f"Sentiment: {text[:50]}... -> {predicted_label} ({confidence:.3f})")

                if predicted_label in ['positive', 'pos']:
                    return 'positive'
                elif predicted_label in ['negative', 'neg']:
                    return 'negative'
                else:
                    return 'neutral'
            else:
                logger.warning(f"No sentiment results for: {text[:100]}")
                return "neutral"
        except Exception as e:
            logger.error(f"Sentiment analysis failed for '{text[:50]}...': {e}")
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
