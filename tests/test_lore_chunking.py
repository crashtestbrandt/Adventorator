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

# Test constants
TEST_MANIFEST_HASH = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
TEST_PACKAGE_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


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
            provenance={"package_id": "test", "manifest_hash": TEST_MANIFEST_HASH},
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
            provenance={"package_id": "test", "manifest_hash": TEST_MANIFEST_HASH},
        )

        chunk_with = LoreChunk(
            chunk_id="TEST-001",
            title="Test Chunk",
            audience="Player",
            tags=["location:tavern"],
            content="Test content",
            source_path="test.md",
            chunk_index=0,
            provenance={"package_id": "test", "manifest_hash": TEST_MANIFEST_HASH},
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
            provenance={"package_id": "test", "manifest_hash": TEST_MANIFEST_HASH},
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
        assert payload["provenance"] == {"package_id": "test", "manifest_hash": TEST_MANIFEST_HASH}


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
        chunks = chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
        chunks = chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
        chunks_disabled = chunker_disabled.parse_lore_file(
            test_file, "test-pkg", TEST_MANIFEST_HASH
        )
        assert chunks_disabled[0].embedding_hint is None

        # Test with flag enabled
        chunker_enabled = LoreChunker(features_importer_embeddings=True)
        chunks_enabled = chunker_enabled.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)
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
            chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
            chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
            chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
            chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
            chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
            chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
            chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
        chunks = chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
        chunks = chunker.parse_lore_file(test_file, "test-pkg", TEST_MANIFEST_HASH)

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
        manifest = {"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH}

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
        manifest = {"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH}

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
        manifest = {"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH}

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
        manifest = {"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH}

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
        manifest = {"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH}

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
        chunks = chunker.parse_lore_file(fixture_path, "test-pkg", TEST_MANIFEST_HASH)

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
        chunks = chunker.parse_lore_file(fixture_path, "test-pkg", TEST_MANIFEST_HASH)

        assert len(chunks) >= 2  # Should split on headings

        # Check that code blocks are preserved
        content = "\n".join(chunk.content for chunk in chunks)
        assert "```yaml" in content
        assert "sequence:" in content

        # Check Unicode handling
        assert "Δ42" in content
        assert "Συνεχής" in content
        assert "следопыт" in content


class TestGoldenHashFixtures:
    """Test hash stability with golden reference values for regression detection."""

    def test_golden_hash_simple_chunk(self):
        """Test canonical hash stability against known golden values."""
        # Simple chunk with all basic fields
        chunk = LoreChunk(
            chunk_id="GOLDEN-SIMPLE",
            title="Simple Golden Test",
            audience="Player",
            tags=["location:tavern", "mood:peaceful"],
            content="Simple test content for hashing.",
            source_path="test.md",
            chunk_index=0,
            provenance={"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH},
        )

        # This is the expected canonical hash for this exact content
        expected_hash = "ae23a20daa3de4dab422d237e03c0c12df08b3ad88b19a46a4e079fc87ce7086"
        assert chunk.content_hash == expected_hash

    def test_golden_hash_with_embedding_hint(self):
        """Test hash stability with embedding hint included."""
        chunk = LoreChunk(
            chunk_id="GOLDEN-EMBED",
            title="Embedding Golden Test",
            audience="GM-Only",
            tags=["npc:wizard", "trait:mysterious"],
            content="Content with embedding hint for testing.",
            source_path="embed_test.md",
            chunk_index=1,
            provenance={"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH},
            embedding_hint="focus:personality",
        )

        expected_hash = "89749064b6fc7f255f40a476bd4b0f28d177c02d1f8fbef16ffc2749a2f6ef4d"
        assert chunk.content_hash == expected_hash

    def test_golden_hash_unicode_content(self):
        """Test hash stability with Unicode content after NFC normalization."""
        # Mix of composed and decomposed Unicode forms
        composed_content = "The café serves naïve customers with prémière service."
        chunk = LoreChunk(
            chunk_id="GOLDEN-UNICODE",
            title="Unicode Test",
            audience="Teen",
            tags=["culture:french"],
            content=composed_content,
            source_path="unicode.md",
            chunk_index=0,
            provenance={"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH},
        )

        expected_hash = "711fb7b0cc0b0c2dde7a9c1a0bff9f79fa5ca99e87005fb19aefc88b094cb826"
        assert chunk.content_hash == expected_hash

    def test_hash_regression_detection(self):
        """Comprehensive regression test with multiple hash values."""
        test_cases = [
            {
                "name": "minimal",
                "chunk": LoreChunk(
                    chunk_id="MIN-001",
                    title="Minimal",
                    audience="Player",
                    tags=["test:minimal"],
                    content="Min",
                    source_path="min.md",
                    chunk_index=0,
                    provenance={
                        "package_id": TEST_PACKAGE_ID,
                        "manifest_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    },
                ),
                "expected": "b66704778153305000381ee9cf0d79cc02f3f945d7f6a87fd5f8dc6dd8537b78",
            },
            {
                "name": "maximal",
                "chunk": LoreChunk(
                    chunk_id="MAX-COMPLEX-CHUNK-ID-999",
                    title="Very Complex Maximal Test Case With Long Title That Tests Length Limits",
                    audience="Adult",
                    tags=[
                        "category:complex",
                        "difficulty:maximal",
                        "type:comprehensive",
                        "status:testing",
                    ],
                    content="This is a very long and complex content block that includes multiple sentences, Unicode characters like café and naïve, and tests the limits of our chunking algorithm. It should produce a stable hash regardless of the complexity.",
                    source_path="complex/maximal/test.md",
                    chunk_index=42,
                    provenance={
                        "package_id": TEST_PACKAGE_ID,
                        "manifest_hash": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
                    },
                    embedding_hint="focus:complexity,depth:comprehensive,tone:analytical",
                ),
                "expected": "ca00fbe1a094d858e6ee58dc7a3cd621481d8a651583757735663b431eca1347",
            },
        ]

        for case in test_cases:
            actual_hash = case["chunk"].content_hash
            assert actual_hash == case["expected"], (
                f"Hash regression detected for {case['name']} case"
            )


class TestEndToEndIdempotency:
    """Test end-to-end idempotency and replay behavior per TASK-CDA-IMPORT-SEED-14B."""

    def test_deterministic_replay_behavior(self, tmp_path):
        """Test that running the importer twice produces identical results."""
        # Set up test lore files
        lore_dir = tmp_path / "lore"
        lore_dir.mkdir()

        content1 = """---
chunk_id: REPLAY-TEST-1
title: "First Test File"
audience: Player
tags:
  - location:village
  - mood:peaceful
---

## Village Square

The village square bustles with activity.

## Market Day

Vendors hawk their wares enthusiastically.
"""

        content2 = """---
chunk_id: REPLAY-TEST-2
title: "Second Test File"
audience: GM-Only
tags:
  - secret:plot
  - npc:mayor
---

The mayor harbors a dark secret.
"""

        (lore_dir / "file1.md").write_text(content1, encoding="utf-8")
        (lore_dir / "file2.md").write_text(content2, encoding="utf-8")

        phase = LorePhase(features_importer_enabled=True)
        manifest = {"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH}

        # First run
        chunks1 = phase.parse_and_validate_lore(tmp_path, manifest)
        events1 = phase.create_seed_events(chunks1)

        # Second run (should be identical)
        chunks2 = phase.parse_and_validate_lore(tmp_path, manifest)
        events2 = phase.create_seed_events(chunks2)

        # Verify deterministic ordering
        assert len(chunks1) == len(chunks2)
        for i, (chunk1, chunk2) in enumerate(zip(chunks1, chunks2)):
            assert chunk1["chunk_id"] == chunk2["chunk_id"], f"Chunk {i} ID mismatch"
            assert chunk1["content_hash"] == chunk2["content_hash"], f"Chunk {i} hash mismatch"
            assert chunk1["source_path"] == chunk2["source_path"], f"Chunk {i} path mismatch"
            assert chunk1["chunk_index"] == chunk2["chunk_index"], f"Chunk {i} index mismatch"

        # Verify event determinism
        assert len(events1) == len(events2)
        for i, (event1, event2) in enumerate(zip(events1, events2)):
            assert event1 == event2, f"Event {i} differs between runs"

    def test_idempotent_skip_metrics_on_duplicate_files(self, tmp_path):
        """Test that duplicate files are handled idempotently with proper metrics."""
        lore_dir = tmp_path / "lore"
        lore_dir.mkdir()

        # Create identical content in two files (should trigger idempotent skip)
        identical_content = """---
chunk_id: IDENTICAL-CHUNK
title: "Identical Content"
audience: Player
tags:
  - test:idempotent
---

This content is identical across files.
"""

        (lore_dir / "file1.md").write_text(identical_content, encoding="utf-8")
        (lore_dir / "file2.md").write_text(identical_content, encoding="utf-8")

        phase = LorePhase(features_importer_enabled=True)
        manifest = {"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH}

        chunks = phase.parse_and_validate_lore(tmp_path, manifest)

        # Should have only one chunk (second one skipped as idempotent duplicate)
        assert len(chunks) == 1
        assert chunks[0]["chunk_id"] == "IDENTICAL-CHUNK-000"

    def test_collision_rollback_behavior(self, tmp_path):
        """Test that collision detection properly fails the import."""
        lore_dir = tmp_path / "lore"
        lore_dir.mkdir()

        # Create conflicting content with same chunk_id
        content1 = """---
chunk_id: CONFLICT-ID
title: "First Version"
audience: Player
tags: []
---

Original content here.
"""

        content2 = """---
chunk_id: CONFLICT-ID
title: "Second Version"
audience: Player
tags: []
---

Different content that conflicts.
"""

        (lore_dir / "file1.md").write_text(content1, encoding="utf-8")
        (lore_dir / "file2.md").write_text(content2, encoding="utf-8")

        phase = LorePhase(features_importer_enabled=True)
        manifest = {"package_id": TEST_PACKAGE_ID, "manifest_hash": TEST_MANIFEST_HASH}

        # Should raise LoreCollisionError
        with pytest.raises(LoreCollisionError, match="Chunk ID collision detected"):
            phase.parse_and_validate_lore(tmp_path, manifest)


class TestFrontMatterSchemaValidation:
    """Test automated front-matter schema validation per TASK-CDA-IMPORT-CHUNK-13A."""

    def test_schema_validation_success(self, tmp_path):
        """Test that valid front-matter passes schema validation."""
        content = """---
chunk_id: SCHEMA-VALID
title: "Valid Schema Test"
audience: Player
tags:
  - location:forest
  - mood:mysterious
embedding_hint: "focus:atmosphere"
provenance:
  manifest_hash: TEST_MANIFEST_HASH
  source_path: "lore/test.md"
---

Valid content with compliant front-matter.
"""
        test_file = tmp_path / "valid.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker(features_importer_embeddings=True)
        chunks = chunker.parse_lore_file(test_file, TEST_PACKAGE_ID, TEST_MANIFEST_HASH)

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.chunk_id == "SCHEMA-VALID-000"
        assert chunk.embedding_hint == "focus:atmosphere"

    def test_schema_validation_invalid_chunk_id(self, tmp_path):
        """Test that invalid chunk_id fails schema validation."""
        content = """---
chunk_id: "invalid-lowercase-id"
title: "Invalid ID Test"
audience: Player
tags: []
---

Invalid chunk_id format.
"""
        test_file = tmp_path / "invalid_id.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker()
        # This should fail at parser validation (before schema validation)
        with pytest.raises(FrontMatterValidationError, match="Invalid chunk_id format"):
            chunker.parse_lore_file(test_file, TEST_PACKAGE_ID, TEST_MANIFEST_HASH)

    def test_schema_validation_invalid_audience(self, tmp_path):
        """Test that invalid audience fails schema validation."""
        content = """---
chunk_id: SCHEMA-BAD-AUD
title: "Bad Audience Test"
audience: "InvalidAudience"
tags: []
---

Invalid audience value.
"""
        test_file = tmp_path / "invalid_audience.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker()
        # This should fail at parser validation (before schema validation)
        with pytest.raises(FrontMatterValidationError, match="Invalid audience"):
            chunker.parse_lore_file(test_file, TEST_PACKAGE_ID, TEST_MANIFEST_HASH)

    def test_schema_validation_invalid_tag_format(self, tmp_path):
        """Test that invalid tag format fails schema validation."""
        content = """---
chunk_id: SCHEMA-BAD-TAG
title: "Bad Tag Test"
audience: Player
tags:
  - "invalid_tag_format"
  - "location:valid"
---

Invalid tag format.
"""
        test_file = tmp_path / "invalid_tag.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker()
        # This should fail at parser validation (before schema validation)
        with pytest.raises(FrontMatterValidationError, match="Invalid tag format"):
            chunker.parse_lore_file(test_file, TEST_PACKAGE_ID, TEST_MANIFEST_HASH)

    def test_schema_validation_invalid_provenance(self, tmp_path):
        """Test that invalid provenance format fails schema validation."""
        content = """---
chunk_id: SCHEMA-BAD-PROV
title: "Bad Provenance Test"
audience: Player
tags: []
provenance:
  manifest_hash: "invalid_hash_format"
  source_path: "valid/path.md"
---

Invalid provenance format.
"""
        test_file = tmp_path / "invalid_provenance.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker()
        # This should fail at parser validation (before schema validation)
        with pytest.raises(FrontMatterValidationError, match="Invalid manifest_hash format"):
            chunker.parse_lore_file(test_file, TEST_PACKAGE_ID, TEST_MANIFEST_HASH)

    def test_provenance_validation_in_parser(self, tmp_path):
        """Test that the parser validates provenance metadata correctly."""
        content = """---
chunk_id: PROV-VALID
title: "Provenance Validation Test"
audience: GM-Only
tags:
  - secret:important
provenance:
  manifest_hash: "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
  source_path: "lore/secrets/important.md"
---

Content with valid provenance metadata.
"""
        test_file = tmp_path / "prov_valid.md"
        test_file.write_text(content, encoding="utf-8")

        chunker = LoreChunker()
        chunks = chunker.parse_lore_file(test_file, TEST_PACKAGE_ID, TEST_MANIFEST_HASH)

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.chunk_id == "PROV-VALID-000"

    def test_direct_schema_validation_function(self):
        """Test the validate_front_matter_against_schema function directly."""
        from Adventorator.lore_chunker import validate_front_matter_against_schema

        # Valid front-matter should pass
        valid_fm = {
            "chunk_id": "TEST-SCHEMA",
            "title": "Schema Test",
            "audience": "Player",
            "tags": ["test:validation"],
        }
        # Should not raise any exception
        validate_front_matter_against_schema(valid_fm)

        # Invalid front-matter should fail
        invalid_fm = {
            "chunk_id": "invalid-id",  # lowercase not allowed by schema
            "title": "Invalid Schema Test",
            "audience": "Player",
            "tags": ["test:validation"],
        }
        with pytest.raises(
            FrontMatterValidationError, match="Front-matter schema validation failed"
        ):
            validate_front_matter_against_schema(invalid_fm)
