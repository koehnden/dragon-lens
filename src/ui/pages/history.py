import httpx
import pandas as pd
import streamlit as st

from config import settings


def show():
    st.title("📜 Runs History")
    st.write("View all tracking runs and their status")

    col1, col2 = st.columns(2)

    with col1:
        try:
            response = httpx.get(
                f"http://localhost:{settings.api_port}/api/v1/verticals",
                timeout=10.0,
            )
            response.raise_for_status()
            verticals = response.json()

            vertical_options = {"All": None}
            vertical_options.update({v["name"]: v["id"] for v in verticals})

            selected_vertical_name = st.selectbox("Filter by Vertical", list(vertical_options.keys()))
            vertical_filter = vertical_options[selected_vertical_name]

        except httpx.HTTPError:
            st.warning("Could not load verticals")
            vertical_filter = None

    with col2:
        model_filter = st.selectbox("Filter by Model", ["All", "qwen", "deepseek", "kimi", "openrouter"])
        if model_filter == "All":
            model_filter = None

    try:
        params = {}
        if vertical_filter:
            params["vertical_id"] = vertical_filter
        if model_filter:
            params["model_name"] = model_filter

        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/tracking/runs",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        runs = response.json()

        if not runs:
            st.info("ℹ️ No runs found matching the filters.")
            return

        df = pd.DataFrame(runs)

        st.markdown("### Summary")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Runs", len(df))

        with col2:
            completed = (df["status"] == "completed").sum()
            st.metric("Completed", completed)

        with col3:
            failed = (df["status"] == "failed").sum()
            st.metric("Failed", failed)

        with col4:
            in_progress = (df["status"] == "in_progress").sum()
            st.metric("In Progress", in_progress)

        def color_status(status):
            if status == "completed":
                return "🟢"
            elif status == "in_progress":
                return "🟡"
            elif status == "failed":
                return "🔴"
            else:
                return "⚪"

        st.markdown("### Recent Runs")

        display_df = df.copy()
        display_df["status_icon"] = display_df["status"].apply(color_status)
        display_df = display_df[[
            "id",
            "status_icon",
            "status",
            "vertical_id",
            "model_name",
            "run_time",
            "completed_at",
        ]]
        display_df.columns = [
            "Run ID",
            "",
            "Status",
            "Vertical ID",
            "Model",
            "Started At",
            "Completed At",
        ]

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### Run Details")
        run_id = st.number_input("Enter Run ID to view details", min_value=1, step=1)

        if st.button("Load Run Details"):
            try:
                response = httpx.get(
                    f"http://localhost:{settings.api_port}/api/v1/tracking/runs/{run_id}",
                    timeout=10.0,
                )
                response.raise_for_status()
                run_details = response.json()

                col1, col2 = st.columns(2)

                with col1:
                    st.json({
                        "Run ID": run_details["id"],
                        "Vertical ID": run_details["vertical_id"],
                        "Model": run_details["model_name"],
                        "Status": run_details["status"],
                    })

                with col2:
                    st.json({
                        "Started": run_details["run_time"],
                        "Completed": run_details["completed_at"],
                        "Error": run_details["error_message"] or "None",
                    })

            except httpx.HTTPError as e:
                if hasattr(e, "response") and e.response and e.response.status_code == 404:
                    st.error(f"❌ Run {run_id} not found")
                else:
                    st.error(f"❌ Error fetching run details: {e}")

    except httpx.HTTPError as e:
        st.error(f"❌ Error fetching runs: {e}")
        if hasattr(e, "response") and e.response:
            st.error(f"Details: {e.response.text}")
    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")
