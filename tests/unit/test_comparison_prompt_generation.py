from services.comparison_prompts.generation import build_comparison_prompt_generation_prompt


def test_build_comparison_prompt_generation_prompt_includes_context_and_count():
    prompt = build_comparison_prompt_generation_prompt({"primary_brand": "A"}, 3)
    assert "primary_brand" in prompt
    assert "3" in prompt
