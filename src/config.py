from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    log_level: str = "INFO"
    cache_dir: str = "./.cache"
    cache_ttl_seconds: int = 86400
    per_source_timeout_seconds: float = 10.0
    max_sources_per_query: int = 3
    max_parallel: int = 10

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()