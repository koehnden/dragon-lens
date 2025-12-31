import pytest


@pytest.mark.asyncio
async def test_extract_products_masks_other_products_and_brands_in_snippets():
    from services.ollama import OllamaService

    service = OllamaService.__new__(OllamaService)
    text = "1. Toyota RAV4很好，但Honda CR-V一般"

    products = ["RAV4", "CR-V"]
    product_aliases = [["RAV4"], ["CR-V", "CRV"]]
    brands = ["Toyota", "Honda"]
    brand_aliases = [["丰田"], ["本田"]]

    mentions = await OllamaService.extract_products(
        service, text, products, product_aliases, brands, brand_aliases
    )

    rav4 = next(m for m in mentions if m["product_index"] == 0)
    assert rav4["mentioned"] is True
    assert rav4["rank"] == 1
    assert rav4["snippets"]
    snippet = rav4["snippets"][0]
    assert "RAV4" in snippet
    assert "CR-V" not in snippet or "[PRODUCT]" in snippet
    assert "Toyota" not in snippet or "[BRAND]" in snippet
    assert "Honda" not in snippet or "[BRAND]" in snippet


@pytest.mark.asyncio
async def test_extract_products_rank_first_occurrence_non_list():
    from services.ollama import OllamaService

    service = OllamaService.__new__(OllamaService)
    text = "CR-V一般，但RAV4不错。"
    products = ["RAV4", "CR-V"]
    product_aliases = [["RAV4"], ["CR-V"]]

    mentions = await OllamaService.extract_products(
        service, text, products, product_aliases, [], []
    )

    ranks = {m["product_index"]: m["rank"] for m in mentions if m["mentioned"]}
    assert ranks[1] == 1
    assert ranks[0] == 2

