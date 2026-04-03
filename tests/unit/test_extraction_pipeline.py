from unittest.mock import AsyncMock, patch

import pytest

from models.knowledge_domain import KnowledgeBrand, KnowledgeBrandAlias, KnowledgeVertical
from services.extraction.models import BrandProductPair, ItemExtractionResult, ResponseItem
from services.extraction.pipeline import ExtractionPipeline


@pytest.mark.asyncio
async def test_pipeline_reuses_session_kb_across_responses(knowledge_db_session):
    pipeline = ExtractionPipeline(
        vertical="SUV Cars",
        vertical_description="Chinese SUV market",
        knowledge_db=knowledge_db_session,
    )

    qwen_result = [
        ItemExtractionResult(
            item=ResponseItem(text="Toyota RAV4", position=0, response_id="r1"),
            pairs=[BrandProductPair(brand="Toyota", product="RAV4", brand_source="qwen", product_source="qwen")],
        )
    ]

    with patch(
        "services.extraction.pipeline.VerticalSeeder.ensure_seeded",
        new=AsyncMock(return_value=None),
    ), patch(
        "services.extraction.pipeline.QwenBatchExtractor.extract_missing",
        new=AsyncMock(side_effect=[qwen_result]),
    ) as mock_extract_missing:
        first = await pipeline.process_response("1. Toyota RAV4", response_id="r1")
        second = await pipeline.process_response("1. RAV4 is practical", response_id="r2")

    assert "Toyota" in first.brands
    assert second.product_brand_relationships == {"RAV4": "Toyota"}
    assert mock_extract_missing.await_count == 1
    pipeline.close()


@pytest.mark.asyncio
async def test_finalize_builds_canonical_response_results(knowledge_db_session):
    vertical = KnowledgeVertical(name="SUV Cars", description="Chinese SUV market")
    knowledge_db_session.add(vertical)
    knowledge_db_session.flush()

    vw = KnowledgeBrand(
        vertical_id=vertical.id,
        canonical_name="Volkswagen",
        display_name="Volkswagen",
        is_validated=True,
        validation_source="user",
    )
    knowledge_db_session.add(vw)
    knowledge_db_session.flush()
    knowledge_db_session.add(KnowledgeBrandAlias(brand_id=vw.id, alias="大众", language="zh"))
    knowledge_db_session.flush()

    pipeline = ExtractionPipeline(
        vertical="SUV Cars",
        vertical_description="Chinese SUV market",
        knowledge_db=knowledge_db_session,
    )

    with patch(
        "services.extraction.pipeline.VerticalSeeder.ensure_seeded",
        new=AsyncMock(return_value=None),
    ), patch(
        "services.extraction.pipeline.QwenBatchExtractor.extract_missing",
        new=AsyncMock(
            return_value=[
                ItemExtractionResult(
                    item=ResponseItem(text="大众途观L 2024款", position=0, response_id="r1"),
                    pairs=[
                        BrandProductPair(
                            brand="大众",
                            product="途观L 2024款",
                            brand_source="qwen",
                            product_source="qwen",
                        )
                    ],
                )
            ]
        ),
    ), patch(
        "services.extraction.pipeline.ExtractionConsultant.normalize_and_map",
        new=AsyncMock(return_value=({"大众": "Volkswagen"}, {"途观L 2024款": "途观L"}, {"途观L": "Volkswagen"})),
    ), patch(
        "services.extraction.pipeline.ExtractionConsultant.validate_relevance",
        new=AsyncMock(return_value=({"Volkswagen"}, {"途观L"}, set(), set(), {})),
    ):
        await pipeline.process_response("1. 大众途观L 2024款", response_id="r1")
        batch = await pipeline.finalize()

    result = batch.response_results["r1"]
    assert result.brands == {"Volkswagen": ["Volkswagen"]}
    assert result.products == {"途观L": ["途观L"]}
    assert result.product_brand_relationships == {"途观L": "Volkswagen"}
    pipeline.close()
