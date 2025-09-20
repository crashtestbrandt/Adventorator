# logging.py

import logging
import os
from logging.handlers import RotatingFileHandler

import structlog
from structlog.contextvars import merge_contextvars

from Adventorator.config import Settings


def setup_logging(settings: Settings | None = None) -> None:
    """Initialize structlog + stdlib logging.

    If settings provided, enable rotating file logs per [logging] config.
    Defaults: INFO level, console on, file to logs/adventorator.jsonl.
    """
    level_name = (settings.logging_level if settings else "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Route Python warnings through logging so they are captured in JSON too
    logging.captureWarnings(True)

    # ProcessorFormatter renders BOTH structlog and stdlib/third-party logs as JSON
    processor_formatter = structlog.stdlib.ProcessorFormatter(
        # Processors applied to event-dicts prior to final render
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            # Pull request-local context (e.g., request_id) from contextvars
            merge_contextvars,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        # For plain stdlib LogRecord -> turn into event-dict before processors run
        foreign_pre_chain=[
            structlog.processors.add_log_level,
            merge_contextvars,
        ],
    )

    root_handlers: list[logging.Handler] = []
    # Console handler (per-handler level)
    console_lvl_name = None
    if settings is not None:
        console_lvl_name = getattr(settings, "logging_console", None)
    if console_lvl_name is None:
        # Fallback to legacy boolean
        use_console = True if settings is None else getattr(settings, "logging_to_console", True)
        console_lvl_name = level_name if use_console else "NONE"
    if (console_lvl_name or "").upper() != "NONE":
        ch = logging.StreamHandler()
        ch.setLevel(getattr(logging, console_lvl_name.upper(), level))
        ch.setFormatter(processor_formatter)
        root_handlers.append(ch)

    # Rotating file handler (Option B)
    file_lvl_name = None
    if settings is not None:
        file_lvl_name = getattr(settings, "logging_file", None)
    if file_lvl_name is None:
        # Fallback to legacy boolean
        to_file = True if settings is None else getattr(settings, "logging_to_file", True)
        file_lvl_name = level_name if to_file else "NONE"
    if (file_lvl_name or "").upper() != "NONE":
        path = settings.logging_file_path if settings is not None else "logs/adventorator.jsonl"
        # Ensure directory exists
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fh = RotatingFileHandler(
            path,
            maxBytes=(settings.logging_max_bytes if settings else 5_000_000),
            backupCount=(settings.logging_backup_count if settings else 5),
        )
        fh.setLevel(getattr(logging, file_lvl_name.upper(), level))
        fh.setFormatter(processor_formatter)
        root_handlers.append(fh)

    # Install root handlers; force=True to replace any prior configuration
    logging.basicConfig(level=level, handlers=root_handlers, force=True)

    # Let uvicorn/asyncio loggers bubble up into our root handlers
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "asyncio"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True

    # Configure structlog to emit into stdlib; ProcessorFormatter renders final JSON
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Hand off to ProcessorFormatter on handlers
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def redact_settings(settings: Settings) -> dict:
    """Return a redacted dict of settings safe for logging.

    Secrets and tokens are replaced with "[REDACTED]".
    """
    data = settings.model_dump()
    # Known sensitive fields
    sensitive = {
        "llm_api_key",
        "discord_bot_token",
        "discord_public_key",
        # Future-proof: any field that ends with _token or _secret
    }
    for k in list(data.keys()):
        if k in sensitive or k.endswith("_token") or k.endswith("_secret") or k.endswith("_key"):
            data[k] = "[REDACTED]"
    # Pydantic SecretStr may have been dumped as dict/str; normalize just in case
    if isinstance(getattr(settings, "llm_api_key", None), object):
        data["llm_api_key"] = "[REDACTED]"
    return data
