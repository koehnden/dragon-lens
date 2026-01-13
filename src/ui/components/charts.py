import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render_positioning_matrix(df: pd.DataFrame, name_col: str, user_brand: str = None) -> None:
    if df.empty:
        st.info("No data available for positioning matrix.")
        return

    fig = px.scatter(
        df,
        x="share_of_voice",
        y="sentiment_index",
        size="mention_rate",
        color=name_col,
        hover_data=["mention_rate", "top_spot_share", "dragon_lens_visibility"],
        labels={
            "share_of_voice": "Share of Voice",
            "sentiment_index": "Sentiment Index",
            "mention_rate": "Mention Rate",
            name_col: "Brand" if name_col == "brand_name" else "Product",
        },
        size_max=50,
    )

    median_sov = df["share_of_voice"].median()
    median_sentiment = df["sentiment_index"].median()

    fig.add_hline(y=median_sentiment, line_dash="dash", line_color="gray", opacity=0.5)
    fig.add_vline(x=median_sov, line_dash="dash", line_color="gray", opacity=0.5)

    x_range = [df["share_of_voice"].min() - 0.05, df["share_of_voice"].max() + 0.05]
    y_range = [df["sentiment_index"].min() - 0.1, df["sentiment_index"].max() + 0.1]

    fig.add_annotation(
        x=x_range[1], y=y_range[1], text="Leaders", showarrow=False,
        font=dict(size=12, color="green"), xanchor="right", yanchor="top",
    )
    fig.add_annotation(
        x=x_range[0], y=y_range[1], text="Niche Favorites", showarrow=False,
        font=dict(size=12, color="blue"), xanchor="left", yanchor="top",
    )
    fig.add_annotation(
        x=x_range[1], y=y_range[0], text="Controversial", showarrow=False,
        font=dict(size=12, color="orange"), xanchor="right", yanchor="bottom",
    )
    fig.add_annotation(
        x=x_range[0], y=y_range[0], text="Underperformers", showarrow=False,
        font=dict(size=12, color="red"), xanchor="left", yanchor="bottom",
    )

    fig.update_layout(
        title="Competitive Positioning Matrix",
        xaxis_title="Share of Voice",
        yaxis_title="Sentiment Index",
        showlegend=True,
        height=500,
    )

    st.plotly_chart(fig, use_container_width=True)


def render_sov_treemap(df: pd.DataFrame, name_col: str) -> None:
    if df.empty or df["share_of_voice"].sum() == 0:
        st.info("No share of voice data available.")
        return

    chart_df = df[df["share_of_voice"] > 0].copy()
    if chart_df.empty:
        st.info("No brands with share of voice > 0.")
        return

    fig = px.treemap(
        chart_df,
        path=[name_col],
        values="share_of_voice",
        color="sentiment_index",
        color_continuous_scale=["#d62728", "#ffcc00", "#2ca02c"],
        color_continuous_midpoint=0,
        hover_data=["mention_rate", "top_spot_share"],
        labels={
            name_col: "Brand" if name_col == "brand_name" else "Product",
            "share_of_voice": "Share of Voice",
            "sentiment_index": "Sentiment",
        },
    )

    fig.update_layout(
        title="Share of Voice Distribution",
        height=400,
    )

    st.plotly_chart(fig, use_container_width=True)


def render_sov_bar_chart(df: pd.DataFrame, name_col: str, user_brand: str = None) -> None:
    if df.empty:
        st.info("No share of voice data available.")
        return

    chart_df = df.sort_values("share_of_voice", ascending=True).copy()
    chart_df["sov_pct"] = chart_df["share_of_voice"] * 100

    colors = ["#1f77b4"] * len(chart_df)
    if user_brand:
        for i, name in enumerate(chart_df[name_col]):
            if name == user_brand:
                colors[i] = "#2ca02c"

    fig = go.Figure(go.Bar(
        x=chart_df["sov_pct"],
        y=chart_df[name_col],
        orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}%" for v in chart_df["sov_pct"]],
        textposition="outside",
    ))

    fig.update_layout(
        title="Share of Voice Ranking",
        xaxis_title="Share of Voice (%)",
        yaxis_title="",
        height=max(300, len(chart_df) * 40),
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True)


def render_radar_chart(df: pd.DataFrame, name_col: str, selected_brands: list[str] = None) -> None:
    if df.empty:
        st.info("No data available for radar chart.")
        return

    if selected_brands is None:
        selected_brands = df.nlargest(3, "dragon_lens_visibility")[name_col].tolist()

    metrics = ["mention_rate", "share_of_voice", "top_spot_share", "sentiment_index", "dragon_lens_visibility"]
    metric_labels = ["Mention Rate", "Share of Voice", "Top Spot", "Sentiment", "DVS"]

    chart_df = df[df[name_col].isin(selected_brands)].copy()
    if chart_df.empty:
        st.info("No data for selected brands.")
        return

    for metric in metrics:
        max_val = df[metric].max()
        if max_val > 0:
            chart_df[f"{metric}_norm"] = chart_df[metric] / max_val
        else:
            chart_df[f"{metric}_norm"] = 0

    fig = go.Figure()

    for _, row in chart_df.iterrows():
        values = [row[f"{m}_norm"] for m in metrics]
        values.append(values[0])

        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=metric_labels + [metric_labels[0]],
            fill="toself",
            name=row[name_col],
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        title="Metrics Comparison Radar",
        showlegend=True,
        height=450,
    )

    st.plotly_chart(fig, use_container_width=True)


def render_sentiment_breakdown(df: pd.DataFrame, name_col: str) -> None:
    if df.empty:
        st.info("No sentiment data available.")
        return

    chart_df = df.sort_values("dragon_lens_visibility", ascending=False).head(10).copy()

    def classify_sentiment(val):
        if val > 0.3:
            return "Positive"
        elif val < -0.3:
            return "Negative"
        else:
            return "Neutral"

    chart_df["sentiment_label"] = chart_df["sentiment_index"].apply(classify_sentiment)

    color_map = {"Positive": "#2ca02c", "Neutral": "#ffcc00", "Negative": "#d62728"}

    fig = px.bar(
        chart_df,
        x="sentiment_index",
        y=name_col,
        orientation="h",
        color="sentiment_label",
        color_discrete_map=color_map,
        labels={
            name_col: "Brand" if name_col == "brand_name" else "Product",
            "sentiment_index": "Sentiment Index",
            "sentiment_label": "Sentiment",
        },
    )

    fig.add_vline(x=0, line_dash="solid", line_color="gray", opacity=0.5)

    fig.update_layout(
        title="Sentiment Breakdown",
        xaxis_title="Sentiment Index (-1 to +1)",
        yaxis_title="",
        height=max(300, len(chart_df) * 35),
        showlegend=True,
    )

    st.plotly_chart(fig, use_container_width=True)


def render_metrics_comparison_bar(df: pd.DataFrame, name_col: str) -> None:
    if df.empty:
        st.info("No data available for metrics comparison.")
        return

    chart_df = df.nlargest(8, "dragon_lens_visibility").copy()

    metrics = {
        "mention_rate": "Mention Rate",
        "share_of_voice": "Share of Voice",
        "top_spot_share": "Top Spot Share",
        "dragon_lens_visibility": "DVS",
    }

    fig = go.Figure()

    for metric, label in metrics.items():
        fig.add_trace(go.Bar(
            name=label,
            y=chart_df[name_col],
            x=chart_df[metric] * 100 if metric != "dragon_lens_visibility" else chart_df[metric] * 100,
            orientation="h",
        ))

    fig.update_layout(
        barmode="group",
        title="Metrics Comparison",
        xaxis_title="Score (%)",
        yaxis_title="",
        height=max(350, len(chart_df) * 50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_feature_spider_chart(
    data: dict,
    selected_entities: list[str] = None,
    max_entities: int = 5,
) -> None:
    if not data or not data.get("entities"):
        st.info("No feature data available for comparison.")
        return

    feature_axes = data.get("top_features", [])
    entities_data = data.get("entities", [])

    if not feature_axes:
        st.info("No features found for comparison.")
        return

    if selected_entities:
        entities_data = [e for e in entities_data if e["entity_name"] in selected_entities]

    entities_data = entities_data[:max_entities]

    if not entities_data:
        st.info("No entities selected for comparison.")
        return

    max_scores = {}
    for entity in entities_data:
        for feature in entity.get("features", []):
            name = feature["feature_name_zh"]
            score = feature["combined_score"]
            max_scores[name] = max(max_scores.get(name, 0), score)

    fig = go.Figure()

    colors = px.colors.qualitative.Set2

    for idx, entity in enumerate(entities_data):
        feature_map = {f["feature_name_zh"]: f for f in entity.get("features", [])}

        values = []
        for feature_name in feature_axes:
            feature = feature_map.get(feature_name, {})
            score = feature.get("combined_score", 0)
            max_val = max_scores.get(feature_name, 1)
            normalized = score / max_val if max_val > 0 else 0
            values.append(normalized)

        values.append(values[0])
        theta = feature_axes + [feature_axes[0]]

        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=theta,
            fill="toself",
            name=entity["entity_name"],
            line_color=colors[idx % len(colors)],
            fillcolor=colors[idx % len(colors)],
            opacity=0.6,
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                tickformat=".0%",
            ),
        ),
        title="Feature Comparison Spider Chart",
        showlegend=True,
        height=500,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_feature_table(data: dict) -> None:
    if not data or not data.get("entities"):
        return

    entities_data = data.get("entities", [])
    feature_axes = data.get("top_features", [])

    if not entities_data or not feature_axes:
        return

    rows = []
    for entity in entities_data:
        row = {"Entity": entity["entity_name"]}
        feature_map = {f["feature_name_zh"]: f for f in entity.get("features", [])}

        for feature_name in feature_axes:
            feature = feature_map.get(feature_name, {})
            score = feature.get("combined_score", 0)
            freq = feature.get("frequency", 0)
            row[feature_name] = f"{score:.1f} ({freq})"

        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
