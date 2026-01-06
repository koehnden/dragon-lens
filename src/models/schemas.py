import enum
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class VerticalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class VerticalResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeVerticalResponse(BaseModel):
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
    brands: List[BrandCreate] = Field(default_factory=list)
    prompts: List[PromptCreate]
    provider: str = Field(default="qwen", description="LLM provider (qwen, deepseek, kimi, openrouter)")
    model_name: str = Field(default="qwen2.5:7b-instruct-q4_0", description="Specific model name or OpenRouter model ID")
    reuse_answers: bool = Field(default=False, description="Whether to reuse answers from previous runs")
    web_search_enabled: bool = Field(default=False, description="Whether web search is enabled for this run")


class TrackingJobResponse(BaseModel):
    run_id: int
    vertical_id: int
    provider: str
    model_name: str
    route: Optional[str] = None
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
    route: Optional[str] = None
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
    route: Optional[str] = None
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
    route: Optional[str] = None
    status: str
    run_time: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    answers: List[LLMAnswerResponse]

    model_config = {"from_attributes": True}


class RunEntityBrand(BaseModel):
    brand_id: int
    brand_name: str
    original_name: str
    translated_name: Optional[str]
    mention_count: int

    model_config = {"from_attributes": True}


class RunEntityProduct(BaseModel):
    product_id: int
    product_name: str
    original_name: str
    translated_name: Optional[str]
    brand_id: Optional[int]
    brand_name: str
    mention_count: int

    model_config = {"from_attributes": True}


class RunEntityMapping(BaseModel):
    product_id: int
    product_name: str
    brand_id: Optional[int]
    brand_name: str
    confidence: float
    source: Optional[str]
    is_validated: bool

    model_config = {"from_attributes": True}


class RunEntitiesResponse(BaseModel):
    run_id: int
    vertical_id: int
    vertical_name: str
    provider: str
    model_name: str
    status: str
    run_time: datetime
    completed_at: Optional[datetime]
    brands: List[RunEntityBrand]
    products: List[RunEntityProduct]
    mappings: List[RunEntityMapping]


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
    provider: str = Field(..., description="LLM provider (deepseek, kimi, openrouter)")
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


class ConsolidationResultResponse(BaseModel):
    brands_merged: int
    products_merged: int
    brands_flagged: int
    products_flagged: int
    canonical_brands_created: int
    canonical_products_created: int


class CanonicalBrandResponse(BaseModel):
    id: int
    vertical_id: int
    canonical_name: str
    display_name: str
    is_validated: bool
    validation_source: Optional[str]
    mention_count: int
    aliases: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CanonicalProductResponse(BaseModel):
    id: int
    vertical_id: int
    canonical_brand_id: Optional[int]
    canonical_name: str
    display_name: str
    is_validated: bool
    validation_source: Optional[str]
    mention_count: int
    aliases: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationCandidateResponse(BaseModel):
    id: int
    vertical_id: int
    entity_type: str
    name: str
    canonical_id: Optional[int]
    mention_count: int
    status: str
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[str]
    rejection_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidateCandidateRequest(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None


class FeedbackAction(str, enum.Enum):
    VALIDATE = "validate"
    REPLACE = "replace"
    REJECT = "reject"


class FeedbackMappingAction(str, enum.Enum):
    ADD = "add"
    REJECT = "reject"


class FeedbackEntityType(str, enum.Enum):
    BRAND = "brand"
    PRODUCT = "product"


class FeedbackLanguage(str, enum.Enum):
    ZH = "zh"
    EN = "en"


class FeedbackCanonicalVertical(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    is_new: bool


class FeedbackBrandFeedbackItem(BaseModel):
    action: FeedbackAction
    name: Optional[str] = None
    wrong_name: Optional[str] = None
    correct_name: Optional[str] = None
    reason: Optional[str] = None


class FeedbackProductFeedbackItem(BaseModel):
    action: FeedbackAction
    name: Optional[str] = None
    wrong_name: Optional[str] = None
    correct_name: Optional[str] = None
    reason: Optional[str] = None


class FeedbackMappingFeedbackItem(BaseModel):
    action: FeedbackMappingAction
    product_name: Optional[str] = None
    brand_name: Optional[str] = None
    reason: Optional[str] = None


class FeedbackTranslationOverrideItem(BaseModel):
    entity_type: FeedbackEntityType
    canonical_name: str
    language: FeedbackLanguage
    override_text: str
    reason: Optional[str] = None


class FeedbackSubmitRequest(BaseModel):
    run_id: int
    vertical_id: int
    canonical_vertical: FeedbackCanonicalVertical
    brand_feedback: List[FeedbackBrandFeedbackItem] = Field(default_factory=list)
    product_feedback: List[FeedbackProductFeedbackItem] = Field(default_factory=list)
    mapping_feedback: List[FeedbackMappingFeedbackItem] = Field(default_factory=list)
    translation_overrides: List[FeedbackTranslationOverrideItem] = Field(default_factory=list)


class FeedbackAppliedSummary(BaseModel):
    brands: int
    products: int
    mappings: int
    translations: int


class FeedbackSubmitResponse(BaseModel):
    status: str
    run_id: int
    canonical_vertical_id: int
    applied: FeedbackAppliedSummary
    warnings: List[str]
