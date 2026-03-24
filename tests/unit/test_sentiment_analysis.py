import asyncio

import httpx
import pytest
from unittest.mock import MagicMock, AsyncMock
import services.sentiment_analysis as sentiment_module


@pytest.fixture(autouse=True)
def reset_sentiment_singleton():
    sentiment_module._sentiment_client_instance = None
    yield
    sentiment_module._sentiment_client_instance = None


def test_sentiment_client_handles_connection_error():
    from services.sentiment_analysis import SentimentClient

    client = SentimentClient(base_url="http://127.0.0.1:59999")
    mock_http = MagicMock()
    mock_http.post.side_effect = httpx.ConnectError("connection refused")
    client._get_client = MagicMock(return_value=mock_http)

    result = client.classify_sentiment("测试文本")
    assert result == "neutral"


def test_sentiment_client_health_check_fails_gracefully():
    from services.sentiment_analysis import SentimentClient

    client = SentimentClient(base_url="http://127.0.0.1:59999")
    mock_http = MagicMock()
    mock_http.get.side_effect = RuntimeError("service unavailable")
    client._get_client = MagicMock(return_value=mock_http)

    assert client.health_check() is False


def test_brand_isolation_in_extract_brands():
    """Test that extract_brands properly isolates brands to prevent sentiment contamination."""
    from services.ollama import OllamaService

    ollama_service = OllamaService()

    test_text = "奔驰GLE性能出色，但宝马X5的性价比更高，而奥迪Q7的科技配置最好。"
    brand_names = ["奔驰", "宝马", "奥迪"]
    brand_aliases = [[], [], []]

    ollama_service._call_ollama = AsyncMock(return_value="")

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    assert len(mentions) == 3

    for mention in mentions:
        assert mention["mentioned"] is True
        assert len(mention["snippets"]) > 0

        for snippet in mention["snippets"]:
            brand_count = 0
            if "奔驰" in snippet:
                brand_count += 1
            if "宝马" in snippet:
                brand_count += 1
            if "奥迪" in snippet:
                brand_count += 1

            assert brand_count <= 1, f"Snippet contains multiple brands: {snippet}"


def test_brand_isolation_edge_cases():
    """Test brand isolation with edge cases."""
    from services.ollama import OllamaService

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    test_text = "奔驰宝马是最好的组合，奔驰的性能和宝马的操控都很出色。"
    brand_names = ["奔驰", "宝马"]
    brand_aliases = [[], []]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    assert len([m for m in mentions if m["mentioned"]]) == 2

    test_text = "奔驰GLE很好，奔驰GLC也很好，奔驰的品质一直很稳定。"
    brand_names = ["奔驰"]
    brand_aliases = [[]]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    assert mentions[0]["mentioned"] is True
    assert len(mentions[0]["snippets"]) >= 2

    test_text = "宝马和奥迪都很好。"
    brand_names = ["奔驰", "宝马"]
    brand_aliases = [[], []]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    benz_mention = next((m for m in mentions if m["brand_index"] == 0), None)
    bmw_mention = next((m for m in mentions if m["brand_index"] == 1), None)
    assert benz_mention["mentioned"] is False
    assert bmw_mention["mentioned"] is True


def test_brand_isolation_with_aliases():
    """Test brand isolation works with brand aliases."""
    from services.ollama import OllamaService

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    test_text = "奔驰GLE很好，但benz的售后服务一般。"
    brand_names = ["奔驰"]
    brand_aliases = [["benz", "benchi"]]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    assert mentions[0]["mentioned"] is True
    assert len(mentions[0]["snippets"]) >= 2

    snippets = mentions[0]["snippets"]
    has_benz_snippet = any("benz" in snippet for snippet in snippets)
    has_benchi_snippet = any("benchi" in snippet for snippet in snippets)

    assert has_benz_snippet or has_benchi_snippet


def test_list_aware_snippet_extraction():
    """Test that extract_brands uses list items for snippet extraction."""
    from services.ollama import OllamaService

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    test_text = """
1. 奔驰GLE性能非常出色，豪华配置一流
2. 宝马X5操控感很差，让人失望
3. 奥迪Q7科技配置最好，非常推荐
    """
    brand_names = ["奔驰", "宝马", "奥迪"]
    brand_aliases = [[], [], []]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    benz_mention = next(m for m in mentions if brand_names[m["brand_index"]] == "奔驰")
    bmw_mention = next(m for m in mentions if brand_names[m["brand_index"]] == "宝马")
    audi_mention = next(m for m in mentions if brand_names[m["brand_index"]] == "奥迪")

    assert benz_mention["mentioned"] is True
    assert bmw_mention["mentioned"] is True
    assert audi_mention["mentioned"] is True

    benz_snippet = benz_mention["snippets"][0]
    assert "出色" in benz_snippet or "一流" in benz_snippet
    assert "失望" not in benz_snippet

    bmw_snippet = bmw_mention["snippets"][0]
    assert "失望" in bmw_snippet or "差" in bmw_snippet
    assert "一流" not in bmw_snippet

    audi_snippet = audi_mention["snippets"][0]
    assert "推荐" in audi_snippet or "最好" in audi_snippet
    assert "失望" not in audi_snippet


def test_list_aware_snippet_chinese_numbered_list():
    """Test list-aware snippets with Chinese-style numbered list."""
    from services.ollama import OllamaService

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    test_text = """
1、本田CRV是首选，性价比很高，推荐购买
2、丰田RAV4可靠性差，维修成本高
3、大众途观性能一般，但价格合理
    """
    brand_names = ["本田", "丰田", "大众"]
    brand_aliases = [[], [], []]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    honda_mention = next(m for m in mentions if brand_names[m["brand_index"]] == "本田")
    toyota_mention = next(m for m in mentions if brand_names[m["brand_index"]] == "丰田")

    honda_snippet = honda_mention["snippets"][0]
    assert "推荐" in honda_snippet or "性价比" in honda_snippet
    assert "差" not in honda_snippet

    toyota_snippet = toyota_mention["snippets"][0]
    assert "差" in toyota_snippet or "维修" in toyota_snippet
    assert "推荐" not in toyota_snippet


def test_non_list_format_uses_default_snippet():
    """Test that non-list format uses the default 50-char window."""
    from services.ollama import OllamaService

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    test_text = "本田CRV是一款很好的SUV，性价比很高。丰田RAV4也不错，但价格偏高。"
    brand_names = ["本田", "丰田"]
    brand_aliases = [[], []]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    honda_mention = next(m for m in mentions if brand_names[m["brand_index"]] == "本田")
    assert honda_mention["mentioned"] is True
    assert len(honda_mention["snippets"]) > 0


def test_non_list_snippet_starts_at_brand():
    """Test that non-list snippets start at brand position, not before."""
    from services.ollama import OllamaService

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    test_text = "前面很多文字介绍了很多内容，现在来说本田CRV是一款很好的SUV。"
    brand_names = ["本田"]
    brand_aliases = [[]]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    honda_mention = mentions[0]
    assert honda_mention["mentioned"] is True
    snippet = honda_mention["snippets"][0]
    assert snippet.startswith("本田")


def test_non_list_snippet_stops_at_next_brand():
    """Test that non-list snippets stop when another brand appears."""
    from services.ollama import OllamaService

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    test_text = "本田性能很好，但是丰田的质量更可靠，两个品牌都不错。"
    brand_names = ["本田", "丰田"]
    brand_aliases = [[], []]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    honda_mention = next(m for m in mentions if brand_names[m["brand_index"]] == "本田")
    snippet = honda_mention["snippets"][0]
    assert "丰田" not in snippet or "[BRAND]" in snippet


def test_non_list_snippet_max_50_chars():
    """Test that non-list snippets are limited to 50 chars when no other brand."""
    from services.ollama import OllamaService

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    long_text = "本田" + "x" * 100
    brand_names = ["本田"]
    brand_aliases = [[]]

    mentions = asyncio.run(
        ollama_service.extract_brands(long_text, brand_names, brand_aliases)
    )

    honda_mention = mentions[0]
    snippet = honda_mention["snippets"][0]
    assert len(snippet) <= 52


def test_truncate_list_item_short_item():
    from services.brand_recognition import _truncate_list_item

    item = "奔驰GLE非常好"
    result = _truncate_list_item(item, "奔驰", max_length=50)
    assert result == item


def test_truncate_list_item_long_item():
    from services.brand_recognition import _truncate_list_item

    item = "这是一个很长的列表项，包含奔驰品牌，还有很多其他描述性文字用于测试截断功能"
    result = _truncate_list_item(item, "奔驰", max_length=30)
    assert len(result) <= 30
    assert "奔驰" in result


def test_truncate_list_item_brand_not_found():
    from services.brand_recognition import _truncate_list_item

    item = "这是一个很长的列表项，包含很多描述性文字用于测试截断功能但没有品牌"
    result = _truncate_list_item(item, "奔驰", max_length=20)
    assert len(result) <= 20
    assert result == item[:20].strip()


def test_list_snippet_truncated_for_long_table_rows():
    from services.ollama import OllamaService

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    long_table_row = "1. 奔驰GLE | 指导价50-80万 | " + "x" * 200
    brand_names = ["奔驰"]
    brand_aliases = [[]]

    mentions = asyncio.run(
        ollama_service.extract_brands(long_table_row, brand_names, brand_aliases)
    )

    benz_mention = mentions[0]
    assert benz_mention["mentioned"] is True
    snippet = benz_mention["snippets"][0]
    assert len(snippet) <= 52
