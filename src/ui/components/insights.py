import pandas as pd
import streamlit as st


def generate_insights(df: pd.DataFrame, name_col: str, user_brand: str = None) -> list[dict]:
    insights = []

    if df.empty:
        return insights

    if user_brand and user_brand in df[name_col].values:
        user_data = df[df[name_col] == user_brand].iloc[0]
        user_dvs = user_data["dragon_lens_visibility"]
        user_sov = user_data["share_of_voice"]
        user_sentiment = user_data["sentiment_index"]
        user_mention = user_data["mention_rate"]

        user_rank = (df["dragon_lens_visibility"] > user_dvs).sum() + 1

        if user_rank == 1:
            insights.append({
                "type": "success",
                "message": f"You're the visibility leader with {user_sov*100:.1f}% Share of Voice!",
            })
        elif user_rank <= 3:
            leader = df.nlargest(1, "dragon_lens_visibility").iloc[0]
            gap = leader["share_of_voice"] - user_sov
            insights.append({
                "type": "info",
                "message": f"You're ranked #{user_rank}. Close the {gap*100:.1f}% SoV gap to overtake {leader[name_col]}.",
            })

        avg_sentiment = df["sentiment_index"].mean()
        if user_sentiment < avg_sentiment - 0.2:
            insights.append({
                "type": "warning",
                "message": f"Your sentiment ({user_sentiment:.2f}) is below market average ({avg_sentiment:.2f}).",
            })
        elif user_sentiment > avg_sentiment + 0.2:
            insights.append({
                "type": "success",
                "message": f"Your sentiment ({user_sentiment:.2f}) is above market average ({avg_sentiment:.2f})!",
            })

        if user_mention < 0.5:
            missing_pct = (1 - user_mention) * 100
            insights.append({
                "type": "warning",
                "message": f"You're missing from {missing_pct:.0f}% of prompts. Opportunity to improve coverage.",
            })

    top_performer = df.nlargest(1, "dragon_lens_visibility").iloc[0]
    insights.append({
        "type": "info",
        "message": f"Top performer: {top_performer[name_col]} with DVS of {top_performer['dragon_lens_visibility']*100:.0f}.",
    })

    high_sov_low_sentiment = df[(df["share_of_voice"] > df["share_of_voice"].median()) &
                                 (df["sentiment_index"] < 0)]
    if not high_sov_low_sentiment.empty:
        brand = high_sov_low_sentiment.iloc[0][name_col]
        insights.append({
            "type": "opportunity",
            "message": f"{brand} has high visibility but negative sentiment - potential vulnerability.",
        })

    return insights


def render_insights(df: pd.DataFrame, name_col: str, user_brand: str = None) -> None:
    insights = generate_insights(df, name_col, user_brand)

    if not insights:
        st.info("No insights available. Add more data to generate actionable insights.")
        return

    st.markdown("### Key Insights")

    for insight in insights:
        insight_type = insight["type"]
        message = insight["message"]

        if insight_type == "success":
            st.success(f"**{message}**")
        elif insight_type == "warning":
            st.warning(f"**{message}**")
        elif insight_type == "opportunity":
            st.info(f"**{message}**")
        else:
            st.info(message)
