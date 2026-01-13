def test_create_job_creates_vertical_alias_in_knowledge_db(client, knowledge_db_session):
    from models.knowledge_domain import KnowledgeVertical, KnowledgeVerticalAlias

    canonical = KnowledgeVertical(name="Car", description=None)
    knowledge_db_session.add(canonical)
    knowledge_db_session.commit()
    knowledge_db_session.refresh(canonical)

    payload = {
        "vertical_name": "SUV",
        "vertical_description": None,
        "canonical_vertical": {"id": canonical.id, "is_new": False},
        "brands": [{"display_name": "比亚迪", "aliases": {"zh": ["BYD"], "en": ["BYD"]}}],
        "prompts": [{"text_zh": "推荐SUV品牌", "text_en": None, "language_original": "zh"}],
        "provider": "qwen",
        "model_name": "qwen2.5:7b-instruct-q4_0",
    }

    response = client.post("/api/v1/tracking/jobs", json=payload)
    assert response.status_code == 201

    alias = (
        knowledge_db_session.query(KnowledgeVerticalAlias)
        .filter(KnowledgeVerticalAlias.vertical_id == canonical.id, KnowledgeVerticalAlias.alias == "SUV")
        .first()
    )
    assert alias is not None
