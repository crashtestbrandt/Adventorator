# logging.py

import logging
import os
from logging.handlers import RotatingFileHandler

import structlog
from Adventorator.config import Settings


def setup_logging(settings: Settings | None = None) -> None:
    """Initialize structlog + stdlib logging.

    If settings provided, enable rotating file logs per [logging] config.
    Defaults: INFO level, console on, file to logs/adventorator.jsonl.
    """
    level_name = (settings.logging_level if settings else "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_handlers: list[logging.Handler] = []
    # Console handler
    if settings is None or getattr(settings, "logging_to_console", True):
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter("%(message)s"))
        root_handlers.append(ch)

    # Rotating file handler (Option B)
    to_file = True if settings is None else getattr(settings, "logging_to_file", True)
    if to_file:
        path = (
            settings.logging_file_path
            if settings is not None
            else "logs/adventorator.jsonl"
        )
        # Ensure directory exists
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fh = RotatingFileHandler(
            path,
            maxBytes=(settings.logging_max_bytes if settings else 5_000_000),
            backupCount=(settings.logging_backup_count if settings else 5),
        )
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter("%(message)s"))
        root_handlers.append(fh)

    logging.basicConfig(level=level, handlers=root_handlers)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )
