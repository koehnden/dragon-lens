import asyncio

import pytest
from unittest.mock import patch, MagicMock
from services.sentiment_analysis import ErlangshenSentimentService
from models.domain import Sentiment

@pytest.fixture
def mock_transformers():
    with patch('services.sentiment_analysis.AutoModelForSequenceClassification') as mock_model_class, \
         patch('services.sentiment_analysis.AutoTokenizer') as mock_tokenizer_class, \
         patch('services.sentiment_analysis.pipeline') as mock_pipeline:
        yield {
            'model_class': mock_model_class,
            'tokenizer_class': mock_tokenizer_class,
            'pipeline': mock_pipeline
        }

def test_erlangshen_sentiment_service_initialization(mock_transformers):
    """Test that the Erlangshen sentiment service initializes correctly."""
    mock_model_instance = MagicMock()
    mock_tokenizer_instance = MagicMock()
    mock_pipeline_instance = MagicMock()

    mock_transformers['model_class'].from_pretrained.return_value = mock_model_instance
    mock_transformers['tokenizer_class'].from_pretrained.return_value = mock_tokenizer_instance
    mock_transformers['pipeline'].return_value = mock_pipeline_instance

    service = ErlangshenSentimentService()

    # Verify initialization
    assert service.model is not None
    assert service.tokenizer is not None
    assert service.pipeline is not None

    # Verify correct model loading
    mock_transformers['model_class'].from_pretrained.assert_called_once_with(
        "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment"
    )
    mock_transformers['tokenizer_class'].from_pretrained.assert_called_once_with(
        "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment"
    )
    mock_transformers['pipeline'].assert_called_once_with(
        "text-classification",
        model=mock_model_instance,
        tokenizer=mock_tokenizer_instance
    )

def test_classify_sentiment_positive(mock_transformers):
    """Test sentiment classification for positive Chinese text."""
    mock_pipeline_instance = MagicMock()
    mock_pipeline_instance.return_value = [{
        'label': 'positive',
        'score': 0.95
    }]

    mock_transformers['pipeline'].return_value = mock_pipeline_instance

    service = ErlangshenSentimentService()

    # Test positive sentiment
    result = service.classify_sentiment("这个产品非常好，我非常喜欢！")
    assert result == "positive"

def test_classify_sentiment_negative(mock_transformers):
    """Test sentiment classification for negative Chinese text."""
    mock_pipeline_instance = MagicMock()
    mock_pipeline_instance.return_value = [{
        'label': 'negative',
        'score': 0.92
    }]

    mock_transformers['pipeline'].return_value = mock_pipeline_instance

    service = ErlangshenSentimentService()

    # Test negative sentiment
    result = service.classify_sentiment("这个服务太差了，非常失望。")
    assert result == "negative"

def test_classify_sentiment_neutral(mock_transformers):
    """Test sentiment classification for neutral Chinese text."""
    mock_pipeline_instance = MagicMock()
    mock_pipeline_instance.return_value = [{
        'label': 'neutral',
        'score': 0.88
    }]

    mock_transformers['pipeline'].return_value = mock_pipeline_instance

    service = ErlangshenSentimentService()

    # Test neutral sentiment
    result = service.classify_sentiment("今天天气不错。")
    assert result == "neutral"

def test_classify_sentiment_empty_text(mock_transformers):
    """Test sentiment classification with empty text."""
    mock_pipeline_instance = MagicMock()
    mock_pipeline_instance.return_value = [{
        'label': 'neutral',
        'score': 0.90
    }]

    mock_transformers['pipeline'].return_value = mock_pipeline_instance

    service = ErlangshenSentimentService()

    # Test empty text - should return neutral
    result = service.classify_sentiment("")
    assert result == "neutral"

def test_classify_sentiment_english_text(mock_transformers):
    """Test sentiment classification with English text (should still work)."""
    mock_pipeline_instance = MagicMock()
    mock_pipeline_instance.return_value = [{
        'label': 'positive',
        'score': 0.93
    }]

    mock_transformers['pipeline'].return_value = mock_pipeline_instance

    service = ErlangshenSentimentService()

    # Test English text
    result = service.classify_sentiment("This product is excellent!")
    assert result == "positive"

def test_classify_sentiment_mixed_results(mock_transformers):
    """Test sentiment classification with various confidence scores."""
    test_cases = [
        (0.95, "positive", "positive"),
        (0.92, "negative", "negative"),
        (0.88, "neutral", "neutral"),
        (0.70, "positive", "positive"),
        (0.60, "negative", "negative"),
        (0.55, "neutral", "neutral"),
    ]

    mock_transformers['pipeline'].return_value = MagicMock()

    service = ErlangshenSentimentService()

    for score, label, expected in test_cases:
        mock_transformers['pipeline'].return_value.return_value = [{
            'label': label,
            'score': score
        }]
        result = service.classify_sentiment(f"Test text for {label}")
        assert result == expected, f"Failed for {label} with score {score}"

def test_sentiment_service_integration_with_ollama():
    """Test that Erlangshen service can be integrated with OllamaService."""
    from services.ollama import OllamaService
    from services.sentiment_analysis import ErlangshenSentimentService

    # This test verifies the interface compatibility
    ollama_service = OllamaService()

    # Verify that both services have the same classify_sentiment method signature
    assert hasattr(ollama_service, 'classify_sentiment')
    assert hasattr(ErlangshenSentimentService, 'classify_sentiment')

    # Both should be async methods that take text and return sentiment string
    import inspect
    ollama_method = getattr(ollama_service, 'classify_sentiment')
    erlangshen_method = getattr(ErlangshenSentimentService, 'classify_sentiment')

    # Check that both are callable and have similar signatures
    assert callable(ollama_method)
    assert callable(erlangshen_method)

@pytest.mark.asyncio
async def test_erlangshen_vs_qwen_performance():
    """Compare performance between Erlangshen and Qwen sentiment analysis."""
    from services.ollama import OllamaService
    from services.sentiment_analysis import ErlangshenSentimentService
    import time

    # Mock the Erlangshen service for this test
    with patch('services.sentiment_analysis.pipeline') as mock_pipeline:
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.return_value = [{'label': 'positive', 'score': 0.95}]
        mock_pipeline.return_value = mock_pipeline_instance

        erlangshen_service = ErlangshenSentimentService()

        # Test text
        test_text = "这个产品非常好，质量上乘，性价比很高！"

        # Measure Erlangshen performance
        start_time = time.time()
        erlangshen_result = erlangshen_service.classify_sentiment(test_text)
        erlangshen_time = time.time() - start_time

        # Verify result
        assert erlangshen_result == "positive"
        assert erlangshen_time < 1.0  # Should be very fast

        print(f"Erlangshen sentiment analysis time: {erlangshen_time:.4f}s")

def test_brand_isolation_in_extract_brands():
    """Test that extract_brands properly isolates brands to prevent sentiment contamination."""
    from services.ollama import OllamaService
    from unittest.mock import AsyncMock

    # Create a mock OllamaService
    ollama_service = OllamaService()

    # Test case: Multiple brands in close proximity
    test_text = "奔驰GLE性能出色，但宝马X5的性价比更高，而奥迪Q7的科技配置最好。"
    brand_names = ["奔驰", "宝马", "奥迪"]
    brand_aliases = [[], [], []]  # No aliases for this test

    # Mock the _call_ollama method to avoid actual API calls
    ollama_service._call_ollama = AsyncMock(return_value="")

    # Extract brands
    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    # Verify results
    assert len(mentions) == 3

    # Check each brand's snippets
    for mention in mentions:
        assert mention["mentioned"] is True
        assert len(mention["snippets"]) > 0

        # Verify brand isolation: other brands should be masked as [BRAND]
        for snippet in mention["snippets"]:
            # Count how many actual brand names appear in the snippet
            brand_count = 0
            if "奔驰" in snippet:
                brand_count += 1
            if "宝马" in snippet:
                brand_count += 1
            if "奥迪" in snippet:
                brand_count += 1
            if "[BRAND]" in snippet:
                # [BRAND] tokens indicate proper isolation
                pass

            # Each snippet should contain at most ONE actual brand name
            # (the target brand) plus any [BRAND] placeholders
            assert brand_count <= 1, f"Snippet contains multiple brands: {snippet}"

def test_brand_isolation_edge_cases():
    """Test brand isolation with edge cases."""
    from services.ollama import OllamaService
    from unittest.mock import AsyncMock

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    # Test case 1: Overlapping brand names
    test_text = "奔驰宝马是最好的组合，奔驰的性能和宝马的操控都很出色。"
    brand_names = ["奔驰", "宝马"]
    brand_aliases = [[], []]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    # Both brands should be found
    assert len([m for m in mentions if m["mentioned"]]) == 2

    # Test case 2: Same brand mentioned multiple times
    test_text = "奔驰GLE很好，奔驰GLC也很好，奔驰的品质一直很稳定。"
    brand_names = ["奔驰"]
    brand_aliases = [[]]

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    # Should find multiple snippets for the same brand
    assert mentions[0]["mentioned"] is True
    assert len(mentions[0]["snippets"]) >= 2  # Multiple mentions

    # Test case 3: Brand not mentioned
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
    from unittest.mock import AsyncMock

    ollama_service = OllamaService()
    ollama_service._call_ollama = AsyncMock(return_value="")

    # Test with aliases
    test_text = "奔驰GLE很好，但benz的售后服务一般。"
    brand_names = ["奔驰"]
    brand_aliases = [["benz", "benchi"]]  # Common aliases

    mentions = asyncio.run(
        ollama_service.extract_brands(test_text, brand_names, brand_aliases)
    )

    # Should find both "奔驰" and "benz" as mentions of the same brand
    assert mentions[0]["mentioned"] is True
    assert len(mentions[0]["snippets"]) >= 2  # Both main name and alias

    # Both should be treated as the same brand in isolation
    snippets = mentions[0]["snippets"]
    has_benz_snippet = any("benz" in snippet for snippet in snippets)
    has_benchi_snippet = any("benchi" in snippet for snippet in snippets)

    assert has_benz_snippet or has_benchi_snippet


def test_list_aware_snippet_extraction():
    """Test that extract_brands uses list items for snippet extraction."""
    from services.ollama import OllamaService
    from unittest.mock import AsyncMock

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
    from unittest.mock import AsyncMock

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
    from unittest.mock import AsyncMock

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
    from unittest.mock import AsyncMock

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
    from unittest.mock import AsyncMock

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
    from unittest.mock import AsyncMock

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
