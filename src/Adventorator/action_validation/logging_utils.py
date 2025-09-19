from __future__ import annotations

"""Shared lightweight logging helpers for action validation phases.

These helpers standardize event naming so that Phase 1 logging requirements
("initiated" / "completed" / "rejected") are consistent across the planner,
predicate gate, and orchestrator without duplicating string literals.
"""

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
