from services.comparison_prompts.generation import (
    build_product_comparison_prompt_generation_prompt,
)


def test_build_product_comparison_prompt_generation_prompt_includes_pairs():
    prompt = build_product_comparison_prompt_generation_prompt(
        [
            {
                "primary_brand": "A",
                "primary_product": "A1",
                "competitor_brand": "B",
                "competitor_product": "B1",
            }
        ]
    )
    assert "A1" in prompt
    assert "B1" in prompt
