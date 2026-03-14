def test_vertical_ai_corrections_flow_creates_report_and_review_items(client, db_session, monkeypatch):
    from models import Run, RunStatus, Vertical

    vertical = Vertical(name="cars", description=None)
    db_session.add(vertical)
    db_session.commit()

    run1 = Run(
        vertical_id=vertical.id,
        provider="qwen",
        model_name="qwen2",
        status=RunStatus.COMPLETED,
        reuse_answers=False,
        web_search_enabled=False,
    )
    run2 = Run(
        vertical_id=vertical.id,
        provider="qwen",
        model_name="qwen2",
        status=RunStatus.COMPLETED,
        reuse_answers=False,
        web_search_enabled=False,
    )
    db_session.add_all([run1, run2])
    db_session.commit()

    vertical_export = [
        {
            "run_id": run1.id,
            "llm_answer_id": 10,
            "vertical_name": vertical.name,
            "model": "qwen2",
            "prompt_zh": "推荐汽车品牌",
            "prompt_eng": "Recommend car brands",
            "prompt_response_zh": "比亚迪是一个品牌。",
            "prompt_response_en": None,
            "brands_extracted": [],
        },
        {
            "run_id": run2.id,
            "llm_answer_id": 11,
            "vertical_name": vertical.name,
            "model": "qwen2",
            "prompt_zh": "推荐SUV品牌",
            "prompt_eng": "Recommend SUV brands",
            "prompt_response_zh": "特斯拉是一个品牌。",
            "prompt_response_en": None,
            "brands_extracted": [],
        },
    ]

    async def fake_run_audit_batches(*args, **kwargs):
        return (
            [
                {
                    "llm_answer_id": 10,
                    "truth": {"brands": [], "products": [], "mappings": []},
                    "suggestions": [
                        {
                            "category": "Brand Duplicates",
                            "action": "replace_brand",
                            "brand_name": None,
                            "product_name": None,
                            "wrong_name": "比亚迪",
                            "correct_name": "BYD",
                            "reason": "normalize name",
                            "evidence_quote_zh": "比亚迪",
                            "confidence_level": "LOW",
                            "confidence_score_0_1": 0.2,
                        }
                    ],
                },
                {
                    "llm_answer_id": 11,
                    "truth": {"brands": [], "products": [], "mappings": []},
                    "suggestions": [
                        {
                            "category": "Brand Duplicates",
                            "action": "replace_brand",
                            "brand_name": None,
                            "product_name": None,
                            "wrong_name": "特斯拉",
                            "correct_name": "Tesla",
                            "reason": "normalize name",
                            "evidence_quote_zh": "特斯拉",
                            "confidence_level": "LOW",
                            "confidence_score_0_1": 0.2,
                        }
                    ],
                },
            ],
            10,
            20,
        )

    monkeypatch.setattr(
        "services.ai_corrections.execution.build_vertical_inspector_export",
        lambda *args, **kwargs: vertical_export,
    )
    monkeypatch.setattr("services.ai_corrections.execution.run_audit_batches", fake_run_audit_batches)

    from services.ai_corrections.model_selection import ResolvedAuditModel

    monkeypatch.setattr(
        "api.routers.verticals.resolve_audit_model",
        lambda *args, **kwargs: ResolvedAuditModel(
            requested_provider="deepseek",
            requested_model="deepseek-reasoner",
            resolved_provider="deepseek",
            resolved_model="deepseek-reasoner",
            resolved_route="vendor",
        ),
    )

    resp = client.post(f"/api/v1/verticals/{vertical.id}/ai-corrections", json={"dry_run": False})
    assert resp.status_code == 200
    audit = resp.json()
    assert audit["run_id"] == 0
    assert audit["dry_run"] is True

    report = client.get(f"/api/v1/verticals/{vertical.id}/ai-corrections/{audit['audit_id']}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["run_id"] == 0
    assert len(body["pending_review_items"]) == 2
    run_ids = {i["run_id"] for i in body["pending_review_items"]}
    assert run_ids == {run1.id, run2.id}

    item_id = body["pending_review_items"][0]["id"]
    apply_resp = client.post(
        f"/api/v1/verticals/{vertical.id}/ai-corrections/{audit['audit_id']}/review-items/{item_id}/apply"
    )
    assert apply_resp.status_code == 200
