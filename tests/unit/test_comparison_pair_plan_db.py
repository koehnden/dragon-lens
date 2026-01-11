from models import Brand, Product, Run, RunMetrics, RunProductMetrics, RunStatus, Vertical
from services.comparison_prompts.run_pipeline import _pair_plan


def test_pair_plan_requires_enough_mapped_competitors(db_session):
    vertical = Vertical(name="V", description=None)
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)
    primary = Brand(vertical_id=vertical.id, display_name="P", original_name="P", translated_name=None, aliases={"zh": [], "en": []})
    db_session.add(primary)
    db_session.commit()
    db_session.refresh(primary)
    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen2.5:7b-instruct-q4_0", status=RunStatus.COMPLETED)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    product_primary = Product(vertical_id=vertical.id, brand_id=primary.id, display_name="P1", original_name="P1", translated_name=None)
    db_session.add(product_primary)
    db_session.commit()
    db_session.refresh(product_primary)
    db_session.add(RunProductMetrics(run_id=run.id, product_id=product_primary.id, mention_rate=0, share_of_voice=0, top_spot_share=0, sentiment_index=0, dragon_lens_visibility=1))
    db_session.commit()
    assert _pair_plan(db_session, run.id, primary.id, 20) == []


def test_pair_plan_builds_20_pairs_with_competitor_cap(db_session):
    vertical = Vertical(name="V2", description=None)
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)
    primary = Brand(vertical_id=vertical.id, display_name="P", original_name="P", translated_name=None, aliases={"zh": [], "en": []})
    competitors = [
        Brand(vertical_id=vertical.id, display_name=f"C{i}", original_name=f"C{i}", translated_name=None, aliases={"zh": [], "en": []})
        for i in range(7)
    ]
    db_session.add_all([primary, *competitors])
    db_session.commit()
    db_session.refresh(primary)
    for c in competitors:
        db_session.refresh(c)
    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen2.5:7b-instruct-q4_0", status=RunStatus.COMPLETED)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    products = [Product(vertical_id=vertical.id, brand_id=primary.id, display_name="P1", original_name="P1", translated_name=None)]
    products += [
        Product(vertical_id=vertical.id, brand_id=c.id, display_name=f"{c.display_name}-1", original_name=f"{c.display_name}-1", translated_name=None)
        for c in competitors
    ]
    db_session.add_all(products)
    db_session.commit()
    for p in products:
        db_session.refresh(p)
    metrics = [RunProductMetrics(run_id=run.id, product_id=p.id, mention_rate=0, share_of_voice=0, top_spot_share=0, sentiment_index=0, dragon_lens_visibility=1) for p in products]
    db_session.add_all(metrics)
    brand_metrics = [RunMetrics(run_id=run.id, brand_id=c.id, mention_rate=0, share_of_voice=0, top_spot_share=0, sentiment_index=0, dragon_lens_visibility=1) for c in competitors]
    db_session.add_all(brand_metrics)
    db_session.commit()
    plan = _pair_plan(db_session, run.id, primary.id, 20)
    assert len(plan) == 20
    assert all(int(p["primary_product"].brand_id) == primary.id for p in plan)
    assert all(int(p["competitor_product"].brand_id) != primary.id for p in plan)
    counts = {}
    for p in plan:
        bid = int(p["competitor_product"].brand_id)
        counts[bid] = counts.get(bid, 0) + 1
    assert max(counts.values()) <= 3

