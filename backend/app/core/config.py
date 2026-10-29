"""Environment settings. API keys stay on the server and out of the browser bundle."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model_api_key: str = ""
    meta_base_url: str = "https://api.meta.ai/v1"
    meta_model: str = "muse-spark-1.3"
    database_url: str = ""
    enable_meta: bool = False

    def resolved_database_url(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()
        path = ROOT / "backend" / "data" / "swarm.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + path.as_posix()
