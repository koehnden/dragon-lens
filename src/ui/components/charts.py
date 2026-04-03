import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.utils.api import api_url, shorten_model_name


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


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_per_model_metrics(
    vertical_id: int, models: tuple[str, ...], view_mode: str,
) -> list[dict]:
    endpoint = "/api/v1/metrics/latest"
    if view_mode == "product":
        endpoint = "/api/v1/metrics/latest/products"
    rows: list[dict] = []
    for model in models:
        try:
            resp = httpx.get(
                api_url(endpoint),
                params={"vertical_id": vertical_id, "model_name": model},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            continue
        items_key = "products" if view_mode == "product" else "brands"
        for item in data.get(items_key) or []:
            name_key = "product_name" if view_mode == "product" else "brand_name"
            rows.append({
                "model": shorten_model_name(model),
                "entity": item[name_key],
                "sov": round(item["share_of_voice"] * 100),
            })
    return rows


def render_model_heatmap(
    vertical_id: int,
    available_models: list[str],
    name_col: str,
    user_brand: str | None = None,
) -> None:
    if not available_models or len(available_models) < 2:
        return

    seen_short: dict[str, str] = {}
    deduped_models: list[str] = []
    for m in available_models:
        short = shorten_model_name(m)
        if short not in seen_short:
            seen_short[short] = m
            deduped_models.append(m)

    view_mode = "product" if name_col == "product_name" else "brand"
    rows = _fetch_per_model_metrics(vertical_id, tuple(deduped_models), view_mode)
    if not rows:
        return

    df = pd.DataFrame(rows)
    pivot = df.pivot_table(index="entity", columns="model", values="sov", fill_value=0)

    model_order = [shorten_model_name(m) for m in deduped_models if shorten_model_name(m) in pivot.columns]
    pivot = pivot[[m for m in model_order if m in pivot.columns]]

    if user_brand and user_brand in pivot.index:
        other_brands = [b for b in pivot.index if b != user_brand]
        pivot = pivot.loc[[user_brand] + other_brands]

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
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
