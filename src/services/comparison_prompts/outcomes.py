from models import ComparisonEntityRole, Sentiment


def score_for_sentiment(sentiment: Sentiment) -> int:
    if sentiment == Sentiment.POSITIVE:
        return 1
    if sentiment == Sentiment.NEGATIVE:
        return -1
    return 0


def outcome_for_role_sentiments(items: list[tuple[ComparisonEntityRole, Sentiment]]) -> str:
    present = {r for r, _ in items}
    if ComparisonEntityRole.PRIMARY not in present or ComparisonEntityRole.COMPETITOR not in present:
        return "unknown"
    primary = sum(score_for_sentiment(s) for r, s in items if r == ComparisonEntityRole.PRIMARY)
    competitor = sum(score_for_sentiment(s) for r, s in items if r == ComparisonEntityRole.COMPETITOR)
    if primary == competitor:
        return "tie"
    return "primary" if primary > competitor else "competitor"

