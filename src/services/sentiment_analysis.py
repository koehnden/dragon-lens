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
