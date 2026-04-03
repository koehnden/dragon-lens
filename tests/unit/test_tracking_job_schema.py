from models.schemas import TrackingJobCreate


def test_tracking_job_defaults_to_deepseek_visibility_model():
    job = TrackingJobCreate(
        vertical_name="SUV Cars",
        prompts=[{"text_zh": "推荐几款值得购买的SUV", "language_original": "zh"}],
    )

    assert job.provider == "deepseek"
    assert job.model_name == "deepseek-chat"
