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
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
