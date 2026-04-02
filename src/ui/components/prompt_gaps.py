import pandas as pd
import streamlit as st

from ui.utils.api import fetch_json


def _build_prompt_coverage(run_details: dict, user_brand: str) -> pd.DataFrame:
    rows: list[dict] = []
    for answer in run_details.get("answers") or []:
        prompt_text = answer.get("prompt_text_en") or answer.get("prompt_text_zh") or ""
        if not prompt_text:
            continue

        mentions = answer.get("mentions") or []
        brand_mentions = [
            m for m in mentions
            if m.get("brand_name") == user_brand and m.get("mentioned")
        ]

        if brand_mentions:
            best = min(brand_mentions, key=lambda m: m.get("rank") or 999)
            rows.append({
                "Prompt": prompt_text[:120],
                "Status": "Visible",
                "Rank": best.get("rank"),
                "Sentiment": (best.get("sentiment") or "").capitalize(),
            })
        else:
            rows.append({
                "Prompt": prompt_text[:120],
                "Status": "Gap",
                "Rank": None,
                "Sentiment": "-",
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(
        by=["Status", "Rank"],
        ascending=[False, True],
        na_position="first",
    )
    return df.reset_index(drop=True)


def render_prompt_gaps(run_id: int, user_brand: str | None) -> None:
    if not user_brand:
        st.info("Select a brand to see prompt coverage.")
        return

    run_details = fetch_json(f"/api/v1/tracking/runs/{run_id}/details")
    if not run_details:
        st.info("Run details not available.")
        return

    df = _build_prompt_coverage(run_details, user_brand)
    if df.empty:
        st.info("No prompt data available for this run.")
        return

    total = len(df)
    visible = (df["Status"] == "Visible").sum()
    gaps = total - visible

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Prompts", total)
    with col2:
        st.metric("Visible In", f"{visible} ({visible * 100 // total}%)")
    with col3:
        st.metric("Gaps", gaps, delta=f"-{gaps}" if gaps > 0 else "0", delta_color="inverse")

    def _highlight_gaps(row: pd.Series) -> list[str]:
        if row["Status"] == "Gap":
            return ["background-color: #fef2f2; color: #991b1b"] * len(row)
        return ["background-color: #f0fdf4; color: #166534"] * len(row)

    styled = df.style.apply(_highlight_gaps, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=min(500, 35 * total + 38))
