import importlib
from unittest.mock import patch, MagicMock


def test_prefetch_ollama_embedding_model_calls_ollama_pull(monkeypatch):
    module = importlib.reload(importlib.import_module("scripts.prefetch_embedding_model"))

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "success"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        module.prefetch_ollama_embedding_model()

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ollama"
        assert call_args[1] == "pull"
        assert "bge-small-zh-v1.5" in call_args[2]


def test_prefetch_ollama_embedding_model_raises_on_failure(monkeypatch):
    module = importlib.reload(importlib.import_module("scripts.prefetch_embedding_model"))

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "model not found"

    with patch("subprocess.run", return_value=mock_result):
        try:
            module.prefetch_ollama_embedding_model()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Failed to pull Ollama model" in str(e)
