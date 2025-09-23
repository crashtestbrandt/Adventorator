"""Test KB cache behavior and metrics."""

import time
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
async def test_hit_miss_counters(mock_sessionmaker):
    """Test cache hit/miss counters increment correctly."""
    adapter = KBAdapter(
        sessionmaker=mock_sessionmaker,
        cache_ttl_s=60.0,
        cache_max_size=10
    )
    
    # Mock database response
    mock_char = AsyncMock()
    mock_char.id = 1
    mock_char.name = "TestChar"
    mock_sessionmaker.return_value.execute.return_value.\
        scalars.return_value.all.return_value = [mock_char]
    
    # First call should be a miss
    await adapter.resolve_entity("testchar")
    assert get_counter("kb.lookup.miss") == 1
    assert get_counter("kb.lookup.hit") == 0
    
    # Second call should be a hit
    await adapter.resolve_entity("testchar")
    assert get_counter("kb.lookup.miss") == 1
    assert get_counter("kb.lookup.hit") == 1
    
    # Third call should still be a hit
    await adapter.resolve_entity("testchar")
    assert get_counter("kb.lookup.miss") == 1
    assert get_counter("kb.lookup.hit") == 2


@pytest.mark.asyncio
async def test_cache_ttl_expiry(mock_sessionmaker):
    """Test that cache entries expire after TTL."""
    adapter = KBAdapter(
        sessionmaker=mock_sessionmaker,
        cache_ttl_s=0.1,  # Very short TTL for testing
        cache_max_size=10
    )
    
    # Mock database response
    mock_char = AsyncMock()
    mock_char.id = 1
    mock_char.name = "TestChar"
    mock_sessionmaker.return_value.execute.return_value.\
        scalars.return_value.all.return_value = [mock_char]
    
    # First call - miss
    await adapter.resolve_entity("testchar")
    assert get_counter("kb.lookup.miss") == 1
    
    # Second call immediately - hit
    await adapter.resolve_entity("testchar")
    assert get_counter("kb.lookup.hit") == 1
    
    # Wait for TTL to expire
    time.sleep(0.2)
    
    # Third call after expiry - miss again
    await adapter.resolve_entity("testchar")
    assert get_counter("kb.lookup.miss") == 2
    assert get_counter("kb.cache.evicted") >= 1


@pytest.mark.asyncio
async def test_cache_size_limit(mock_sessionmaker):
    """Test that cache evicts old entries when size limit reached."""
    adapter = KBAdapter(
        sessionmaker=mock_sessionmaker,
        cache_ttl_s=60.0,
        cache_max_size=2  # Very small cache
    )
    
    # Mock database responses
    mock_sessionmaker.return_value.execute.return_value.scalars.return_value.all.return_value = []
    
    # Fill cache to capacity
    await adapter.resolve_entity("term1")
    await adapter.resolve_entity("term2")
    
    # Add one more - should evict oldest
    await adapter.resolve_entity("term3")
    
    # Check if eviction occurred
    assert get_counter("kb.cache.evicted") >= 1


@pytest.mark.asyncio
async def test_cache_key_normalization(mock_sessionmaker):
    """Test that cache keys are normalized for consistent behavior."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker)
    
    # Mock database response
    mock_char = AsyncMock()
    mock_char.id = 1
    mock_char.name = "TestChar"
    mock_sessionmaker.return_value.execute.return_value.\
        scalars.return_value.all.return_value = [mock_char]
    
    # Different cases/whitespace should hit same cache entry
    await adapter.resolve_entity("TestChar")
    await adapter.resolve_entity("testchar")
    await adapter.resolve_entity("  TESTCHAR  ")
    
    # Should have 1 miss and 2 hits
    assert get_counter("kb.lookup.miss") == 1
    assert get_counter("kb.lookup.hit") == 2


@pytest.mark.asyncio
async def test_different_limits_different_cache_keys(mock_sessionmaker):
    """Test that different limit parameters create different cache entries."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker)
    
    # Mock database response
    mock_chars = []
    for i in range(5):
        mock_char = AsyncMock()
        mock_char.id = i
        mock_char.name = f"TestChar{i}"
        mock_chars.append(mock_char)
    mock_sessionmaker.return_value.execute.return_value.\
        scalars.return_value.all.return_value = mock_chars
    
    # Same term with different limits should be separate cache entries
    await adapter.resolve_entity("test", limit=3)
    await adapter.resolve_entity("test", limit=5)
    await adapter.resolve_entity("test", limit=3)  # Should hit cache
    
    # Should have 2 misses and 1 hit
    assert get_counter("kb.lookup.miss") == 2
    assert get_counter("kb.lookup.hit") == 1