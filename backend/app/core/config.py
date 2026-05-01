"""Runtime configuration helpers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_timezone: str = Field(default="Asia/Shanghai", alias="APP_TIMEZONE")
    api_v1_prefix: str = "/api"
    project_name: str = "Personal Affairs Assistant"
    project_version: str = "0.1.0"
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    slow_request_threshold_ms: int = Field(default=1200, alias="SLOW_REQUEST_THRESHOLD_MS")

    sqlite_db_path: str = Field(default="./data/app.db", alias="SQLITE_DB_PATH")
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", alias="REDIS_URL")

    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="models/gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_timeout_seconds: float = Field(default=15.0, alias="GEMINI_TIMEOUT_SECONDS")
    gemini_max_retries: int = Field(default=3, alias="GEMINI_MAX_RETRIES")
    gemini_retry_delay_seconds: float = Field(default=1.0, alias="GEMINI_RETRY_DELAY_SECONDS")
    gemini_circuit_breaker_seconds: int = Field(default=60, alias="GEMINI_CIRCUIT_BREAKER_SECONDS")

    map_provider: str = Field(default="amap", alias="MAP_PROVIDER")
    map_api_key: str | None = Field(default=None, alias="MAP_API_KEY")
    amap_secret: str | None = Field(default=None, alias="AMAP_SECRET")

    weather_provider: str = Field(default="qweather", alias="WEATHER_PROVIDER")
    qweather_api_key: str | None = Field(default=None, alias="QWEATHER_API_KEY")
    qweather_api_host: str | None = Field(default=None, alias="QWEATHER_API_HOST")
    weather_cache_path: str = Field(default="./data/weather_snapshot_cache.json", alias="WEATHER_CACHE_PATH")
    weather_snapshot_max_age_hours: int = Field(default=10, alias="WEATHER_SNAPSHOT_MAX_AGE_HOURS")

    google_calendar_enabled: bool = Field(default=True, alias="GOOGLE_CALENDAR_ENABLED")
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str | None = Field(default=None, alias="GOOGLE_REDIRECT_URI")
    google_calendar_id: str = Field(default="primary", alias="GOOGLE_CALENDAR_ID")
    google_client_secret_json_path: str | None = Field(
        default=None,
        alias="GOOGLE_CLIENT_SECRET_JSON_PATH",
    )

    notification_in_app: bool = Field(default=True, alias="NOTIFICATION_IN_APP")
    notification_desktop: bool = Field(default=True, alias="NOTIFICATION_DESKTOP")

    enable_workflow: bool = Field(default=True, alias="ENABLE_WORKFLOW")
    enable_react_subgraph: bool = Field(default=True, alias="ENABLE_REACT_SUBGRAPH")
    route_confidence_threshold: float = Field(default=0.6, alias="ROUTE_CONFIDENCE_THRESHOLD")
    assistant_conductor_mode: str = Field(default="legacy", alias="ASSISTANT_CONDUCTOR_MODE")
    assistant_proactive_mode: str = Field(default="off", alias="ASSISTANT_PROACTIVE_MODE")
    assistant_legacy_inbox_job_enabled: bool = Field(default=False, alias="ASSISTANT_LEGACY_INBOX_JOB_ENABLED")
    assistant_memory_path: str = Field(default="./data/assistant_memory", alias="ASSISTANT_MEMORY_PATH")

    voice_input_enabled: bool = Field(default=False, alias="VOICE_INPUT_ENABLED")
    voice_output_enabled: bool = Field(default=False, alias="VOICE_OUTPUT_ENABLED")
    voice_input_model: str = Field(default="base", alias="VOICE_INPUT_MODEL")
    voice_output_lang: str = Field(default="zh-CN", alias="VOICE_OUTPUT_LANG")

    @property
    def database_url(self) -> str:
        """Return the SQLAlchemy database URL."""
        db_path = Path(self.sqlite_db_path)
        if not db_path.is_absolute():
            db_path = (BASE_DIR / db_path).resolve()
        return f"sqlite:///{db_path.as_posix()}"

    @property
    def sqlite_db_file(self) -> Path:
        """Return the resolved SQLite database path."""
        db_path = Path(self.sqlite_db_path)
        if not db_path.is_absolute():
            db_path = (BASE_DIR / db_path).resolve()
        return db_path

    @property
    def weather_cache_file(self) -> Path:
        """Return the resolved weather snapshot cache path."""
        cache_path = Path(self.weather_cache_path)
        if not cache_path.is_absolute():
            cache_path = (BASE_DIR / cache_path).resolve()
        return cache_path

    @property
    def assistant_memory_dir(self) -> Path:
        """Return the resolved assistant memory root directory."""
        memory_path = Path(self.assistant_memory_path)
        if not memory_path.is_absolute():
            memory_path = (BASE_DIR / memory_path).resolve()
        return memory_path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
