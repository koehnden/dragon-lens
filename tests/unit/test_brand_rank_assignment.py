import pytest


@pytest.mark.asyncio
async def test_extract_brands_rank_list_position():
    from services.ollama import OllamaService

    service = OllamaService.__new__(OllamaService)
    text = "1. 奔驰GLE\n2. 宝马X5\n3. 奥迪Q7"
    mentions = await OllamaService.extract_brands(service, text, ["奔驰", "宝马", "奥迪"], [[], [], []])
    ranks = {m["brand_index"]: m["rank"] for m in mentions if m["mentioned"]}
    assert ranks[0] == 1
    assert ranks[1] == 2
    assert ranks[2] == 3


@pytest.mark.asyncio
async def test_extract_brands_rank_first_occurrence():
    from services.ollama import OllamaService

    service = OllamaService.__new__(OllamaService)
    text = "宝马更好一些，奔驰也不错。"
    mentions = await OllamaService.extract_brands(service, text, ["奔驰", "宝马"], [[], []])
    ranks = {m["brand_index"]: m["rank"] for m in mentions if m["mentioned"]}
    assert ranks[1] == 1
    assert ranks[0] == 2


@pytest.mark.asyncio
async def test_extract_brands_rank_caps_at_10():
    from services.ollama import OllamaService

    service = OllamaService.__new__(OllamaService)
    text = "\n".join([f"- item{i}" for i in range(1, 12)]) + "\n- 奔驰"
    mentions = await OllamaService.extract_brands(service, text, ["奔驰"], [[]])
    benz = next(m for m in mentions if m["brand_index"] == 0)
    assert benz["rank"] == 10

