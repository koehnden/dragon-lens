import streamlit as st


def show() -> None:
    st.title("DragonLens Demo")
    st.caption("Chinese-market GEO visibility tracking across multiple LLMs")

    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(
            """
            DragonLens measures how Chinese LLMs talk about brands and products.

            This public demo is intentionally read-only. It showcases curated verticals,
            completed runs, bilingual answers, and the resulting visibility metrics.
            """
        )
    with col2:
        st.info(
            "Use the sidebar to explore results, inspect raw prompts and answers, "
            "and review historical runs."
        )

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Mode", "Read-only")
    with col2:
        st.metric("Surface", "Demo verticals")
    with col3:
        st.metric("Pipeline", "Local-first")

    st.markdown("---")
    st.subheader("What To Look For")
    st.markdown(
        """
        - Results shows brand and product visibility scores derived from completed runs.
        - Run Inspector exposes the raw bilingual prompts, answers, and extracted mentions.
        - Runs History shows the completed run inventory behind the demo.
        """
    )
