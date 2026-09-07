"""Environment and path configuration.

Everything comes from `.env` (never committed) or the process environment.
The token is a `SecretStr` so it never appears in reprs, logs or tracebacks.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Phase 0-2
    tarkovtracker_token: SecretStr = Field(..., description="PVE_-prefixed TarkovTracker API token")
    tarkovtracker_base: str = "https://api.tarkovtracker.org"
    tarkov_json_base: str = "https://json.tarkov.dev"
    game_mode: str = "pve"

    # Phase 3+
    ollama_host: str = "http://localhost:11434"
    ollama_vision_model: str = ""
    obsidian_vault: Path | None = None
    slack_webhook_url: SecretStr | None = None
    inbox_dir: Path = REPO_ROOT / "inbox"
    eft_process_name: str = "EscapeFromTarkov.exe"

    # Paths
    data_dir: Path = REPO_ROOT / "data"
    samples_dir: Path = REPO_ROOT / "docs" / "samples"
    out_dir: Path = REPO_ROOT / "out"
    config_dir: Path = REPO_ROOT / "config"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tarkov-ops.db"

    @field_validator("tarkovtracker_token")
    @classmethod
    def _check_token_prefix(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        if not raw.startswith("PVE_"):
            raise ValueError(
                "TARKOVTRACKER_TOKEN must be a PVE_ token (legacy tt_ tokens are rejected)"
            )
        return v

    @field_validator("game_mode")
    @classmethod
    def _check_game_mode(cls, v: str) -> str:
        v = v.lower()
        if v != "pve":
            raise ValueError("v1 supports GAME_MODE=pve only")
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
