import pytest


def test_ai_corrections_flow_creates_report_and_review_items(client, db_session, knowledge_db_session, monkeypatch):
    from models import Run, RunStatus, Vertical

    vertical = Vertical(name="sportswear", description=None)
    db_session.add(vertical)
    db_session.commit()

    run = Run(
        vertical_id=vertical.id,
        provider="qwen",
        model_name="qwen2",
        status=RunStatus.COMPLETED,
        reuse_answers=False,
        web_search_enabled=False,
    )
    db_session.add(run)
    db_session.commit()

    run_export = [
        {
            "run_id": run.id,
            "llm_answer_id": 10,
            "vertical_name": vertical.name,
            "model": "qwen2",
            "prompt_zh": "推荐运动鞋品牌",
            "prompt_eng": "Recommend sports shoe brands",
            "prompt_response_zh": "耐克是一个品牌。",
            "prompt_response_en": None,
            "brands_extracted": [
                {
                    "brand_zh": "耐克",
                    "brand_en": "Nike",
                    "text_snippet_zh": "耐克",
                    "text_snippet_en": "Nike",
                    "rank": 1,
                    "products_zh": [],
                    "products_en": [],
                }
            ],
        }
    ]

    async def fake_run_audit_batches(*args, **kwargs):
        return (
            [
                {
                    "llm_answer_id": 10,
                    "truth": {"brands": ["耐克"], "products": [], "mappings": []},
                    "suggestions": [
                        {
                            "category": "Ok",
                            "action": "validate_brand",
                            "brand_name": "耐克",
                            "product_name": None,
                            "wrong_name": None,
                            "correct_name": None,
                            "reason": "correct",
                            "evidence_quote_zh": "耐克",
                            "confidence_level": "VERY_HIGH",
                            "confidence_score_0_1": 0.99,
                        },
                        {
                            "category": "Brand Duplicates",
                            "action": "replace_brand",
                            "brand_name": None,
                            "product_name": None,
                            "wrong_name": "耐克",
                            "correct_name": "Nike",
                            "reason": "normalize name",
                            "evidence_quote_zh": "耐克",
                            "confidence_level": "HIGH",
                            "confidence_score_0_1": 0.8,
                        },
                    ],
                }
            ],
            10,
            20,
        )

    monkeypatch.setattr("services.ai_corrections.execution.build_run_inspector_export", lambda *args, **kwargs: run_export)
    monkeypatch.setattr("services.ai_corrections.execution.run_audit_batches", fake_run_audit_batches)

    from services.ai_corrections.model_selection import ResolvedAuditModel

    monkeypatch.setattr(
        "api.routers.ai_corrections.resolve_audit_model",
        lambda *args, **kwargs: ResolvedAuditModel(
            requested_provider="deepseek",
            requested_model="deepseek-reasoner",
            resolved_provider="deepseek",
            resolved_model="deepseek-reasoner",
            resolved_route="vendor",
        ),
    )

    resp = client.post(f"/api/v1/tracking/runs/{run.id}/ai-corrections", json={"dry_run": True})
    assert resp.status_code == 200
    audit = resp.json()
    assert audit["run_id"] == run.id
    assert audit["audit_id"] > 0

    report = client.get(f"/api/v1/tracking/runs/{run.id}/ai-corrections/{audit['audit_id']}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["run_id"] == run.id
    assert body["brands"]["precision"] == pytest.approx(1.0)
    assert len(body["pending_review_items"]) == 1
    assert body["pending_review_items"][0]["run_id"] == run.id

    item_id = body["pending_review_items"][0]["id"]
    apply_resp = client.post(
        f"/api/v1/tracking/runs/{run.id}/ai-corrections/{audit['audit_id']}/review-items/{item_id}/apply"
    )
    assert apply_resp.status_code == 200


def test_ai_corrections_persists_auto_applied_items_as_applied(client, db_session, knowledge_db_session, monkeypatch):
    from models import Run, RunStatus, Vertical
    from models.knowledge_domain import KnowledgeAIAuditReviewItem, KnowledgeAIAuditReviewStatus

    vertical = Vertical(name="sportswear", description=None)
    db_session.add(vertical)
    db_session.commit()

    run = Run(
        vertical_id=vertical.id,
        provider="qwen",
        model_name="qwen2",
        status=RunStatus.COMPLETED,
        reuse_answers=False,
        web_search_enabled=False,
    )
    db_session.add(run)
    db_session.commit()

    run_export = [
        {
            "run_id": run.id,
            "llm_answer_id": 10,
            "vertical_name": vertical.name,
            "model": "qwen2",
            "prompt_zh": "推荐运动鞋品牌",
            "prompt_eng": "Recommend sports shoe brands",
            "prompt_response_zh": "耐克是一个品牌。",
            "prompt_response_en": None,
            "brands_extracted": [],
        }
    ]

    async def fake_run_audit_batches(*args, **kwargs):
        return (
            [
                {
                    "llm_answer_id": 10,
                    "truth": {"brands": ["耐克"], "products": [], "mappings": []},
                    "suggestions": [
                        {
                            "category": "Missed Brand",
                            "action": "validate_brand",
                            "brand_name": "耐克",
                            "product_name": None,
                            "wrong_name": None,
                            "correct_name": None,
                            "reason": "brand explicitly mentioned",
                            "evidence_quote_zh": "耐克",
                            "confidence_level": "VERY_HIGH",
                            "confidence_score_0_1": 0.99,
                        }
                    ],
                }
            ],
            10,
            20,
        )

    monkeypatch.setattr("services.ai_corrections.execution.build_run_inspector_export", lambda *args, **kwargs: run_export)
    monkeypatch.setattr("services.ai_corrections.execution.run_audit_batches", fake_run_audit_batches)

    from services.ai_corrections.model_selection import ResolvedAuditModel

    monkeypatch.setattr(
        "api.routers.ai_corrections.resolve_audit_model",
        lambda *args, **kwargs: ResolvedAuditModel(
            requested_provider="deepseek",
            requested_model="deepseek-reasoner",
            resolved_provider="deepseek",
            resolved_model="deepseek-reasoner",
            resolved_route="vendor",
        ),
    )

    resp = client.post(f"/api/v1/tracking/runs/{run.id}/ai-corrections", json={"dry_run": False})
    assert resp.status_code == 200
    audit = resp.json()

    applied = knowledge_db_session.query(KnowledgeAIAuditReviewItem).filter(
        KnowledgeAIAuditReviewItem.audit_run_id == int(audit["audit_id"]),
        KnowledgeAIAuditReviewItem.status == KnowledgeAIAuditReviewStatus.APPLIED,
    ).all()
    assert len(applied) == 1
    assert applied[0].applied_at is not None
