"""Importer run context utilities for STORY-CDA-IMPORT-002F readiness.

This module does **not** implement the finalization step. Instead it provides a
lightweight aggregation layer that captures manifest metadata, per-phase counts,
and provenance digests so the final story can emit `seed.import.complete` using
existing importer outputs.

The `ImporterRunContext` exposes:

* Manifest metadata (package_id + manifest hash).
* Normalized import log entries gathered from each phase.
* Deterministic count helpers for entities, edges, ontology items, and lore
  chunks.
* A canonical state digest computation that reuses the repository-wide
  `compute_canonical_hash` helper mandated by ARCH-CDA-001.

Tests are provided under `tests/importer/test_importer_context.py` and the
golden fixture digest is asserted by
`tests/importer/test_state_digest_fixture.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from Adventorator.canonical_json import compute_canonical_hash


def _log_entry_identity(entry: Mapping[str, Any]) -> tuple[str, str, str | None]:
    """Create a stable identity tuple for ImportLog entries.

    Args:
        entry: ImportLog entry containing at least phase and stable_id.

    Returns:
        Tuple used for deduplication across phases.
    """

    phase = str(entry.get("phase", ""))
    stable_id = str(entry.get("stable_id", ""))
    file_hash = entry.get("file_hash")
    if file_hash is not None:
        file_hash = str(file_hash)
    return phase, stable_id, file_hash


@dataclass
class ImporterRunContext:
    """Collects importer phase outputs for readiness validation.

    The context surfaces deterministic counts and provenance so the final story
    can emit completion events and ImportLog summaries without additional
    plumbing. It deliberately avoids any database or event-emission side
    effects.
    """

    manifest: dict[str, Any] | None = None
    manifest_hash: str | None = None
    package_id: str | None = None
    entities: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    ontology_tags: list[dict[str, Any]] = field(default_factory=list)
    ontology_affordances: list[dict[str, Any]] = field(default_factory=list)
    lore_chunks: list[dict[str, Any]] = field(default_factory=list)
    _import_logs: list[dict[str, Any]] = field(default_factory=list)
    _log_identities: set[tuple[str, str, str | None]] = field(
        default_factory=set, init=False
    )
    _sequence_counter: int = field(default=0, init=False)

    def next_sequence_number(self) -> int:
        """Get the next sequence number for ImportLog entries."""
        self._sequence_counter += 1
        return self._sequence_counter

    def record_manifest(self, manifest_result: Mapping[str, Any]) -> None:
        """Record manifest metadata from the manifest phase.

        Args:
            manifest_result: Output from ``ManifestPhase.validate_and_register``.
        """

        manifest = manifest_result.get("manifest")
        manifest_hash = manifest_result.get("manifest_hash")
        if not isinstance(manifest, Mapping) or not isinstance(manifest_hash, str):
            raise ValueError("Manifest result must include manifest and manifest_hash")

        manifest_dict = dict(manifest)
        manifest_dict.setdefault("manifest_hash", manifest_hash)
        self.manifest = manifest_dict
        self.manifest_hash = manifest_hash
        self.package_id = manifest_dict.get("package_id")

        log_entry = manifest_result.get("import_log_entry")
        if isinstance(log_entry, Mapping):
            self._merge_import_logs([log_entry])

    def record_entities(self, entities: Iterable[Mapping[str, Any]]) -> None:
        """Store entity phase output and associated ImportLog entries."""

        self.entities = [dict(entity) for entity in entities]
        if not self.entities:
            return

        provenance = self.entities[0].get("provenance")
        if isinstance(provenance, Mapping) and not self.package_id:
            self.package_id = provenance.get("package_id")

        # Collect ImportLog entries from all entities, not just the first one
        all_log_entries = []
        for entity in self.entities:
            log_entries = entity.get("import_log_entries")
            if isinstance(log_entries, Iterable):
                all_log_entries.extend(log_entries)
        
        if all_log_entries:
            self._merge_import_logs(all_log_entries)

    def record_edges(self, edges: Iterable[Mapping[str, Any]]) -> None:
        """Store edge phase output and associated ImportLog entries."""

        self.edges = [dict(edge) for edge in edges]
        if not self.edges:
            return

        log_entries = [
            edge.get("import_log_entry")
            for edge in self.edges
            if isinstance(edge.get("import_log_entry"), Mapping)
        ]
        self._merge_import_logs(log_entries)

    def record_ontology(
        self,
        tags: Iterable[Mapping[str, Any]],
        affordances: Iterable[Mapping[str, Any]],
        import_log_entries: Iterable[Mapping[str, Any]] | None = None,
    ) -> None:
        """Store ontology phase output and ImportLog entries."""

        self.ontology_tags = [dict(tag) for tag in tags]
        self.ontology_affordances = [dict(aff) for aff in affordances]
        if import_log_entries is not None:
            self._merge_import_logs(import_log_entries)

    def record_lore_chunks(self, chunks: Iterable[Mapping[str, Any]]) -> None:
        """Store lore phase output and associated ImportLog entries."""

        self.lore_chunks = [dict(chunk) for chunk in chunks]
        if not self.lore_chunks:
            return

        # Collect ImportLog entries from all chunks, not just the first one
        all_log_entries = []
        for chunk in self.lore_chunks:
            log_entries = chunk.get("import_log_entries")
            if isinstance(log_entries, Iterable):
                all_log_entries.extend(log_entries)
        
        if all_log_entries:
            self._merge_import_logs(all_log_entries)

    def summary_counts(self) -> dict[str, int]:
        """Return deterministic counts for each phase output."""

        return {
            "entities": len(self.entities),
            "edges": len(self.edges),
            "tags": len(self.ontology_tags),
            "affordances": len(self.ontology_affordances),
            "chunks": len(self.lore_chunks),
        }

    @property
    def import_log_entries(self) -> list[dict[str, Any]]:
        """Return ImportLog entries sorted by phase + sequence."""

        def sort_key(entry: Mapping[str, Any]) -> tuple[str, int, str]:
            phase = str(entry.get("phase", ""))
            sequence = entry.get("sequence_no")
            if not isinstance(sequence, int):
                sequence = -1
            stable_id = str(entry.get("stable_id", ""))
            return (phase, sequence, stable_id)

        return sorted(self._import_logs, key=sort_key)

    def state_digest_components(self) -> list[dict[str, str]]:
        """Return canonical components used for state digest calculation."""

        components: list[dict[str, str]] = []

        if self.manifest and self.manifest_hash:
            package_id = str(self.manifest.get("package_id", ""))
            components.append(
                {
                    "phase": "manifest",
                    "stable_id": package_id,
                    "content_hash": self.manifest_hash,
                }
            )

        def append_components(
            phase: str,
            records: Iterable[Mapping[str, Any]],
            stable_field: str,
            hash_field: str,
        ) -> None:
            for record in records:
                stable_id = record.get(stable_field)
                if not isinstance(stable_id, str):
                    continue
                provenance = record.get("provenance", {})
                content_hash = provenance.get(hash_field)
                if not isinstance(content_hash, str):
                    continue
                components.append(
                    {
                        "phase": phase,
                        "stable_id": stable_id,
                        "content_hash": content_hash,
                    }
                )

        append_components("entity", self.entities, "stable_id", "file_hash")
        append_components("edge", self.edges, "stable_id", "file_hash")

        for tag in self.ontology_tags:
            tag_id = tag.get("tag_id")
            prov = tag.get("provenance", {})
            tag_hash = prov.get("file_hash")
            if isinstance(tag_id, str) and isinstance(tag_hash, str):
                components.append(
                    {
                        "phase": "ontology.tag",
                        "stable_id": tag_id,
                        "content_hash": tag_hash,
                    }
                )

        for affordance in self.ontology_affordances:
            affordance_id = affordance.get("affordance_id")
            prov = affordance.get("provenance", {})
            affordance_hash = prov.get("file_hash")
            if isinstance(affordance_id, str) and isinstance(affordance_hash, str):
                components.append(
                    {
                        "phase": "ontology.affordance",
                        "stable_id": affordance_id,
                        "content_hash": affordance_hash,
                    }
                )

        for chunk in self.lore_chunks:
            chunk_id = chunk.get("chunk_id")
            content_hash = chunk.get("content_hash")
            if isinstance(chunk_id, str) and isinstance(content_hash, str):
                components.append(
                    {
                        "phase": "lore",
                        "stable_id": chunk_id,
                        "content_hash": content_hash,
                    }
                )

        components.sort(
            key=lambda item: (item["phase"], item["stable_id"], item["content_hash"])
        )
        return components

    def compute_state_digest(self) -> str:
        """Compute canonical state digest using repository hashing helper."""

        payload = {"state_components": self.state_digest_components()}
        digest_bytes = compute_canonical_hash(payload)
        return digest_bytes.hex()

    def _merge_import_logs(
        self, entries: Iterable[Mapping[str, Any]] | None
    ) -> None:
        if entries is None:
            return
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            identity = _log_entry_identity(entry)
            if identity in self._log_identities:
                continue
            self._log_identities.add(identity)
            self._import_logs.append(dict(entry))


__all__ = ["ImporterRunContext"]

