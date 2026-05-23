import logging
import os
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

class _ExtraFormatter(logging.Formatter):
    """Appends any extra fields passed to logger calls to the log line."""

    def format(self, record: logging.LogRecord) -> str:
        standard = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "asctime", "taskName",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in standard and not k.startswith("_")}
        base = super().format(record)
        if extras:
            fields = " ".join(f"{k}={v}" for k, v in extras.items())
            return f"{base} {fields}"
        return base


logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
for _handler in logging.root.handlers:
    _handler.setFormatter(_ExtraFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    ))
os.environ.setdefault("TAVILY_API_KEY", settings.tavily_api_key)
os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
os.environ.setdefault("LLM_PROVIDER", settings.llm_provider)
os.environ.setdefault("LLM_MODEL", settings.llm_model)
os.environ.setdefault("WEB_SEARCH_PROVIDER", settings.web_search_provider)