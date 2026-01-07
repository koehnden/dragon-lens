import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_model = None
_tokenizer = None
_pipeline = None


class SentimentRequest(BaseModel):
    text: str


class SentimentResponse(BaseModel):
    sentiment: str
    confidence: float


def _load_model():
    global _model, _tokenizer, _pipeline
    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        pipeline,
    )

    model_name = "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment"
    logger.info(f"Loading Erlangshen sentiment model: {model_name}")

    _model = AutoModelForSequenceClassification.from_pretrained(model_name)
    _model = _model.to(torch.device("cpu"))
    _tokenizer = AutoTokenizer.from_pretrained(model_name)
    _pipeline = pipeline(
        "text-classification",
        model=_model,
        tokenizer=_tokenizer,
        device=torch.device("cpu"),
        truncation=True,
        max_length=512,
    )
    logger.info("Erlangshen sentiment model loaded successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_model()
    yield
    logger.info("Sentiment service shutting down")


app = FastAPI(
    title="DragonLens Sentiment Service",
    description="Dedicated sentiment analysis microservice using Erlangshen",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "healthy", "model": "Erlangshen-Roberta-110M-Sentiment"}


@app.post("/sentiment", response_model=SentimentResponse)
async def classify_sentiment(request: SentimentRequest):
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    text = request.text
    if not text or not text.strip():
        return SentimentResponse(sentiment="neutral", confidence=0.0)

    try:
        results = _pipeline(text)
        if results and len(results) > 0:
            label = results[0]["label"].lower()
            confidence = results[0]["score"]

            if label in ["positive", "pos"]:
                sentiment = "positive"
            elif label in ["negative", "neg"]:
                sentiment = "negative"
            else:
                sentiment = "neutral"

            return SentimentResponse(sentiment=sentiment, confidence=confidence)

        return SentimentResponse(sentiment="neutral", confidence=0.0)
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8100)
