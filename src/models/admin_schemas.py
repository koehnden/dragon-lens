from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AdminResponse(BaseModel):
    status: str


class KnowledgeAliasPayload(BaseModel):
    alias: str
    language: Optional[str] = None


class KnowledgeBrandPayload(BaseModel):
    canonical_name: str
    display_name: str
    is_validated: bool = False
    validation_source: Optional[str] = None
    mention_count: int = 0
    aliases: list[KnowledgeAliasPayload] = Field(default_factory=list)


class KnowledgeProductPayload(BaseModel):
    canonical_name: str
    display_name: str
    brand_canonical_name: Optional[str] = None
    is_validated: bool = False
    validation_source: Optional[str] = None
    mention_count: int = 0
    aliases: list[KnowledgeAliasPayload] = Field(default_factory=list)


class KnowledgeMappingPayload(BaseModel):
    product_canonical_name: str
    brand_canonical_name: str
    is_validated: bool = False
    source: Optional[str] = None


class KnowledgeRejectedEntityPayload(BaseModel):
    entity_type: str
    name: str
    reason: str


class KnowledgeTranslationOverridePayload(BaseModel):
    entity_type: str
    canonical_name: str
    language: str
    override_text: str
    reason: Optional[str] = None


class KnowledgeSyncRequest(BaseModel):
    submission_id: str
    source_app_version: Optional[str] = None
    submitted_at: Optional[datetime] = None
    vertical_name: str
    vertical_description: Optional[str] = None
    vertical_aliases: list[str] = Field(default_factory=list)
    brands: list[KnowledgeBrandPayload] = Field(default_factory=list)
    products: list[KnowledgeProductPayload] = Field(default_factory=list)
    mappings: list[KnowledgeMappingPayload] = Field(default_factory=list)
    rejected_entities: list[KnowledgeRejectedEntityPayload] = Field(default_factory=list)
    translation_overrides: list[KnowledgeTranslationOverridePayload] = Field(
        default_factory=list
    )


class KnowledgeSyncResponse(AdminResponse):
    canonical_vertical_id: int
    created_counts: dict[str, int]
    updated_counts: dict[str, int]


class DemoVerticalPayload(BaseModel):
    name: str
    description: Optional[str] = None


class DemoBrandPayload(BaseModel):
    source_id: int
    display_name: str
    original_name: str
    translated_name: Optional[str] = None
    aliases: dict = Field(default_factory=dict)
    is_user_input: bool = True
    created_at: Optional[datetime] = None


class DemoProductPayload(BaseModel):
    source_id: int
    brand_source_id: Optional[int] = None
    display_name: str
    original_name: str
    translated_name: Optional[str] = None
    is_user_input: bool = False
    created_at: Optional[datetime] = None


class DemoRunPayload(BaseModel):
    source_id: int
    provider: str
    model_name: str
    route: Optional[str] = None
    status: str
    reuse_answers: bool = False
    web_search_enabled: bool = False
    run_time: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class DemoPromptPayload(BaseModel):
    source_id: int
    run_source_id: int
    text_en: Optional[str] = None
    text_zh: Optional[str] = None
    language_original: str
    created_at: Optional[datetime] = None


class DemoAnswerPayload(BaseModel):
    source_id: int
    run_source_id: int
    prompt_source_id: int
    provider: str
    model_name: str
    route: Optional[str] = None
    raw_answer_zh: str
    raw_answer_en: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency: Optional[float] = None
    cost_estimate: Optional[float] = None
    created_at: Optional[datetime] = None


class DemoBrandMentionPayload(BaseModel):
    llm_answer_source_id: int
    brand_source_id: int
    mentioned: bool
    rank: Optional[int] = None
    sentiment: str
    evidence_snippets: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class DemoProductMentionPayload(BaseModel):
    llm_answer_source_id: int
    product_source_id: int
    mentioned: bool
    rank: Optional[int] = None
    sentiment: str
    evidence_snippets: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class DemoProductBrandMappingPayload(BaseModel):
    product_source_id: Optional[int] = None
    brand_source_id: Optional[int] = None
    confidence: float = 0.0
    is_validated: bool = False
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DemoRunMetricPayload(BaseModel):
    run_source_id: int
    brand_source_id: int
    mention_rate: float
    share_of_voice: float
    top_spot_share: float
    sentiment_index: float
    dragon_lens_visibility: float
    created_at: Optional[datetime] = None


class DemoRunProductMetricPayload(BaseModel):
    run_source_id: int
    product_source_id: int
    mention_rate: float
    share_of_voice: float
    top_spot_share: float
    sentiment_index: float
    dragon_lens_visibility: float
    created_at: Optional[datetime] = None


class DemoPublishRequest(BaseModel):
    submission_id: str
    source_app_version: Optional[str] = None
    published_at: Optional[datetime] = None
    vertical: DemoVerticalPayload
    brands: list[DemoBrandPayload] = Field(default_factory=list)
    products: list[DemoProductPayload] = Field(default_factory=list)
    runs: list[DemoRunPayload] = Field(default_factory=list)
    prompts: list[DemoPromptPayload] = Field(default_factory=list)
    answers: list[DemoAnswerPayload] = Field(default_factory=list)
    brand_mentions: list[DemoBrandMentionPayload] = Field(default_factory=list)
    product_mentions: list[DemoProductMentionPayload] = Field(default_factory=list)
    product_brand_mappings: list[DemoProductBrandMappingPayload] = Field(
        default_factory=list
    )
    run_metrics: list[DemoRunMetricPayload] = Field(default_factory=list)
    run_product_metrics: list[DemoRunProductMetricPayload] = Field(default_factory=list)


class DemoPublishResponse(AdminResponse):
    vertical_id: int
    run_count: int
    brand_count: int
    product_count: int
