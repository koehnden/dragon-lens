"""Unit tests for VerticalSeeder (cold start seeding)."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session

from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
    KnowledgeVertical,
)
from services.extraction.vertical_seeder import VerticalSeeder, _parse_json_response


@pytest.fixture
def vertical(knowledge_db_session: Session) -> KnowledgeVertical:
    v = KnowledgeVertical(name="SUV Cars", description="Chinese SUV market")
    knowledge_db_session.add(v)
    knowledge_db_session.flush()
    return v


@pytest.fixture
def seeder(vertical: KnowledgeVertical) -> VerticalSeeder:
    return VerticalSeeder(
        vertical="SUV Cars",
        vertical_description="Chinese SUV market",
        vertical_id=vertical.id,
    )


USER_BRANDS = [
    {
        "display_name": "Volkswagen",
        "aliases": {
            "zh": ["大众汽车", "一汽-大众", "上汽大众"],
            "en": ["VW", "Volkswagen"],
        },
    },
    {
        "display_name": "Toyota",
        "aliases": {
            "zh": ["丰田", "一汽丰田", "广汽丰田"],
            "en": ["Toyota"],
        },
    },
]

DEEPSEEK_SEED_RESPONSE = json.dumps({
    "brands": [
        {
            "name_en": "BYD",
            "name_zh": "比亚迪",
            "aliases": ["BYD汽车"],
            "products": [
                {"name": "Song PLUS", "aliases": ["宋PLUS", "宋PLUS DM-i"]},
                {"name": "Tang", "aliases": ["唐", "唐DM-i"]},
            ],
        },
        {
            "name_en": "Li Auto",
            "name_zh": "理想",
            "aliases": ["理想汽车", "LIXIANG"],
            "products": [
                {"name": "L8", "aliases": ["理想L8"]},
            ],
        },
        {
            "name_en": "NIO",
            "name_zh": "蔚来",
            "aliases": [],
            "products": [],
        },
    ]
})


class TestShouldSeed:
    def test_returns_true_when_no_brands(
        self, seeder: VerticalSeeder, knowledge_db_session: Session
    ):
        assert seeder.should_seed(knowledge_db_session) is True

    def test_returns_true_when_few_validated_brands(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        for i in range(5):
            knowledge_db_session.add(
                KnowledgeBrand(
                    vertical_id=vertical.id,
                    canonical_name=f"Brand{i}",
                    display_name=f"Brand{i}",
                    is_validated=True,
                    validation_source="user",
                )
            )
        knowledge_db_session.flush()
        assert seeder.should_seed(knowledge_db_session) is True

    def test_returns_false_when_enough_validated_brands(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        for i in range(10):
            knowledge_db_session.add(
                KnowledgeBrand(
                    vertical_id=vertical.id,
                    canonical_name=f"Brand{i}",
                    display_name=f"Brand{i}",
                    is_validated=True,
                    validation_source="user",
                )
            )
        knowledge_db_session.flush()
        assert seeder.should_seed(knowledge_db_session) is False

    def test_unvalidated_brands_dont_count(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        for i in range(15):
            knowledge_db_session.add(
                KnowledgeBrand(
                    vertical_id=vertical.id,
                    canonical_name=f"Brand{i}",
                    display_name=f"Brand{i}",
                    is_validated=False,
                    validation_source="seed",
                )
            )
        knowledge_db_session.flush()
        assert seeder.should_seed(knowledge_db_session) is True


class TestSeedFromUserBrands:
    def test_creates_brands_with_aliases(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        count = seeder.seed_from_user_brands(knowledge_db_session, USER_BRANDS)
        assert count == 2

        brands = (
            knowledge_db_session.query(KnowledgeBrand)
            .filter(KnowledgeBrand.vertical_id == vertical.id)
            .all()
        )
        assert len(brands) == 2

        vw = next(b for b in brands if b.display_name == "Volkswagen")
        assert vw.is_validated is True
        assert vw.validation_source == "user"
        assert vw.alias_key is not None

        vw_aliases = (
            knowledge_db_session.query(KnowledgeBrandAlias)
            .filter(KnowledgeBrandAlias.brand_id == vw.id)
            .all()
        )
        alias_texts = {a.alias for a in vw_aliases}
        assert "大众汽车" in alias_texts
        assert "一汽-大众" in alias_texts
        assert "上汽大众" in alias_texts
        assert "VW" in alias_texts

    def test_skips_duplicate_brands(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        seeder.seed_from_user_brands(knowledge_db_session, USER_BRANDS)
        count = seeder.seed_from_user_brands(knowledge_db_session, USER_BRANDS)
        assert count == 0

        brands = (
            knowledge_db_session.query(KnowledgeBrand)
            .filter(KnowledgeBrand.vertical_id == vertical.id)
            .all()
        )
        assert len(brands) == 2

    def test_skips_empty_display_name(
        self, seeder: VerticalSeeder, knowledge_db_session: Session
    ):
        count = seeder.seed_from_user_brands(
            knowledge_db_session, [{"display_name": "", "aliases": {}}]
        )
        assert count == 0

    def test_alias_key_populated(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        seeder.seed_from_user_brands(knowledge_db_session, USER_BRANDS)
        vw = (
            knowledge_db_session.query(KnowledgeBrand)
            .filter(KnowledgeBrand.display_name == "Volkswagen")
            .first()
        )
        assert vw.alias_key == "volkswagen"

        aliases = (
            knowledge_db_session.query(KnowledgeBrandAlias)
            .filter(KnowledgeBrandAlias.brand_id == vw.id)
            .all()
        )
        for alias in aliases:
            assert alias.alias_key is not None
            assert len(alias.alias_key) > 0


class TestSeedFromDeepSeek:
    @pytest.mark.asyncio
    async def test_stores_brands_products_aliases(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        with patch(
            "services.remote_llms.DeepSeekService"
        ) as mock_ds_cls:
            mock_ds = mock_ds_cls.return_value
            mock_ds.has_api_key.return_value = True
            mock_ds.query = AsyncMock(
                return_value=(DEEPSEEK_SEED_RESPONSE, 100, 500, 0.5)
            )

            count = await seeder.seed_from_deepseek(knowledge_db_session)

        assert count == 3

        brands = (
            knowledge_db_session.query(KnowledgeBrand)
            .filter(KnowledgeBrand.vertical_id == vertical.id)
            .all()
        )
        assert len(brands) == 3

        byd = next(b for b in brands if b.canonical_name == "BYD")
        assert byd.is_validated is False
        assert byd.validation_source == "seed"

        # Check BYD aliases
        byd_aliases = (
            knowledge_db_session.query(KnowledgeBrandAlias)
            .filter(KnowledgeBrandAlias.brand_id == byd.id)
            .all()
        )
        alias_texts = {a.alias for a in byd_aliases}
        assert "比亚迪" in alias_texts
        assert "BYD" in alias_texts
        assert "BYD汽车" in alias_texts

        # Check products
        products = (
            knowledge_db_session.query(KnowledgeProduct)
            .filter(KnowledgeProduct.brand_id == byd.id)
            .all()
        )
        assert len(products) == 2
        product_names = {p.canonical_name for p in products}
        assert "Song PLUS" in product_names
        assert "Tang" in product_names

        # Check product aliases
        song = next(p for p in products if p.canonical_name == "Song PLUS")
        song_aliases = (
            knowledge_db_session.query(KnowledgeProductAlias)
            .filter(KnowledgeProductAlias.product_id == song.id)
            .all()
        )
        song_alias_texts = {a.alias for a in song_aliases}
        assert "宋PLUS" in song_alias_texts
        assert "宋PLUS DM-i" in song_alias_texts

        # Check product-brand mappings
        mappings = (
            knowledge_db_session.query(KnowledgeProductBrandMapping)
            .filter(KnowledgeProductBrandMapping.vertical_id == vertical.id)
            .all()
        )
        assert len(mappings) == 3  # Song PLUS, Tang, L8
        for m in mappings:
            assert m.source == "seed"
            assert m.is_validated is False

    @pytest.mark.asyncio
    async def test_no_api_key_returns_zero(
        self, seeder: VerticalSeeder, knowledge_db_session: Session
    ):
        with patch(
            "services.remote_llms.DeepSeekService"
        ) as mock_ds_cls:
            mock_ds = mock_ds_cls.return_value
            mock_ds.has_api_key.return_value = False

            count = await seeder.seed_from_deepseek(knowledge_db_session)

        assert count == 0

    @pytest.mark.asyncio
    async def test_deepseek_error_returns_zero(
        self, seeder: VerticalSeeder, knowledge_db_session: Session
    ):
        with patch(
            "services.remote_llms.DeepSeekService"
        ) as mock_ds_cls:
            mock_ds = mock_ds_cls.return_value
            mock_ds.has_api_key.return_value = True
            mock_ds.query = AsyncMock(side_effect=Exception("API error"))

            count = await seeder.seed_from_deepseek(knowledge_db_session)

        assert count == 0

    @pytest.mark.asyncio
    async def test_products_have_alias_keys(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        with patch(
            "services.remote_llms.DeepSeekService"
        ) as mock_ds_cls:
            mock_ds = mock_ds_cls.return_value
            mock_ds.has_api_key.return_value = True
            mock_ds.query = AsyncMock(
                return_value=(DEEPSEEK_SEED_RESPONSE, 100, 500, 0.5)
            )

            await seeder.seed_from_deepseek(knowledge_db_session)

        products = (
            knowledge_db_session.query(KnowledgeProduct)
            .filter(KnowledgeProduct.vertical_id == vertical.id)
            .all()
        )
        for product in products:
            assert product.alias_key is not None


class TestEnsureSeeded:
    @pytest.mark.asyncio
    async def test_seeds_user_brands_then_deepseek(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        with patch(
            "services.remote_llms.DeepSeekService"
        ) as mock_ds_cls:
            mock_ds = mock_ds_cls.return_value
            mock_ds.has_api_key.return_value = True
            mock_ds.query = AsyncMock(
                return_value=(DEEPSEEK_SEED_RESPONSE, 100, 500, 0.5)
            )

            await seeder.ensure_seeded(knowledge_db_session, USER_BRANDS)

        brands = (
            knowledge_db_session.query(KnowledgeBrand)
            .filter(KnowledgeBrand.vertical_id == vertical.id)
            .all()
        )
        # 2 user brands + 3 DeepSeek brands = 5
        assert len(brands) == 5

        user_brands = [b for b in brands if b.validation_source == "user"]
        seed_brands = [b for b in brands if b.validation_source == "seed"]
        assert len(user_brands) == 2
        assert len(seed_brands) == 3

    @pytest.mark.asyncio
    async def test_skips_deepseek_if_enough_user_brands(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        # Create 10 validated user brands
        many_brands = [
            {"display_name": f"Brand{i}", "aliases": {"en": [f"B{i}"]}}
            for i in range(10)
        ]

        with patch(
            "services.remote_llms.DeepSeekService"
        ) as mock_ds_cls:
            mock_ds = mock_ds_cls.return_value

            await seeder.ensure_seeded(knowledge_db_session, many_brands)

            # DeepSeek should never be called
            mock_ds.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_if_already_seeded(
        self, seeder: VerticalSeeder, knowledge_db_session: Session, vertical: KnowledgeVertical
    ):
        # Pre-populate with 10 validated brands
        for i in range(10):
            knowledge_db_session.add(
                KnowledgeBrand(
                    vertical_id=vertical.id,
                    canonical_name=f"Brand{i}",
                    display_name=f"Brand{i}",
                    is_validated=True,
                    validation_source="user",
                )
            )
        knowledge_db_session.flush()

        with patch(
            "services.remote_llms.DeepSeekService"
        ) as mock_ds_cls:
            await seeder.ensure_seeded(knowledge_db_session, USER_BRANDS)
            mock_ds_cls.assert_not_called()


class TestParseJsonResponse:
    def test_parses_clean_json(self):
        result = _parse_json_response('{"brands": []}')
        assert result == {"brands": []}

    def test_parses_markdown_fenced_json(self):
        text = '```json\n{"brands": []}\n```'
        result = _parse_json_response(text)
        assert result == {"brands": []}

    def test_parses_json_with_surrounding_text(self):
        text = 'Here are the brands:\n{"brands": []}\nThat is all.'
        result = _parse_json_response(text)
        assert result == {"brands": []}

    def test_returns_none_for_invalid_json(self):
        result = _parse_json_response("not json at all")
        assert result is None

    def test_returns_none_for_empty(self):
        result = _parse_json_response("")
        assert result is None
