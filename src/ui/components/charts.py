from collections import Counter

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render_positioning_matrix(df: pd.DataFrame, name_col: str, user_brand: str = None) -> None:
    if df.empty:
        st.info("No data available for positioning matrix.")
        return

    competitor_df = df[df[name_col] != user_brand] if user_brand else df
    fig = px.scatter(
        competitor_df,
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

    if user_brand and user_brand in df[name_col].values:
        user_row = df[df[name_col] == user_brand].iloc[0]
        fig.add_trace(go.Scatter(
            x=[user_row["share_of_voice"]],
            y=[user_row["sentiment_index"]],
            mode="markers+text",
            marker=dict(
                size=max(12, user_row["mention_rate"] * 200),
                color="#2ca02c",
                symbol="star",
                line=dict(width=2, color="white"),
            ),
            text=[user_brand],
            textposition="top center",
            textfont=dict(size=12, color="#2ca02c"),
            name=f"★ {user_brand}",
            customdata=[[
                user_row["mention_rate"],
                user_row["top_spot_share"],
                user_row["dragon_lens_visibility"],
            ]],
            hovertemplate=(
                f"<b>{user_brand}</b><br>"
                "Share of Voice: %{x:.3f}<br>"
                "Sentiment Index: %{y:.3f}<br>"
                "Mention Rate: %{customdata[0]:.3f}<br>"
                "Top Spot Share: %{customdata[1]:.3f}<br>"
                "Visibility: %{customdata[2]:.3f}<extra></extra>"
            ),
        ))

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


def render_model_heatmap(
    rows: list[dict],
    user_entity: str | None = None,
) -> None:
    if not rows:
        return

    pivot, x_labels = _build_heatmap_matrix(rows)

    if user_entity and user_entity in pivot.index:
        other_entities = [entity for entity in pivot.index if entity != user_entity]
        pivot = pivot.loc[[user_entity] + other_entities]

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=x_labels,
        y=pivot.index.tolist(),
        text=[[f"{v}%" for v in row] for row in pivot.values.astype(int)],
        texttemplate="%{text}",
        textfont={"size": 13},
        colorscale=[[0, "#ef4444"], [0.3, "#fbbf24"], [0.6, "#22c55e"], [1, "#15803d"]],
        zmin=0,
        zmax=100,
        colorbar=dict(title="SoV %", ticksuffix="%"),
        hoverongaps=False,
    ))

    fig.update_layout(
        title="Share of Voice Across LLMs",
        xaxis_title="",
        yaxis_title="",
        height=max(200, 50 * len(pivot.index) + 100),
        yaxis=dict(autorange="reversed"),
    )

    st.plotly_chart(fig, use_container_width=True)


def _build_heatmap_matrix(rows: list[dict]) -> tuple[pd.DataFrame, list[str]]:
    df = pd.DataFrame(rows)
    if "model_label" not in df.columns:
        df["model_label"] = df["model"]

    model_frame = df[["model", "model_label"]].drop_duplicates()
    display_labels = _build_display_labels(model_frame)
    pivot = df.pivot_table(
        index="entity",
        columns="model",
        values="sov",
        aggfunc="first",
        fill_value=0,
    )
    ordered_models = model_frame["model"].tolist()
    pivot = pivot.reindex(columns=ordered_models)
    return pivot, [display_labels[model_name] for model_name in pivot.columns]


def _build_display_labels(model_frame: pd.DataFrame) -> dict[str, str]:
    labels = model_frame["model_label"].tolist()
    counts = Counter(labels)
    display_labels: dict[str, str] = {}
    for row in model_frame.itertuples(index=False):
        if counts[row.model_label] == 1:
            display_labels[row.model] = row.model_label
        else:
            display_labels[row.model] = f"{row.model_label} ({row.model})"
    return display_labels
