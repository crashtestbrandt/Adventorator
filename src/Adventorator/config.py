"""Settings loader for Adventorator."""

from pathlib import Path
from typing import Any, Literal

import tomllib
from pydantic import BaseModel, Field, SecretStr
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
        "features_action_validation": t.get("features", {}).get("action_validation", False),
        "features_predicate_gate": t.get("features", {}).get("predicate_gate", False),
        "features_mcp": t.get("features", {}).get("mcp", False),
        "features_activity_log": t.get("features", {}).get("activity_log", False),
        # Map rendering (Phase 12) — prefer [map].enabled with legacy fallback
        "features_map": bool(
            (t.get("map", {}) or {}).get(
                "enabled",
                (t.get("features", {}) or {}).get("map", False),
            )
        ),
        # Default visibility to False for safe-by-default shadow mode
        "features_llm_visible": t.get("features", {}).get("llm_visible", False),
        # Planner hard-toggle; prefer [planner].enabled, fallback to legacy [features].planner
        "feature_planner_enabled": bool(
            (t.get("planner", {}) or {}).get(
                "enabled",
                (t.get("features", {}) or {}).get("planner", True),
            )
        ),
        "features_rules": t.get("features", {}).get("rules", False),
        # Combat FF now lives under [combat].enabled; keep a fallback to legacy [features].combat
        # Example:
        # [combat]
        # enabled = true
        # Legacy:
        # [features]
        # combat = true
        "features_combat": bool(
            (t.get("combat", {}) or {}).get(
                "enabled",
                (t.get("features", {}) or {}).get("combat", False),
            )
        ),
        # Events ledger (Phase 9) — default disabled
        "features_events": t.get("features", {}).get("events", False),
        # Executor (Phase 7+) — default disabled
        "features_executor": t.get("features", {}).get("executor", False),
        # Confirmation gating FF (Phase 8); default true so it can be disabled in dev
        "features_executor_confirm": t.get("features", {}).get("executor_confirm", True),
        "response_timeout_seconds": t.get("discord", {}).get("response_timeout_seconds", 3),
        # When set, app will post follow-ups to this base URL instead of Discord.
        # Example: "http://host.docker.internal:19000"
        "discord_webhook_url_override": t.get("discord", {}).get("webhook_url_override"),
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

    # Planner
    planner_cfg = t.get("planner", {}) or {}
    out["planner_timeout_seconds"] = int(planner_cfg.get("timeout_seconds", 12))

    # Retrieval (Phase 6)
    # Example TOML:
    # [features.retrieval]
    # enabled = true
    # provider = "none" # future: pgvector|qdrant
    # top_k = 4
    retrieval_cfg = (t.get("features", {}).get("retrieval", {}) or {})
    if retrieval_cfg:
        out["retrieval"] = {
            "enabled": bool(retrieval_cfg.get("enabled", False)),
            "provider": retrieval_cfg.get("provider", "none"),
            "top_k": int(retrieval_cfg.get("top_k", 4)),
        }

    # Ops toggles
    ops_cfg = t.get("ops", {}) or {}
    out["metrics_endpoint_enabled"] = ops_cfg.get("metrics_endpoint_enabled", False)

    return out


class Settings(BaseSettings):
    env: str = Field(default="dev")
    database_url: str = Field(default="sqlite+aiosqlite:///./adventorator.sqlite3")

    # --- Discord Credentials ---
    discord_app_id: str | None = None
    discord_public_key: str = ""
    # Development-only alternate public key used for local CLI-signed requests
    discord_dev_public_key: str | None = None
    discord_bot_token: SecretStr | None = None
    # For development/testing with web_cli.py only
    discord_private_key: SecretStr | None = None
    # For redirecting webhooks back to the local web_cli.py sink
    discord_webhook_url_override: str | None = None

    # --- App Behavior ---
    features_llm: bool = False
    features_llm_visible: bool = False
    feature_planner_enabled: bool = True
    features_rules: bool = False
    features_combat: bool = False
    features_action_validation: bool = False
    features_predicate_gate: bool = False
    features_mcp: bool = False
    features_activity_log: bool = False
    features_map: bool = False
    features_events: bool = False
    features_executor: bool = False
    features_executor_confirm: bool = True
    response_timeout_seconds: int = 3
    app_port: int = 18000
    planner_timeout_seconds: int = 12

    # --- Retrieval (Phase 6) ---
    class RetrievalConfig(BaseModel):
        enabled: bool = False
        provider: Literal["none", "pgvector", "qdrant"] = "none"
        top_k: int = 4

    retrieval: RetrievalConfig = RetrievalConfig()

    # --- LLM Configuration ---
    llm_api_provider: Literal["ollama", "openai"] = Field(
        default="ollama", description="The type of LLM API to use ('ollama' or 'openai')."
    )
    llm_api_url: str | None = None
    llm_api_key: SecretStr | None = Field(
        default=None, description="API key for OpenAI-compatible services."
    )
    llm_model_name: str = "llama3:8b"
    llm_default_system_prompt: str = "You are a helpful assistant."
    llm_max_prompt_tokens: int = 4096
    llm_max_response_chars: int = 4096

    # --- Logging ---
    logging_enabled: bool = True
    logging_level: str = "INFO"
    logging_console: str = "INFO"
    logging_file: str = "INFO"
    logging_to_console: bool = True
    logging_to_file: bool = True
    logging_file_path: str = "logs/adventorator.jsonl"
    logging_max_bytes: int = 5_000_000
    logging_backup_count: int = 5

    # --- Ops ---
    metrics_endpoint_enabled: bool = False

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_file=".env",
        extra="ignore", # Safely ignore any extra env vars
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
        # Precedence (highest to lowest):
        # 1) init_settings (explicit overrides in code/tests)
        # 2) dotenv (.env in cwd) — developer-local overrides
        # 3) env_settings (OS env)
        # 4) TOML (repo config.toml) — project defaults
        # 5) file_secret_settings
        return (
            init_settings,
            dotenv_settings,
            env_settings,
            _toml_settings_source,
            file_secret_settings,
        )


def load_settings() -> Settings:
    return Settings()

