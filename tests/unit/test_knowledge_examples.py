from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models.domain import EntityType
from models.knowledge_domain import (
    KnowledgeRejectedEntity,
    KnowledgeTranslationOverride,
    KnowledgeVertical,
)
from services.knowledge_examples import rejected_examples, translation_override_examples


def test_rejected_examples_prioritize_same_vertical_and_mix_others(knowledge_db_session: Session):
    base = datetime(2024, 1, 1, 0, 0, 0)
    target = KnowledgeVertical(name="Target")
    knowledge_db_session.add(target)
    knowledge_db_session.flush()

    knowledge_db_session.add_all(
        [
            KnowledgeRejectedEntity(
                vertical_id=target.id,
                entity_type=EntityType.BRAND,
                name="四驱",
                reason="user_reject",
                created_at=base,
            ),
            KnowledgeRejectedEntity(
                vertical_id=target.id,
                entity_type=EntityType.BRAND,
                name="两驱",
                reason="too_generic",
                created_at=base + timedelta(seconds=1),
            ),
        ]
    )

    other_verticals: list[KnowledgeVertical] = []
    for idx in range(10):
        v = KnowledgeVertical(name=f"Other-{idx}")
        knowledge_db_session.add(v)
        other_verticals.append(v)
    knowledge_db_session.flush()

    for idx, v in enumerate(other_verticals):
        for j in range(3):
            knowledge_db_session.add(
                KnowledgeRejectedEntity(
                    vertical_id=v.id,
                    entity_type=EntityType.BRAND,
                    name=f"bad-{idx}-{j}",
                    reason="mistake_with_reason",
                    created_at=base + timedelta(minutes=idx, seconds=j),
                )
            )
    knowledge_db_session.flush()

    examples = rejected_examples(
        knowledge_db_session, target_vertical_id=target.id, entity_type=EntityType.BRAND, limit=30, max_per_other_vertical=3
    )

    assert len(examples) == 30
    assert examples[0]["same_vertical"] is True
    assert examples[0]["name"] == "两驱"

    cross = [e for e in examples if not e["same_vertical"]]
    assert len({e["vertical_name"] for e in cross}) >= 5
    assert all(e["vertical_name"] for e in cross)


def test_translation_override_examples_prioritize_reason_and_mix_others(knowledge_db_session: Session):
    base = datetime(2024, 1, 1, 0, 0, 0)
    target = KnowledgeVertical(name="Target-T")
    knowledge_db_session.add(target)
    knowledge_db_session.flush()

    knowledge_db_session.add_all(
        [
            KnowledgeTranslationOverride(
                vertical_id=target.id,
                entity_type=EntityType.BRAND,
                canonical_name="丰田",
                language="en",
                override_text="Toyota",
                reason=None,
                created_at=base,
            ),
            KnowledgeTranslationOverride(
                vertical_id=target.id,
                entity_type=EntityType.BRAND,
                canonical_name="大众",
                language="en",
                override_text="Volkswagen",
                reason="official English name",
                created_at=base + timedelta(seconds=1),
            ),
        ]
    )

    other_verticals: list[KnowledgeVertical] = []
    for idx in range(10):
        v = KnowledgeVertical(name=f"OtherT-{idx}")
        knowledge_db_session.add(v)
        other_verticals.append(v)
    knowledge_db_session.flush()

    for idx, v in enumerate(other_verticals):
        for j in range(3):
            knowledge_db_session.add(
                KnowledgeTranslationOverride(
                    vertical_id=v.id,
                    entity_type=EntityType.BRAND,
                    canonical_name=f"牌子{idx}{j}",
                    language="en",
                    override_text=f"Brand{idx}{j}",
                    reason="has reason",
                    created_at=base + timedelta(minutes=idx, seconds=j),
                )
            )
    knowledge_db_session.flush()

    examples = translation_override_examples(
        knowledge_db_session, target_vertical_id=target.id, entity_type=EntityType.BRAND, limit=30, max_per_other_vertical=3, language="en"
    )

    assert len(examples) == 30
    assert examples[0]["same_vertical"] is True
    assert examples[0]["canonical_name"] == "大众"

    cross = [e for e in examples if not e["same_vertical"]]
    assert len({e["vertical_name"] for e in cross}) >= 5
    assert all(e["vertical_name"] for e in cross)
