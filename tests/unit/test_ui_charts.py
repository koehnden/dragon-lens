from ui.components.charts import _build_heatmap_matrix


def test_build_heatmap_matrix_keeps_distinct_models_with_same_short_label() -> None:
    pivot, x_labels = _build_heatmap_matrix(
        [
            {
                "model": "kimi-k2.5",
                "model_label": "Kimi K2.5",
                "entity": "Toyota",
                "sov": 40,
            },
            {
                "model": "moonshotai/kimi-k2.5",
                "model_label": "Kimi K2.5",
                "entity": "Toyota",
                "sov": 65,
            },
        ]
    )

    assert pivot.columns.tolist() == ["kimi-k2.5", "moonshotai/kimi-k2.5"]
    assert pivot.loc["Toyota", "kimi-k2.5"] == 40
    assert pivot.loc["Toyota", "moonshotai/kimi-k2.5"] == 65
    assert x_labels == [
        "Kimi K2.5 (kimi-k2.5)",
        "Kimi K2.5 (moonshotai/kimi-k2.5)",
    ]
