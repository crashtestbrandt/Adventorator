"""Tests for lore content chunking implementation (STORY-CDA-IMPORT-002E)."""

import unicodedata
from pathlib import Path

import pytest

from Adventorator.importer import (
    ImporterError,
    LoreCollisionError,
    LorePhase,
    LoreValidationError,
    create_lore_phase,
)
from Adventorator.lore_chunker import (
    FrontMatterValidationError,
    LoreChunk,
    LoreChunker,
)


class TestLoreChunk:
    """Test the LoreChunk data class."""

    def test_content_hash_deterministic(self):
        """Test that content hash is deterministic and stable."""
        chunk = LoreChunk(
            chunk_id="TEST-001",
            title="Test Chunk",
            audience="Player",
            tags=["location:tavern", "mood:melancholy"],
            content="Test content with ünicøde",
            source_path="test.md",
            chunk_index=0,
            provenance={"package_id": "test", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"},
        )

        hash1 = chunk.content_hash
        hash2 = chunk.content_hash  # Should use cached value

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex string
        assert hash1.isalnum()

    def test_content_hash_with_embedding_hint(self):
        """Test that embedding_hint affects hash when present."""
        chunk_without = LoreChunk(
            chunk_id="TEST-001",
            title="Test Chunk",
            audience="Player",
            tags=["location:tavern"],
            content="Test content",
            source_path="test.md",
            chunk_index=0,
            provenance={"package_id": "test", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"},
        )

        chunk_with = LoreChunk(
            chunk_id="TEST-001",
            title="Test Chunk",
            audience="Player",
            tags=["location:tavern"],
            content="Test content",
            source_path="test.md",
            chunk_index=0,
            provenance={"package_id": "test", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"},
            embedding_hint="focus:atmosphere",
        )

        assert chunk_without.content_hash != chunk_with.content_hash

    def test_word_count(self):
        """Test word count calculation."""
        chunk = LoreChunk(
            chunk_id="TEST-001",
            title="Test",
            audience="Player",
            tags=[],
            content="This is a test with five words.",
            source_path="test.md",
            chunk_index=0,
            provenance={},
        )

        assert chunk.word_count == 7

    def test_to_event_payload(self):
        """Test conversion to event payload."""
        chunk = LoreChunk(
            chunk_id="TEST-001",
            title="Test Chunk",
            audience="Player",
            tags=["location:tavern", "mood:melancholy"],
            content="Test content",
            source_path="test.md",
            chunk_index=0,
            provenance={"package_id": "test", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"},
            embedding_hint="focus:atmosphere",
        )

        payload = chunk.to_event_payload()

        assert payload["chunk_id"] == "TEST-001"
        assert payload["title"] == "Test Chunk"
        assert payload["audience"] == "Player"
        assert payload["tags"] == ["location:tavern", "mood:melancholy"]  # Sorted
        assert payload["source_path"] == "test.md"
        assert payload["chunk_index"] == 0
        assert payload["word_count"] == 2
        assert payload["embedding_hint"] == "focus:atmosphere"
        assert "content_hash" in payload
        assert payload["provenance"] == {"package_id": "test", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"}


class TestLoreChunker:
    """Test the LoreChunker class."""

    def test_init_with_feature_flags(self):
        """Test chunker initialization with feature flags."""
        chunker_disabled = LoreChunker(features_importer_embeddings=False)
        chunker_enabled = LoreChunker(features_importer_embeddings=True)

        assert not chunker_disabled.features_importer_embeddings
        assert chunker_enabled.features_importer_embeddings

    def test_parse_simple_file(self, tmp_path):
        """Test parsing a simple lore file."""
        content = """---
chunk_id: TEST-SIMPLE
title: "Simple Test"
audience: Player
tags:
  - location:tavern
  - mood:peaceful
---

## Opening Scene

The tavern is quiet tonight.

## Later

Patrons begin to arrive.
"""
        test_file = tmp_path / "simple.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker()
        chunks = chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

        assert len(chunks) == 2  # Split by ## headings

        # Check first chunk
        chunk0 = chunks[0]
        assert chunk0.chunk_id == "TEST-SIMPLE-000"
        assert chunk0.title == "Simple Test"
        assert chunk0.audience == "Player"
        assert chunk0.tags == ["location:tavern", "mood:peaceful"]
        assert "The tavern is quiet tonight." in chunk0.content
        assert chunk0.chunk_index == 0

        # Check second chunk
        chunk1 = chunks[1]
        assert chunk1.chunk_id == "TEST-SIMPLE-001"
        assert "Patrons begin to arrive." in chunk1.content
        assert chunk1.chunk_index == 1

    def test_unicode_normalization(self, tmp_path):
        """Test Unicode normalization in content and front-matter."""
        # Using different Unicode forms of 'é'
        composed = "café"  # NFC form
        decomposed = unicodedata.normalize("NFD", composed)  # NFD form

        content = f"""---
chunk_id: TEST-UNICODE
title: "{composed}"
audience: Player
tags:
  - location:tavern
---

Content with {composed} and {decomposed}.
"""
        test_file = tmp_path / "unicode.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker()
        chunks = chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

        assert len(chunks) == 1
        chunk = chunks[0]

        # All Unicode should be normalized to NFC in title and content
        assert "café" in chunk.title
        assert "café" in chunk.content
        # Hash should be deterministic despite different input forms
        assert chunk.content_hash

    def test_embedding_hint_feature_flag(self, tmp_path):
        """Test embedding_hint processing with feature flag."""
        content = """---
chunk_id: TEST-EMBED
title: "Embedding Test"
audience: Player
tags:
  - test:flag
embedding_hint: "focus:atmosphere"
---

Test content with embedding hint.
"""
        test_file = tmp_path / "embed.md"
        test_file.write_text(content, encoding="utf-8")

        # Test with flag disabled
        chunker_disabled = LoreChunker(features_importer_embeddings=False)
        chunks_disabled = chunker_disabled.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")
        assert chunks_disabled[0].embedding_hint is None

        # Test with flag enabled
        chunker_enabled = LoreChunker(features_importer_embeddings=True)
        chunks_enabled = chunker_enabled.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")
        assert chunks_enabled[0].embedding_hint == "focus:atmosphere"

        # Hashes should be different because the enabled version includes the hint
        assert chunks_disabled[0].content_hash != chunks_enabled[0].content_hash

    def test_front_matter_validation_errors(self, tmp_path):
        """Test various front-matter validation errors."""
        # Missing front-matter
        test_file = tmp_path / "no_front_matter.md"
        test_file.write_text("Just content without front-matter.", encoding="utf-8")

        chunker = LoreChunker()
        with pytest.raises(FrontMatterValidationError, match="Missing YAML front-matter"):
            chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

        # Invalid YAML
        invalid_yaml = """---
chunk_id: TEST
title: "Test
invalid: yaml: content:
---
Content
"""
        test_file.write_text(invalid_yaml, encoding="utf-8")
        with pytest.raises(FrontMatterValidationError, match="Invalid YAML front-matter"):
            chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

        # Missing required fields
        missing_field = """---
chunk_id: TEST
title: "Test"
# audience: Player  # Missing required field
tags: []
---
Content
"""
        test_file.write_text(missing_field, encoding="utf-8")
        with pytest.raises(FrontMatterValidationError, match="Missing required field 'audience'"):
            chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_chunk_id_validation(self, tmp_path):
        """Test chunk_id format validation."""
        # Invalid characters
        invalid_content = """---
chunk_id: test-invalid-lowercase
title: "Test"
audience: Player
tags: []
---
Content
"""
        test_file = tmp_path / "invalid_id.md"
        test_file.write_text(invalid_content, encoding="utf-8")

        chunker = LoreChunker()
        with pytest.raises(FrontMatterValidationError, match="Invalid chunk_id format"):
            chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_audience_validation(self, tmp_path):
        """Test audience value validation."""
        invalid_content = """---
chunk_id: TEST-AUDIENCE
title: "Test"
audience: InvalidAudience
tags: []
---
Content
"""
        test_file = tmp_path / "invalid_audience.md"
        test_file.write_text(invalid_content, encoding="utf-8")

        chunker = LoreChunker()
        with pytest.raises(FrontMatterValidationError, match="Invalid audience"):
            chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_tag_format_validation(self, tmp_path):
        """Test tag format validation."""
        invalid_content = """---
chunk_id: TEST-TAGS
title: "Test"
audience: Player
tags:
  - invalid_tag_format
  - location:valid
---
Content
"""
        test_file = tmp_path / "invalid_tags.md"
        test_file.write_text(invalid_content, encoding="utf-8")

        chunker = LoreChunker()
        with pytest.raises(FrontMatterValidationError, match="Invalid tag format"):
            chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_embedding_hint_length_validation(self, tmp_path):
        """Test embedding_hint length validation."""
        long_hint = "x" * 129  # Too long
        invalid_content = f"""---
chunk_id: TEST-EMBED
title: "Test"
audience: Player
tags: []
embedding_hint: "{long_hint}"
---
Content
"""
        test_file = tmp_path / "long_hint.md"
        test_file.write_text(invalid_content, encoding="utf-8")

        chunker = LoreChunker()
        with pytest.raises(FrontMatterValidationError, match="embedding_hint too long"):
            chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_chunking_by_headings(self, tmp_path):
        """Test content splitting by heading boundaries."""
        content = """---
chunk_id: TEST-HEADINGS
title: "Heading Test"
audience: Player
tags: []
---

Introduction paragraph.

## First Section

Content of first section.

### Subsection

Subsection content.

## Second Section

Content of second section.

#### Deep heading

Deep content.
"""
        test_file = tmp_path / "headings.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker()
        chunks = chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

        # Should split on ## headings (level 2+)
        assert len(chunks) >= 2

        # Check content distribution
        chunk_contents = [chunk.content for chunk in chunks]
        combined_content = "\n".join(chunk_contents)

        assert "Introduction paragraph." in combined_content
        assert "First Section" in combined_content
        assert "Second Section" in combined_content

    def test_token_limit_splitting(self, tmp_path):
        """Test content splitting by token limits."""
        # Create content that exceeds token limit
        long_paragraph = "This is a very long paragraph. " * 200  # Should exceed default limit

        content = f"""---
chunk_id: TEST-LONG
title: "Long Test"
audience: Player
tags: []
---

{long_paragraph}

Another paragraph that should be in a separate chunk due to length.
"""
        test_file = tmp_path / "long.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker(max_tokens=100)  # Small limit for testing
        chunks = chunker.parse_lore_file(test_file, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

        # Should split into multiple chunks due to length
        assert len(chunks) > 1

        # Each chunk should be within reasonable limits
        for chunk in chunks:
            assert len(chunk.content) <= chunker.max_chars * 2  # Allow some flexibility


class TestLorePhase:
    """Test the LorePhase class integration."""

    def test_init_with_feature_flags(self):
        """Test LorePhase initialization with feature flags."""
        phase = LorePhase(
            features_importer_enabled=True,
            features_importer_embeddings=True,
        )

        assert phase.features_importer_enabled
        assert phase.features_importer_embeddings

    def test_feature_flag_disabled_error(self, tmp_path):
        """Test error when importer feature flag is disabled."""
        phase = LorePhase(features_importer_enabled=False)
        manifest = {"package_id": "test"}

        with pytest.raises(ImporterError, match="Importer feature flag is disabled"):
            phase.parse_and_validate_lore(tmp_path, manifest)

    def test_no_lore_directory(self, tmp_path):
        """Test handling when no lore directory exists."""
        phase = LorePhase(features_importer_enabled=True)
        manifest = {"package_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"}

        chunks = phase.parse_and_validate_lore(tmp_path, manifest)
        assert len(chunks) == 0

    def test_parse_multiple_files(self, tmp_path):
        """Test parsing multiple lore files in deterministic order."""
        lore_dir = tmp_path / "lore"
        lore_dir.mkdir()

        # Create files in non-alphabetical order to test sorting
        file2_content = """---
chunk_id: FILE2-CHUNK
title: "File 2"
audience: Player
tags: []
---
Content from file 2.
"""

        file1_content = """---
chunk_id: FILE1-CHUNK
title: "File 1" 
audience: Player
tags: []
---
Content from file 1.
"""

        (lore_dir / "file_b.md").write_text(file2_content, encoding="utf-8")
        (lore_dir / "file_a.md").write_text(file1_content, encoding="utf-8")

        phase = LorePhase(features_importer_enabled=True)
        manifest = {"package_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"}

        chunks = phase.parse_and_validate_lore(tmp_path, manifest)

        assert len(chunks) == 2
        # Should be sorted by file path, so file_a comes before file_b
        assert chunks[0]["chunk_id"] == "FILE1-CHUNK-000"
        assert chunks[1]["chunk_id"] == "FILE2-CHUNK-000"

    def test_collision_detection(self, tmp_path):
        """Test chunk_id collision detection."""
        lore_dir = tmp_path / "lore"
        lore_dir.mkdir()

        # Two files with same chunk_id but different content
        file1_content = """---
chunk_id: DUPLICATE-ID
title: "File 1"
audience: Player
tags: []
---
Different content 1.
"""

        file2_content = """---
chunk_id: DUPLICATE-ID
title: "File 2"
audience: Player
tags: []
---
Different content 2.
"""

        (lore_dir / "file1.md").write_text(file1_content, encoding="utf-8")
        (lore_dir / "file2.md").write_text(file2_content, encoding="utf-8")

        phase = LorePhase(features_importer_enabled=True)
        manifest = {"package_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"}

        with pytest.raises(LoreCollisionError, match="Chunk ID collision detected"):
            phase.parse_and_validate_lore(tmp_path, manifest)

    def test_idempotent_duplicates(self, tmp_path):
        """Test idempotent handling of identical chunks."""
        lore_dir = tmp_path / "lore"
        lore_dir.mkdir()

        # Two files with same content (should be idempotent)
        identical_content = """---
chunk_id: IDENTICAL-CHUNK
title: "Identical"
audience: Player
tags: []
---
Identical content.
"""

        (lore_dir / "file1.md").write_text(identical_content, encoding="utf-8")
        (lore_dir / "file2.md").write_text(identical_content, encoding="utf-8")

        phase = LorePhase(features_importer_enabled=True)
        manifest = {"package_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"}

        chunks = phase.parse_and_validate_lore(tmp_path, manifest)

        # Should deduplicate to single chunk
        assert len(chunks) == 1
        assert chunks[0]["chunk_id"] == "IDENTICAL-CHUNK-000"

    def test_create_seed_events(self, tmp_path):
        """Test seed event creation from chunks."""
        lore_dir = tmp_path / "lore"
        lore_dir.mkdir()

        content = """---
chunk_id: TEST-EVENT
title: "Event Test"
audience: Player
tags:
  - location:tavern
  - mood:cheerful
embedding_hint: "focus:atmosphere"
---
Test content for event.
"""
        (lore_dir / "test.md").write_text(content, encoding="utf-8")

        phase = LorePhase(
            features_importer_enabled=True,
            features_importer_embeddings=True,
        )
        # Use proper ULID format for package_id and 64-char hex for manifest_hash
        manifest = {"package_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "manifest_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"}

        chunks = phase.parse_and_validate_lore(tmp_path, manifest)
        events = phase.create_seed_events(chunks)

        assert len(events) == 1
        event = events[0]

        assert event["chunk_id"] == "TEST-EVENT-000"
        assert event["title"] == "Event Test"
        assert event["audience"] == "Player"
        assert event["tags"] == ["location:tavern", "mood:cheerful"]
        assert event["embedding_hint"] == "focus:atmosphere"
        assert "content_hash" in event
        assert "provenance" in event


class TestFactoryFunctions:
    """Test factory functions."""

    def test_create_lore_phase(self):
        """Test create_lore_phase factory function."""
        phase = create_lore_phase(
            features_importer=True,
            features_importer_embeddings=True,
        )

        assert isinstance(phase, LorePhase)
        assert phase.features_importer_enabled
        assert phase.features_importer_embeddings


class TestIntegrationWithFixtures:
    """Integration tests using the existing fixture files."""

    def test_parse_simple_fixture(self):
        """Test parsing the simple fixture file."""
        fixture_path = Path("tests/fixtures/import/lore/simple/moonlight-tavern.md")
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        chunker = LoreChunker(features_importer_embeddings=True)
        chunks = chunker.parse_lore_file(fixture_path, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

        assert len(chunks) >= 1
        chunk = chunks[0]

        # Check front-matter parsing
        assert chunk.chunk_id.startswith("LORE-SIMPLE-MOONLIGHT")
        assert chunk.title == "Moonlight at the Whispering Tavern"
        assert chunk.audience == "Teen"
        assert "location:tavern" in chunk.tags
        assert chunk.embedding_hint == "focus:whispers"

        # Check Unicode content handling
        assert "æthereal" in chunk.content or any("æthereal" in c.content for c in chunks)
        assert "こんにちは" in chunk.content or any("こんにちは" in c.content for c in chunks)

    def test_parse_complex_fixture(self):
        """Test parsing the complex fixture file."""
        fixture_path = Path("tests/fixtures/import/lore/complex/clockwork-archive.md")
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        chunker = LoreChunker()
        chunks = chunker.parse_lore_file(fixture_path, "test-pkg", "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

        assert len(chunks) >= 2  # Should split on headings

        # Check that code blocks are preserved
        content = "\n".join(chunk.content for chunk in chunks)
        assert "```yaml" in content
        assert "sequence:" in content

        # Check Unicode handling
        assert "Δ42" in content
        assert "Συνεχής" in content
        assert "следопыт" in content
