"""Integration tests for the run-level extraction pipeline."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session

from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeExtractionLog,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
    KnowledgeVertical,
)
from services.extraction.deepseek_consultant import DeepSeekConsultant
from services.extraction.pipeline import ExtractionPipeline


_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "suv_example_mini.json"

_QWEN_EXTRACTION_RESPONSE = json.dumps(
    [
        {"item_index": 0, "brand": "丰田", "product": "RAV4荣放"},
        {"item_index": 1, "brand": "本田", "product": "CR-V"},
        {"item_index": 2, "brand": "别克", "product": "昂科旗"},
        {"item_index": 3, "brand": "奇瑞", "product": "瑞虎9"},
        {"item_index": 4, "brand": "比亚迪", "product": "唐DM-i"},
        {"item_index": 5, "brand": "理想", "product": "L8"},
        {"item_index": 6, "brand": "丰田", "product": "汉兰达"}
    ],
    ensure_ascii=False,
)

_NORMALIZE_RESPONSE = json.dumps(
    {
        "brand_aliases": {
            "丰田": "Toyota",
            "本田": "Honda",
            "别克": "Buick",
            "奇瑞": "Chery",
            "比亚迪": "BYD",
            "理想": "Li Auto"
        },
        "product_aliases": {},
        "product_brand_map": {
            "途观L": "Volkswagen",
            "揽巡": "Volkswagen",
            "RAV4荣放": "Toyota",
            "CR-V": "Honda",
            "昂科旗": "Buick",
            "瑞虎9": "Chery",
            "唐DM-i": "BYD",
            "L8": "Li Auto",
            "汉兰达": "Toyota"
        }
    },
    ensure_ascii=False,
)

_VALIDATE_RESPONSE = json.dumps(
    {
        "valid_brands": [
            "Volkswagen",
            "Toyota",
            "Honda",
            "Buick",
            "Chery",
            "BYD",
            "Li Auto"
        ],
        "valid_products": [
            "途观L",
            "RAV4荣放",
            "CR-V",
            "昂科旗",
            "揽巡",
            "瑞虎9",
            "唐DM-i",
            "L8",
            "汉兰达"
        ],
        "rejected": []
    },
    ensure_ascii=False,
)

_COLD_START_SEED_RESPONSE = json.dumps(
    {
        "brands": [
            {
                "name_en": "Volkswagen",
                "name_zh": "大众",
                "aliases": ["大众汽车", "一汽-大众", "上汽大众"],
                "products": [
                    {"name": "途观L", "aliases": ["大众途观L"]},
                    {"name": "揽巡", "aliases": ["大众揽巡"]}
                ]
            },
            {
                "name_en": "Toyota",
                "name_zh": "丰田",
                "aliases": [],
                "products": [
                    {"name": "RAV4荣放", "aliases": ["丰田RAV4荣放"]},
                    {"name": "汉兰达", "aliases": ["丰田汉兰达"]}
                ]
            },
            {
                "name_en": "Honda",
                "name_zh": "本田",
                "aliases": [],
                "products": [{"name": "CR-V", "aliases": ["本田CR-V"]}]
            },
            {
                "name_en": "Buick",
                "name_zh": "别克",
                "aliases": [],
                "products": [{"name": "昂科旗", "aliases": ["别克昂科旗"]}]
            },
            {
                "name_en": "Chery",
                "name_zh": "奇瑞",
                "aliases": [],
                "products": [{"name": "瑞虎9", "aliases": ["奇瑞瑞虎9"]}]
            },
            {
                "name_en": "BYD",
                "name_zh": "比亚迪",
                "aliases": [],
                "products": [{"name": "唐DM-i", "aliases": ["比亚迪唐DM-i"]}]
            },
            {
                "name_en": "Li Auto",
                "name_zh": "理想",
                "aliases": [],
                "products": [{"name": "L8", "aliases": ["理想L8"]}]
            }
        ]
    },
    ensure_ascii=False,
)


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _seed_brand(
    db: Session,
    *,
    vertical_id: int,
    canonical_name: str,
    aliases: list[str],
    validation_source: str = "user",
) -> KnowledgeBrand:
    brand = KnowledgeBrand(
        vertical_id=vertical_id,
        canonical_name=canonical_name,
        display_name=canonical_name,
        is_validated=True,
        validation_source=validation_source,
    )
    db.add(brand)
    db.flush()
    for alias in aliases:
        db.add(KnowledgeBrandAlias(brand_id=brand.id, alias=alias))
    db.flush()
    return brand


def _seed_product(
    db: Session,
    *,
    vertical_id: int,
    brand: KnowledgeBrand,
    canonical_name: str,
    aliases: list[str],
    validation_source: str = "pipeline",
) -> KnowledgeProduct:
    product = KnowledgeProduct(
        vertical_id=vertical_id,
        brand_id=brand.id,
        canonical_name=canonical_name,
        display_name=canonical_name,
        is_validated=True,
        validation_source=validation_source,
    )
    db.add(product)
    db.flush()
    for alias in aliases:
        db.add(KnowledgeProductAlias(product_id=product.id, alias=alias))
    db.add(
        KnowledgeProductBrandMapping(
            vertical_id=vertical_id,
            product_id=product.id,
            brand_id=brand.id,
            is_validated=True,
            source=validation_source,
        )
    )
    db.flush()
    return product


@pytest.mark.asyncio
async def test_e2e_extraction_suv_mini_partial_kb(knowledge_db_session: Session):
    fixture = _load_fixture()
    vertical = KnowledgeVertical(
        name=fixture["vertical"],
        description=fixture["vertical_description"],
        seeded_at=datetime.now(timezone.utc),
        seed_version="fixture",
    )
    knowledge_db_session.add(vertical)
    knowledge_db_session.flush()

    vw = _seed_brand(
        knowledge_db_session,
        vertical_id=vertical.id,
        canonical_name="Volkswagen",
        aliases=["大众", "大众汽车", "一汽-大众", "上汽大众", "VW"],
    )
    _seed_product(
        knowledge_db_session,
        vertical_id=vertical.id,
        brand=vw,
        canonical_name="途观L",
        aliases=["大众途观L"],
    )
    _seed_product(
        knowledge_db_session,
        vertical_id=vertical.id,
        brand=vw,
        canonical_name="揽巡",
        aliases=["大众揽巡"],
    )

    pipeline = ExtractionPipeline(
        vertical=fixture["vertical"],
        vertical_description=fixture["vertical_description"],
        knowledge_db=knowledge_db_session,
        run_id=101,
    )

    with patch(
        "services.ollama.OllamaService._call_ollama",
        new=AsyncMock(return_value=_QWEN_EXTRACTION_RESPONSE),
    ) as mock_qwen, patch.object(
        DeepSeekConsultant,
        "normalize_and_map",
        new=AsyncMock(
            return_value=(
                json.loads(_NORMALIZE_RESPONSE)["brand_aliases"],
                json.loads(_NORMALIZE_RESPONSE)["product_aliases"],
                json.loads(_NORMALIZE_RESPONSE)["product_brand_map"],
            )
        ),
    ) as mock_normalize, patch.object(
        DeepSeekConsultant,
        "validate_relevance",
        new=AsyncMock(
            return_value=(
                set(json.loads(_VALIDATE_RESPONSE)["valid_brands"]),
                set(json.loads(_VALIDATE_RESPONSE)["valid_products"]),
                set(),
                set(),
                {},
            )
        ),
    ) as mock_validate, patch.object(
        DeepSeekConsultant,
        "store_rejections",
    ) as mock_store_rejections:
        await pipeline.process_response(fixture["llm_response"], response_id="r1")
        batch = await pipeline.finalize()

    result = batch.response_results["r1"]
    assert len(result.products) == 9
    assert set(result.brands) == {
        "Volkswagen",
        "Toyota",
        "Honda",
        "Buick",
        "Chery",
        "BYD",
        "Li Auto",
    }
    assert result.product_brand_relationships["途观L"] == "Volkswagen"
    assert result.product_brand_relationships["汉兰达"] == "Toyota"
    assert pipeline.debug_info.step0_item_count == 9
    assert pipeline.debug_info.step2_qwen_input_count == 7
    assert pipeline.debug_info.step2_qwen_batch_count == 1
    assert mock_qwen.await_count == 1
    assert mock_normalize.await_count == 1
    assert mock_validate.await_count == 1
    mock_store_rejections.assert_called_once()
    assert (
        knowledge_db_session.query(KnowledgeExtractionLog)
        .filter(KnowledgeExtractionLog.run_id == 101)
        .count()
        == 18
    )
    pipeline.close()


@pytest.mark.asyncio
async def test_e2e_kb_only_extraction_avoids_llm_calls(knowledge_db_session: Session):
    fixture = _load_fixture()
    vertical = KnowledgeVertical(
        name=fixture["vertical"],
        description=fixture["vertical_description"],
        seeded_at=datetime.now(timezone.utc),
        seed_version="fixture",
    )
    knowledge_db_session.add(vertical)
    knowledge_db_session.flush()

    seeded_brands = {
        "Volkswagen": ["大众", "大众汽车", "一汽-大众", "上汽大众", "VW"],
        "Toyota": ["丰田"],
        "Honda": ["本田"],
        "Buick": ["别克"],
        "Chery": ["奇瑞"],
        "BYD": ["比亚迪"],
        "Li Auto": ["理想"],
    }
    products = {
        "Volkswagen": [("途观L", ["大众途观L"]), ("揽巡", ["大众揽巡"])],
        "Toyota": [("RAV4荣放", ["丰田RAV4荣放"]), ("汉兰达", ["丰田汉兰达"])],
        "Honda": [("CR-V", ["本田CR-V"])],
        "Buick": [("昂科旗", ["别克昂科旗"])],
        "Chery": [("瑞虎9", ["奇瑞瑞虎9"])],
        "BYD": [("唐DM-i", ["比亚迪唐DM-i"])],
        "Li Auto": [("L8", ["理想L8"])],
    }

    for canonical_brand, aliases in seeded_brands.items():
        brand = _seed_brand(
            knowledge_db_session,
            vertical_id=vertical.id,
            canonical_name=canonical_brand,
            aliases=aliases,
        )
        for canonical_product, product_aliases in products[canonical_brand]:
            _seed_product(
                knowledge_db_session,
                vertical_id=vertical.id,
                brand=brand,
                canonical_name=canonical_product,
                aliases=product_aliases,
            )

    pipeline = ExtractionPipeline(
        vertical=fixture["vertical"],
        vertical_description=fixture["vertical_description"],
        knowledge_db=knowledge_db_session,
        run_id=102,
    )

    with patch(
        "services.ollama.OllamaService._call_ollama",
        new=AsyncMock(return_value="[]"),
    ) as mock_qwen, patch.object(
        DeepSeekConsultant,
        "_has_deepseek",
        return_value=False,
    ), patch.object(
        DeepSeekConsultant,
        "_call_deepseek",
        new=AsyncMock(),
    ) as mock_deepseek:
        await pipeline.process_response(fixture["llm_response"], response_id="r1")
        batch = await pipeline.finalize()

    result = batch.response_results["r1"]
    assert len(result.products) == 9
    assert result.product_brand_relationships["RAV4荣放"] == "Toyota"
    assert result.product_brand_relationships["揽巡"] == "Volkswagen"
    assert pipeline.debug_info.step2_qwen_batch_count == 0
    assert mock_qwen.await_count == 0
    assert mock_deepseek.await_count == 0
    pipeline.close()


@pytest.mark.asyncio
async def test_e2e_cold_start_with_user_brands(knowledge_db_session: Session):
    fixture = _load_fixture()
    pipeline = ExtractionPipeline(
        vertical=fixture["vertical"],
        vertical_description=fixture["vertical_description"],
        knowledge_db=knowledge_db_session,
        run_id=103,
    )

    with patch("services.remote_llms.DeepSeekService") as mock_deepseek_cls, patch(
        "services.ollama.OllamaService._call_ollama",
        new=AsyncMock(return_value="[]"),
    ) as mock_qwen, patch.object(
        DeepSeekConsultant,
        "_has_deepseek",
        return_value=False,
    ):
        mock_service = mock_deepseek_cls.return_value
        mock_service.has_api_key.return_value = True
        mock_service.query = AsyncMock(return_value=(_COLD_START_SEED_RESPONSE, 100, 300, 0.4))

        await pipeline.process_response(
            fixture["llm_response"],
            response_id="r1",
            user_brands=fixture["user_brands"],
        )
        batch = await pipeline.finalize()

    result = batch.response_results["r1"]
    knowledge_vertical = (
        knowledge_db_session.query(KnowledgeVertical)
        .filter(KnowledgeVertical.name == fixture["vertical"])
        .one()
    )
    volkswagen = (
        knowledge_db_session.query(KnowledgeBrand)
        .filter(
            KnowledgeBrand.vertical_id == knowledge_vertical.id,
            KnowledgeBrand.canonical_name == "Volkswagen",
        )
        .one()
    )
    vw_aliases = {
        alias.alias
        for alias in knowledge_db_session.query(KnowledgeBrandAlias)
        .filter(KnowledgeBrandAlias.brand_id == volkswagen.id)
        .all()
    }

    assert knowledge_vertical.seeded_at is not None
    assert knowledge_vertical.seed_version == "deepseek_v1"
    assert volkswagen.is_validated is True
    assert volkswagen.validation_source == "user"
    assert {"大众", "大众汽车", "一汽-大众", "上汽大众"} <= vw_aliases
    assert len(result.products) == 9
    assert result.product_brand_relationships["唐DM-i"] == "BYD"
    assert pipeline.debug_info.knowledge_seeded is True
    assert mock_service.query.await_count == 1
    assert mock_qwen.await_count == 0
    pipeline.close()
