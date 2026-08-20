from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FedRepro"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg2://user:password@localhost:5432/fedrepo"
    secret_key: str = "replace-with-a-long-random-value"
    access_token_expire_minutes: int = 1440
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    upload_root: Path = Path("uploads")
    max_upload_bytes: int = 100 * 1024 * 1024
    ai_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:latest"
    evidence_warmup_on_startup: bool = True
    ai_max_workers: int = 1
    ai_job_max_attempts: int = 2
    ai_job_timeout_seconds: int = 90
    ai_max_pending_jobs: int = 50
    ai_prefetch_enabled: bool = True
    ai_warmup_mode: str = "recent"
    ai_warmup_recent_versions: int = 3
    ai_warmup_max_jobs: int = 5
    ai_version_analysis_max_tokens: int = 2200
    ai_report_max_tokens: int = 2600
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
