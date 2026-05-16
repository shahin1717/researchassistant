import logging
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.0-flash"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # Web search
    web_search_provider: str = "tavily"
    tavily_api_key: str = ""
    serper_api_key: str = ""

    # SE layer
    log_level: str = "INFO"
    cache_dir: str = "./.cache"
    cache_ttl_seconds: int = 86400
    per_source_timeout_seconds: float = 10.0
    max_sources_per_query: int = 3
    max_parallel: int = 10

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)