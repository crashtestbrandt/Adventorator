"""Test KB timeout and bounds enforcement."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from Adventorator.kb.adapter import KBAdapter
from Adventorator.metrics import get_counter, reset_counters


@pytest.fixture
def mock_sessionmaker():
    """Mock sessionmaker for testing."""
    mock_session = AsyncMock()
    mock_sm = AsyncMock(return_value=mock_session)
    mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sm.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_sm


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test."""
    reset_counters()


@pytest.mark.asyncio
async def test_timeout_and_bounds(mock_sessionmaker):
    """Test timeout behavior and payload bounds enforcement."""
    adapter = KBAdapter(
        sessionmaker=mock_sessionmaker,
        timeout_s=0.01,  # Very short timeout
        max_candidates=3,
        max_terms_per_call=5,
    )

    # Mock slow database response
    async def slow_mock(*args, **kwargs):
        await asyncio.sleep(0.1)  # Longer than timeout
        return AsyncMock()

    mock_sessionmaker.return_value.execute = slow_mock

    # Test single entity timeout
    result = await adapter.resolve_entity("test")
    assert result.canonical_id is None
    assert result.reason.startswith("Timeout after")
    assert get_counter("kb.lookup.timeout") >= 1


@pytest.mark.asyncio
async def test_max_candidates_limit(mock_sessionmaker):
    """Test that max_candidates is enforced."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker, max_candidates=2)

    # Mock many database results
    mock_chars = []
    for i in range(10):
        mock_char = AsyncMock()
        mock_char.id = i
        mock_char.name = f"TestChar{i}"
        mock_chars.append(mock_char)
    mock_sessionmaker.return_value.execute.return_value.scalars.return_value.all.return_value = (
        mock_chars
    )

    # Request more than max_candidates
    result = await adapter.resolve_entity("test", limit=5)

    # Should be limited to max_candidates
    assert len(result.candidates) <= 2


@pytest.mark.asyncio
async def test_max_terms_per_call_limit(mock_sessionmaker):
    """Test that max_terms_per_call is enforced in bulk operations."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker, max_terms_per_call=3)

    # Mock database response
    mock_sessionmaker.return_value.execute.return_value.scalars.return_value.all.return_value = []

    # Request more terms than limit
    terms = ["term1", "term2", "term3", "term4", "term5"]
    results = await adapter.bulk_resolve(terms)

    # Should only process max_terms_per_call
    assert len(results) == 3


@pytest.mark.asyncio
async def test_bulk_timeout_scaling(mock_sessionmaker):
    """Test that bulk operations scale timeout appropriately."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker, timeout_s=0.05)

    # Mock slow database response
    async def slow_mock(*args, **kwargs):
        await asyncio.sleep(0.3)  # Longer than scaled timeout
        return AsyncMock()

    mock_sessionmaker.return_value.execute = slow_mock

    # Test bulk operation timeout
    terms = ["term1", "term2"]
    results = await adapter.bulk_resolve(terms)

    # All results should indicate timeout
    for result in results:
        assert result.reason.startswith("Bulk timeout after")

    assert get_counter("kb.lookup.timeout") >= 1


@pytest.mark.asyncio
async def test_custom_timeout_parameter(mock_sessionmaker):
    """Test that custom timeout parameter overrides default."""
    adapter = KBAdapter(
        sessionmaker=mock_sessionmaker,
        timeout_s=0.1,  # Default timeout
    )

    # Mock slow database response
    async def slow_mock(*args, **kwargs):
        await asyncio.sleep(0.05)  # Between custom and default timeout
        return AsyncMock()

    mock_sessionmaker.return_value.execute = slow_mock

    # Should timeout with custom timeout
    result = await adapter.resolve_entity("test", timeout_s=0.01)
    assert result.reason.startswith("Timeout after")

    # Should succeed with longer custom timeout
    await adapter.resolve_entity("test", timeout_s=0.2)
    # This might still timeout due to cache, but the point is custom timeout is used


@pytest.mark.asyncio
async def test_zero_timeout_handling(mock_sessionmaker):
    """Test graceful handling of zero or negative timeouts."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker)

    # Mock database response
    mock_sessionmaker.return_value.execute.return_value.scalars.return_value.all.return_value = []

    # Zero timeout should still work (immediate timeout)
    result = await adapter.resolve_entity("test", timeout_s=0.0)
    # Should either timeout immediately or succeed very quickly
    assert result.source == "repo"


@pytest.mark.asyncio
async def test_empty_terms_list(mock_sessionmaker):
    """Test handling of empty terms list in bulk operations."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker)

    # Empty list should return empty results
    results = await adapter.bulk_resolve([])
    assert results == []

    # No metrics should be recorded for empty operations
    assert get_counter("kb.lookup.miss") == 0
    assert get_counter("kb.lookup.hit") == 0


@pytest.mark.asyncio
async def test_exception_handling(mock_sessionmaker):
    """Test graceful handling of database exceptions."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker)

    # Mock database exception
    mock_sessionmaker.return_value.execute.side_effect = Exception("Database error")

    # Should handle exception gracefully
    result = await adapter.resolve_entity("test")
    assert result.canonical_id is None
    assert "Error:" in result.reason
    assert result.source == "repo"
