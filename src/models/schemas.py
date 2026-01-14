import enum
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
    provider: str = Field(
        default="qwen", description="LLM provider (qwen, deepseek, kimi, openrouter)"
    )
    model_name: str = Field(
        default="qwen2.5:7b-instruct-q4_0",
        description="Specific model name or OpenRouter model ID",
    )
    reuse_answers: bool = Field(
        default=False, description="Whether to reuse answers from previous runs"
    )
    web_search_enabled: bool = Field(
        default=False, description="Whether web search is enabled for this run"
    )
    comparison_enabled: bool = Field(
        default=True, description="Deprecated: comparison prompts run automatically after the main run completes"
    )
    comparison_competitor_brands: List[str] = Field(
        default_factory=list, description="Ignored (comparison prompts are system-generated)"
    )
    comparison_prompts: List[PromptCreate] = Field(
        default_factory=list, description="Ignored (comparison prompts are system-generated)"
    )
    comparison_target_count: int = Field(
        default=20,
        ge=1,
        le=500,
        description="Ignored (comparison prompts are system-generated with a fixed count)",
    )
    comparison_min_prompts_per_competitor: int = Field(
        default=2,
        ge=0,
        le=50,
        description="Ignored (comparison prompts are system-generated)",
    )
    comparison_autogenerate_missing: bool = Field(
        default=True, description="Ignored (comparison prompts are system-generated)"
    )


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


class RunInspectorBrandExtract(BaseModel):
    brand_zh: Optional[str]
    brand_en: Optional[str]
    text_snippet_zh: Optional[str]
    text_snippet_en: Optional[str]
    rank: Optional[int]
    products_zh: List[str]
    products_en: List[str]


class RunInspectorPromptExport(BaseModel):
    run_id: int
    llm_answer_id: int
    vertical_name: str
    model: str
    prompt_zh: Optional[str]
    prompt_eng: Optional[str]
    prompt_response_zh: str
    prompt_response_en: Optional[str]
    brands_extracted: List[RunInspectorBrandExtract]


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


class ComparisonEvidenceSnippet(BaseModel):
    snippet_zh: str
    snippet_en: str
    sentiment: str
    aspect: Optional[str] = None


class ComparisonEntitySentimentSummary(BaseModel):
    entity_type: str
    entity_id: int
    entity_name: str
    entity_role: str
    positive_count: int
    neutral_count: int
    negative_count: int
    sentiment_index: float
    snippets: List[ComparisonEvidenceSnippet] = Field(default_factory=list)


class RunComparisonMessage(BaseModel):
    level: str
    code: str
    message: str


class RunComparisonMetricsResponse(BaseModel):
    run_id: int
    vertical_id: int
    vertical_name: str
    provider: str
    model_name: str
    primary_brand_id: int
    primary_brand_name: str
    brands: List[ComparisonEntitySentimentSummary]
    products: List[ComparisonEntitySentimentSummary]
    messages: List[RunComparisonMessage] = Field(default_factory=list)


class ComparisonCharacteristicSummary(BaseModel):
    characteristic_zh: str
    characteristic_en: str
    total_prompts: int
    primary_wins: int
    competitor_wins: int
    ties: int
    unknown: int


class ComparisonPromptOutcomeDetail(BaseModel):
    prompt_id: int
    characteristic_zh: str
    characteristic_en: str
    prompt_zh: str
    prompt_en: Optional[str] = None
    answer_zh: Optional[str] = None
    answer_en: Optional[str] = None
    primary_product_id: Optional[int] = None
    primary_product_name: str
    competitor_product_id: Optional[int] = None
    competitor_product_name: str
    winner_role: str
    winner_product_id: Optional[int] = None
    winner_product_name: str
    loser_product_id: Optional[int] = None
    loser_product_name: str


class RunComparisonSummaryResponse(BaseModel):
    run_id: int
    vertical_id: int
    vertical_name: str
    provider: str
    model_name: str
    primary_brand_id: int
    primary_brand_name: str
    brands: List[ComparisonEntitySentimentSummary]
    products: List[ComparisonEntitySentimentSummary]
    characteristics: List[ComparisonCharacteristicSummary] = Field(default_factory=list)
    prompts: List[ComparisonPromptOutcomeDetail] = Field(default_factory=list)
    messages: List[RunComparisonMessage] = Field(default_factory=list)


class AllRunMetricsResponse(BaseModel):
    run_id: int
    vertical_id: int
    vertical_name: str
    provider: str
    model_name: str
    run_time: datetime
    metrics: List[RunMetricsResponse]

    model_config = {"from_attributes": True}


class AllRunProductMetricsResponse(BaseModel):
    run_id: int
    vertical_id: int
    vertical_name: str
    provider: str
    model_name: str
    run_time: datetime
    products: List[ProductMetrics]

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
    api_key: Optional[str] = Field(
        None, min_length=1, description="New API key (optional)"
    )
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
    VALIDATE = "validate"
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
    translation_overrides: List[FeedbackTranslationOverrideItem] = Field(
        default_factory=list
    )


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


class FeedbackCandidateBrand(BaseModel):
    name: str
    translated_name: Optional[str]
    mention_count: int


class FeedbackCandidateProduct(BaseModel):
    name: str
    translated_name: Optional[str]
    brand_name: Optional[str]
    mention_count: int


class FeedbackCandidateMapping(BaseModel):
    product_name: str
    brand_name: str
    confidence: Optional[float] = None
    source: Optional[str] = None


class FeedbackCandidateMissingMapping(BaseModel):
    product_name: str


class FeedbackCandidateTranslation(BaseModel):
    entity_type: FeedbackEntityType
    canonical_name: str
    current_translation_en: Optional[str]
    mention_count: int


class FeedbackCandidatesResponse(BaseModel):
    group_vertical_ids: List[int] = Field(default_factory=list)
    vertical_id: int
    vertical_name: str
    latest_completed_run_id: Optional[int]
    resolved_canonical_vertical_id: Optional[int]
    resolved_canonical_vertical_name: Optional[str]
    brands: List[FeedbackCandidateBrand] = Field(default_factory=list)
    products: List[FeedbackCandidateProduct] = Field(default_factory=list)
    mappings: List[FeedbackCandidateMapping] = Field(default_factory=list)
    missing_mappings: List[FeedbackCandidateMissingMapping] = Field(
        default_factory=list
    )
    translations: List[FeedbackCandidateTranslation] = Field(default_factory=list)


class FeedbackVerticalAliasRequest(BaseModel):
    vertical_id: int
    canonical_vertical: FeedbackCanonicalVertical


class FeedbackVerticalAliasResponse(BaseModel):
    status: str
    vertical_id: int
    vertical_name: str
    canonical_vertical_id: int
    canonical_vertical_name: str
    alias_created: bool


class FeatureScoreSchema(BaseModel):
    feature_id: int
    feature_name_zh: str
    feature_name_en: Optional[str]
    frequency: int
    positive_count: int
    neutral_count: int
    negative_count: int
    combined_score: float


class EntityFeatureDataSchema(BaseModel):
    entity_id: int
    entity_name: str
    entity_type: str
    features: List[FeatureScoreSchema] = Field(default_factory=list)


class RunFeatureMetricsResponse(BaseModel):
    run_id: int
    vertical_id: int
    vertical_name: str
    top_features: List[str] = Field(default_factory=list)
    entities: List[EntityFeatureDataSchema] = Field(default_factory=list)
