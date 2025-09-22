"""Placeholder metric instrumentation for idempotency key v2 (STORY-CDA-CORE-001D)."""

import logging
from typing import Any

# Placeholder logging setup
logger = logging.getLogger(__name__)


def log_idempotency_reuse(
    campaign_id: int,
    idempotency_key: bytes,
    event_id: int,
    tool_name: str | None = None,
    plan_id: str | None = None,
) -> None:
    """Log idempotency key reuse for observability.
    
    This provides structured logging for when an existing event is returned
    instead of creating a new one, enabling observability of retry collapse.
    """
    logger.info(
        "idempotency.reuse",
        extra={
            "campaign_id": campaign_id,
            "idempotency_key_hex": idempotency_key.hex(),
            "event_id": event_id,
            "tool_name": tool_name,
            "plan_id": plan_id,
        }
    )


def log_idempotency_collision(
    campaign_id: int,
    idempotency_key: bytes,
    original_event_id: int,
    collision_inputs: dict[str, Any],
) -> None:
    """Log potential idempotency collision for investigation.
    
    This would be called if we detect unexpected collision patterns
    during the shadow computation period.
    """
    logger.warning(
        "idempotency.collision",
        extra={
            "campaign_id": campaign_id,
            "idempotency_key_hex": idempotency_key.hex(),
            "original_event_id": original_event_id,
            "collision_inputs": collision_inputs,
        }
    )


def increment_metric(metric_name: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
    """Placeholder metric increment function.
    
    In a real implementation, this would integrate with the application's
    metrics system (e.g., Prometheus, StatsD, etc.).
    """
    # For now, just log the metric
    logger.info(
        f"metric.{metric_name}",
        extra={
            "metric_name": metric_name,
            "value": value,
            "tags": tags or {},
        }
    )


# Metric names as specified in the epic documentation
METRIC_EVENTS_IDEMPOTENT_REUSE = "events.idempotent_reuse"
METRIC_EVENTS_COLLISION = "events.idempotent_collision"


def record_idempotent_reuse(tool_name: str | None = None) -> None:
    """Record idempotent reuse metric."""
    tags = {"tool_name": tool_name} if tool_name else {}
    increment_metric(METRIC_EVENTS_IDEMPOTENT_REUSE, tags=tags)


def record_collision_detected(tool_name: str | None = None) -> None:
    """Record collision detection metric.""" 
    tags = {"tool_name": tool_name} if tool_name else {}
    increment_metric(METRIC_EVENTS_COLLISION, tags=tags)


# Example usage in executor prototype
def example_executor_integration():
    """Example of how metrics would be integrated in the executor."""
    
    # In the executor when reusing an existing event:
    log_idempotency_reuse(
        campaign_id=12345,
        idempotency_key=b"\\x01\\x02\\x03...",
        event_id=67890,
        tool_name="dice_roll",
        plan_id="plan-abc123"
    )
    record_idempotent_reuse(tool_name="dice_roll")
    
    # If collision is ever detected (should be rare):
    log_idempotency_collision(
        campaign_id=12345,
        idempotency_key=b"\\x01\\x02\\x03...",
        original_event_id=67890,
        collision_inputs={
            "plan_id": "different-plan",
            "tool_name": "different_tool",
            # ...
        }
    )
    record_collision_detected(tool_name="dice_roll")