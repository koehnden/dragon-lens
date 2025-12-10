from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "DragonLens"
    debug: bool = False

    database_url: str = "sqlite:///./dragonlens.db"

    redis_url: str = "redis://localhost:6379/0"

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    deepseek_api_key: Optional[str] = None
    deepseek_api_base: str = "https://api.deepseek.com/v1"

    kimi_api_key: Optional[str] = None
    kimi_api_base: str = "https://api.moonshot.cn/v1"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model_translation: str = "qwen2.5:7b"
    ollama_model_sentiment: str = "qwen2.5:7b"
    ollama_model_ner: str = "qwen2.5:7b"
    ollama_model_main: str = "qwen2.5:7b"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False

    streamlit_port: int = 8501


settings = Settings()
