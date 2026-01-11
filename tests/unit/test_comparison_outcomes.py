from models import ComparisonEntityRole, Sentiment


def test_outcome_unknown_when_one_side_missing():
    from services.comparison_prompts.outcomes import outcome_for_role_sentiments

    outcome = outcome_for_role_sentiments([(ComparisonEntityRole.PRIMARY, Sentiment.POSITIVE)])
    assert outcome == "unknown"


def test_outcome_tie_when_scores_equal():
    from services.comparison_prompts.outcomes import outcome_for_role_sentiments

    outcome = outcome_for_role_sentiments([
        (ComparisonEntityRole.PRIMARY, Sentiment.POSITIVE),
        (ComparisonEntityRole.COMPETITOR, Sentiment.POSITIVE),
    ])
    assert outcome == "tie"


def test_outcome_primary_when_primary_score_higher():
    from services.comparison_prompts.outcomes import outcome_for_role_sentiments

    outcome = outcome_for_role_sentiments([
        (ComparisonEntityRole.PRIMARY, Sentiment.POSITIVE),
        (ComparisonEntityRole.COMPETITOR, Sentiment.NEGATIVE),
    ])
    assert outcome == "primary"


def test_outcome_competitor_when_competitor_score_higher():
    from services.comparison_prompts.outcomes import outcome_for_role_sentiments

    outcome = outcome_for_role_sentiments([
        (ComparisonEntityRole.PRIMARY, Sentiment.NEUTRAL),
        (ComparisonEntityRole.COMPETITOR, Sentiment.POSITIVE),
    ])
    assert outcome == "competitor"

