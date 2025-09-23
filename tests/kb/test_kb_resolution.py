"""Test KB resolution determinism and candidate ordering."""

import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock
from Adventorator.kb.adapter import KBAdapter, Candidate, KBResolution


@pytest.fixture
def golden_data():
    """Load golden test data."""
    fixture_path = Path("tests/kb/fixtures/golden_resolution.json")
    if fixture_path.exists():
        return json.loads(fixture_path.read_text(encoding="utf-8"))
    return {
        "canonical_entities": [],
        "ambiguous_entities": [],
        "no_match_entities": []
    }


@pytest.fixture
def mock_sessionmaker():
    """Mock sessionmaker for testing."""
    mock_session = AsyncMock()
    mock_sm = AsyncMock(return_value=mock_session)
    mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sm.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_sm


@pytest.mark.asyncio
async def test_deterministic_resolution(mock_sessionmaker, golden_data):
    """Test that KB resolution produces deterministic results for seeded data."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker)
    
    # Test canonical entities
    for entity in golden_data.get("canonical_entities", []):
        # Mock database response for exact match
        if entity["term"].lower() == "gandalf":
            mock_char = AsyncMock()
            mock_char.id = 1
            mock_char.name = "Gandalf"
            mock_sessionmaker.return_value.execute.return_value.scalars.return_value.all.return_value = [mock_char]
        elif entity["term"].lower() == "frodo":
            mock_char = AsyncMock()
            mock_char.id = 2
            mock_char.name = "Frodo"
            mock_sessionmaker.return_value.execute.return_value.scalars.return_value.all.return_value = [mock_char]
        
        result = await adapter.resolve_entity(entity["term"])
        
        # Verify deterministic results
        assert result.canonical_id == entity["expected_canonical"]
        assert result.reason == entity["expected_reason"]
        assert result.source == "repo"
        
        # Run again to ensure same result
        result2 = await adapter.resolve_entity(entity["term"])
        assert result.canonical_id == result2.canonical_id
        assert len(result.candidates) == len(result2.candidates)


@pytest.mark.asyncio 
async def test_candidates_stable_order(mock_sessionmaker, golden_data):
    """Test that ambiguous results return candidates in stable order."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker)
    
    for entity in golden_data.get("ambiguous_entities", []):
        # Mock multiple partial matches
        if entity["term"] == "guard":
            mock_chars = []
            for i, candidate in enumerate(entity["expected_candidates"], 3):
                mock_char = AsyncMock()
                mock_char.id = i
                mock_char.name = candidate["label"]
                mock_chars.append(mock_char)
            mock_sessionmaker.return_value.execute.return_value.scalars.return_value.all.return_value = mock_chars
        
        # Get result multiple times
        results = []
        for _ in range(3):
            result = await adapter.resolve_entity(entity["term"])
            results.append(result)
        
        # Verify all results have same order
        for i in range(1, len(results)):
            assert len(results[0].candidates) == len(results[i].candidates)
            for j in range(len(results[0].candidates)):
                assert results[0].candidates[j].id == results[i].candidates[j].id
                assert results[0].candidates[j].label == results[i].candidates[j].label


@pytest.mark.asyncio
async def test_empty_term_handling(mock_sessionmaker):
    """Test handling of empty or invalid terms."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker)
    
    # Test empty string
    result = await adapter.resolve_entity("")
    assert result.canonical_id is None
    assert result.candidates == []
    assert result.reason == "Empty term"
    
    # Test whitespace only
    result = await adapter.resolve_entity("   ")
    assert result.canonical_id is None
    assert result.candidates == []
    assert result.reason == "Empty term"


@pytest.mark.asyncio
async def test_bulk_resolve_determinism(mock_sessionmaker):
    """Test that bulk resolution maintains determinism."""
    adapter = KBAdapter(sessionmaker=mock_sessionmaker)
    
    terms = ["gandalf", "frodo", "nonexistent"]
    
    # Mock responses
    mock_sessionmaker.return_value.execute.return_value.scalars.return_value.all.return_value = []
    
    # Run bulk resolve multiple times
    results1 = await adapter.bulk_resolve(terms)
    results2 = await adapter.bulk_resolve(terms)
    
    assert len(results1) == len(results2)
    for i in range(len(results1)):
        assert results1[i].canonical_id == results2[i].canonical_id
        assert len(results1[i].candidates) == len(results2[i].candidates)
        assert results1[i].reason == results2[i].reason