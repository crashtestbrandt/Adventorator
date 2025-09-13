"""Settings loader for Adventorator."""

from pathlib import Path
from typing import Any, Literal

import tomllib
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _toml_settings_source() -> dict[str, Any]:
    """Load settings from config.toml with keys mapped to Settings fields.

    This source has LOWER priority than env/.env so those can override TOML.
    """
    cfg_path = Path("config.toml")
    if not cfg_path.exists():
        return {}
    with cfg_path.open("rb") as f:
        t = tomllib.load(f)
    out: dict[str, Any] = {
        "env": t.get("app", {}).get("env", "dev"),
        "features_llm": t.get("features", {}).get("llm", False),
    # Default visibility to False for safe-by-default shadow mode
    "features_llm_visible": t.get("features", {}).get("llm_visible", False),
    # Planner hard-toggle; defaults to True so it can be disabled quickly via env
    "feature_planner_enabled": t.get("features", {}).get("planner", True),
        "features_rules": t.get("features", {}).get("rules", False),
        "features_combat": t.get("features", {}).get("combat", False),
        "response_timeout_seconds": t.get("discord", {}).get("response_timeout_seconds", 3),
        "llm_api_provider": t.get("llm", {}).get("api_provider", "ollama"),
        "llm_api_url": t.get("llm", {}).get("api_url"),
        "llm_model_name": t.get("llm", {}).get("model_name"),
        "llm_default_system_prompt": t.get("llm", {}).get("default_system_prompt"),
        # Logging config
        "logging_enabled": t.get("logging", {}).get("enabled", True),
        "logging_level": t.get("logging", {}).get("level", "INFO"),
    # Per-handler levels: strings INFO|DEBUG|WARNING|ERROR|CRITICAL|NONE
    # Backward-compatible: if console/to_file are bools, map True->level, False->NONE
    "logging_console": None,
    "logging_file": None,
        "logging_file_path": t.get("logging", {}).get("file_path", "logs/adventorator.jsonl"),
        "logging_max_bytes": t.get("logging", {}).get("max_bytes", 5_000_000),
        "logging_backup_count": t.get("logging", {}).get("backup_count", 5),
    }

    log_cfg = t.get("logging", {}) or {}
    # Derive per-handler levels if provided as strings; otherwise fallback from booleans
    console_val = log_cfg.get("console", None)
    file_val = log_cfg.get("to_file", None)
    overall = out["logging_level"]
    def _norm_level(v, default):
        if isinstance(v, str):
            return v.upper()
        if isinstance(v, bool):
            return default if v else "NONE"
        return default

    out["logging_console"] = _norm_level(console_val, overall)
    out["logging_file"] = _norm_level(file_val, overall)

    # Only set legacy booleans if TOML provided booleans to avoid validation errors
    if isinstance(console_val, bool):
        out["logging_to_console"] = console_val
    if isinstance(file_val, bool):
        out["logging_to_file"] = file_val

    llm_cfg = t.get("llm", {}) or {}
    if "max_prompt_tokens" in llm_cfg and llm_cfg.get("max_prompt_tokens") is not None:
        out["llm_max_prompt_tokens"] = llm_cfg["max_prompt_tokens"]
    if "max_response_chars" in llm_cfg and llm_cfg.get("max_response_chars") is not None:
        out["llm_max_response_chars"] = llm_cfg["max_response_chars"]

    # Ops toggles
    ops_cfg = t.get("ops", {}) or {}
    out["metrics_endpoint_enabled"] = ops_cfg.get("metrics_endpoint_enabled", False)

    return out


class Settings(BaseSettings):
    env: str = Field(default="dev")
    database_url: str = Field(default="sqlite+aiosqlite:///./adventorator.sqlite3")
    # Provide a default to satisfy static type checkers; real value should come from env/TOML.
    discord_public_key: str = ""
    discord_bot_token: str | None = None
    features_llm: bool = False
    features_llm_visible: bool = False
    feature_planner_enabled: bool = True
    features_rules: bool = False
    features_combat: bool = False
    response_timeout_seconds: int = 3

    llm_api_provider: Literal["ollama", "openai"] = Field(
        default="ollama", description="The type of LLM API to use ('ollama' or 'openai')."
    )
    llm_api_url: str | None = None
    llm_api_key: SecretStr | None = Field(
        default=None, description="API key for OpenAI-compatible services."
    )
    llm_model_name: str = "llama3:8b"
    llm_default_system_prompt: str = "You are a helpful assistant."
    # TODO: These limits should align with the selected model's context window.
    llm_max_prompt_tokens: int = 4096
    llm_max_response_chars: int = 4096

    # Logging
    logging_enabled: bool = True
    logging_level: str = "INFO"
    # Per-handler levels; use "NONE" to disable
    logging_console: str = "INFO"
    logging_file: str = "INFO"
    # Legacy booleans retained for backward compatibility (unused if above present)
    logging_to_console: bool = True
    logging_to_file: bool = True
    logging_file_path: str = "logs/adventorator.jsonl"
    logging_max_bytes: int = 5_000_000
    logging_backup_count: int = 5

    # Ops
    metrics_endpoint_enabled: bool = False

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_file=".env",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Priority: explicit env vars > .env file > TOML file > init kwargs > file secrets
        return (
            env_settings,
            dotenv_settings,
            _toml_settings_source,
            init_settings,
            file_secret_settings,
        )


def load_settings() -> Settings:
    # Instantiate with no kwargs so env/.env can override TOML source
    return Settings()
