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
    original_name: str
    translated_name: Optional[str]
    aliases: Dict[str, List[str]]
    is_user_input: bool
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
    provider: str = Field(default="qwen", description="LLM provider (qwen, deepseek, kimi)")
    model_name: str = Field(default="qwen2.5:7b-instruct-q4_0", description="Specific model name (e.g., deepseek-chat, deepseek-reasoner)")


class TrackingJobResponse(BaseModel):
    run_id: int
    vertical_id: int
    provider: str
    model_name: str
    status: str
    message: str


class BrandMetrics(BaseModel):
    brand_id: int
    brand_name: str
    mention_rate: float
    share_of_voice: float
    top_spot_share: float
    sentiment_index: float
    dragon_lens_visibility: float


class ProductMetrics(BaseModel):
    product_id: int
    product_name: str
    brand_id: Optional[int]
    brand_name: str
    mention_rate: float
    share_of_voice: float
    top_spot_share: float
    sentiment_index: float
    dragon_lens_visibility: float


class MetricsResponse(BaseModel):
    vertical_id: int
    vertical_name: str
    model_name: str
    date: datetime
    brands: List[BrandMetrics]


class ProductMetricsResponse(BaseModel):
    vertical_id: int
    vertical_name: str
    model_name: str
    date: datetime
    products: List[ProductMetrics]


class RunResponse(BaseModel):
    id: int
    vertical_id: int
    provider: str
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
    provider: str
    model_name: str
    raw_answer_zh: str
    raw_answer_en: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    latency: Optional[float]
    cost_estimate: Optional[float]
    mentions: List[BrandMentionResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class RunDetailedResponse(BaseModel):
    id: int
    vertical_id: int
    vertical_name: str
    provider: str
    model_name: str
    status: str
    run_time: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    answers: List[LLMAnswerResponse]

    model_config = {"from_attributes": True}


class RunMetricsResponse(BaseModel):
    brand_id: int
    brand_name: str
    is_user_input: bool
    top_spot_share: float
    sentiment_index: float
    mention_rate: float
    share_of_voice: float
    dragon_lens_visibility: float

    model_config = {"from_attributes": True}


class AllRunMetricsResponse(BaseModel):
    run_id: int
    vertical_id: int
    vertical_name: str
    provider: str
    model_name: str
    run_time: datetime
    metrics: List[RunMetricsResponse]

    model_config = {"from_attributes": True}


class DeleteVerticalResponse(BaseModel):
    vertical_id: int
    deleted: bool
    deleted_runs_count: int
    message: str


class APIKeyCreate(BaseModel):
    provider: str = Field(..., description="LLM provider (deepseek, kimi)")
    api_key: str = Field(..., min_length=1, description="API key to encrypt and store")


class APIKeyUpdate(BaseModel):
    api_key: Optional[str] = Field(None, min_length=1, description="New API key (optional)")
    is_active: Optional[bool] = Field(None, description="Active status")


class APIKeyResponse(BaseModel):
    id: int
    provider: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeleteJobsResponse(BaseModel):
    deleted_count: int
    vertical_ids: List[int]
