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

    database_url: str = "postgresql+psycopg://dragonlens:dragonlens@localhost:5432/dragonlens"
    knowledge_database_url: str = "sqlite:///./data/knowledge.db"

    redis_url: str = "redis://localhost:6379/0"

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_queue_name: str = "dragon-lens"

    deepseek_api_key: Optional[str] = None
    deepseek_api_base: str = "https://api.deepseek.com/v1"

    kimi_api_key: Optional[str] = None
    kimi_api_base: str = "https://api.moonshot.ai/v1"

    openrouter_api_key: Optional[str] = None
    openrouter_api_base: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: Optional[str] = None
    openrouter_app_title: Optional[str] = None

    ollama_base_url: str = "http://localhost:11434"
    ollama_model_translation: str = "qwen2.5:7b-instruct-q4_0"
    ollama_model_sentiment: str = "qwen2.5:7b-instruct-q4_0"  # Fallback model
    ollama_model_ner: str = "qwen2.5:7b-instruct-q4_0"
    ollama_model_main: str = "qwen2.5:7b-instruct-q4_0"

    # Erlangshen-Roberta-110M-Sentiment configuration
    erlangshen_sentiment_model: str = "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment"
    use_erlangshen_sentiment: bool = True  # Set to False to disable Erlangshen and use Qwen only

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False

    streamlit_port: int = 8501

    encryption_secret_key: str = "ENCRYPTION_SECRET_KEY_NOT_SET_PLEASE_SET_IN_ENV"

    parallel_llm_enabled: bool = True
    remote_llm_concurrency: int = 3
    local_llm_concurrency: int = 1


settings = Settings()
