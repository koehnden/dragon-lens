from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class VerticalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class VerticalResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class BrandCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    aliases: Dict[str, List[str]] = Field(
        default_factory=lambda: {"zh": [], "en": []},
        description="Brand aliases in different languages",
    )


class BrandResponse(BaseModel):
    id: int
    vertical_id: int
    display_name: str
    aliases: Dict[str, List[str]]
    created_at: datetime

    model_config = {"from_attributes": True}


class PromptCreate(BaseModel):
    text_en: Optional[str] = None
    text_zh: Optional[str] = None
    language_original: str = Field(..., pattern="^(en|zh)$")


class PromptResponse(BaseModel):
    id: int
    vertical_id: int
    text_en: Optional[str]
    text_zh: Optional[str]
    language_original: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TrackingJobCreate(BaseModel):
    vertical_name: str = Field(..., min_length=1)
    vertical_description: Optional[str] = None
    brands: List[BrandCreate]
    prompts: List[PromptCreate]
    model_name: str = Field(default="qwen", description="Model to use (qwen, deepseek, kimi)")


class TrackingJobResponse(BaseModel):
    run_id: int
    vertical_id: int
    model_name: str
    status: str
    message: str


class BrandMetrics(BaseModel):
    brand_id: int
    brand_name: str
    mention_rate: float
    avg_rank: Optional[float]
    sentiment_positive: float
    sentiment_neutral: float
    sentiment_negative: float


class MetricsResponse(BaseModel):
    vertical_id: int
    vertical_name: str
    model_name: str
    date: datetime
    brands: List[BrandMetrics]


class RunResponse(BaseModel):
    id: int
    vertical_id: int
    model_name: str
    status: str
    run_time: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]

    model_config = {"from_attributes": True}


class BrandMentionResponse(BaseModel):
    brand_id: int
    brand_name: str
    mentioned: bool
    rank: Optional[int]
    sentiment: str
    evidence_snippets: Dict[str, List[str]]

    model_config = {"from_attributes": True}


class LLMAnswerResponse(BaseModel):
    id: int
    prompt_text_zh: Optional[str]
    prompt_text_en: Optional[str]
    raw_answer_zh: str
    raw_answer_en: Optional[str]
    mentions: List[BrandMentionResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class RunDetailedResponse(BaseModel):
    id: int
    vertical_id: int
    vertical_name: str
    model_name: str
    status: str
    run_time: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    answers: List[LLMAnswerResponse]

    model_config = {"from_attributes": True}
