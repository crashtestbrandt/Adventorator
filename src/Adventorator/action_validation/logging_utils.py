"""Lightweight logging helpers for action validation phases.

Standardizes event naming: initiated/completed/rejected across planner,
predicate gate, orchestrator.
"""

from __future__ import annotations

import structlog

_log = structlog.get_logger()


def log_event(stage: str, event: str, **fields):  # type: ignore[any]
    """Emit a structured log event following the <stage>.<event> naming style.

    Parameters
    ----------
    stage: Logical pipeline stage (e.g. "planner", "predicate_gate", "orchestrator").
    event: Lifecycle or outcome token (e.g. "initiated", "completed", "rejected", "failed").
    fields: Additional structured context fields.
    """

    _log.info(f"{stage}.{event}", **fields)


def log_rejection(stage: str, reason: str, **fields):  # type: ignore[any]
    """Emit a standardized rejection log for observability dashboards."""

    _log.warning(f"{stage}.rejected", reason=reason, **fields)
