#!/usr/bin/env python3
"""Validate prompt and contract registries for naming and metadata conventions."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Tuple

PROMPT_EXTS = {".md"}
CONTRACT_EXTS = {".json", ".yaml", ".yml"}
VERSION_RE = re.compile(r"v(\d+)(?:[._](\d+))?", re.IGNORECASE)
FRONT_MATTER_RE = re.compile(r"^---\n(?P<meta>.*?)\n---\n", re.DOTALL)
REQUIRED_PROMPT_KEYS = {"id", "version", "owner", "model"}


def iter_artifacts(root: Path, exts: set[str]) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "README.md":
            continue
        if path.suffix.lower() in exts:
            yield path


def parse_front_matter(text: str) -> dict[str, str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for line in match.group("meta").splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            continue
        parts = line.split(":", 1)
        key, value = parts
        key = key.strip()
        if not key:
            continue
        meta[key.lower()] = value.strip()
    return meta


def validate_prompts() -> list[str]:
    errors: list[str] = []
    prompt_dir = Path("prompts")
    if not prompt_dir.exists():
        return ["prompts directory is missing"]

    artifacts = list(iter_artifacts(prompt_dir, PROMPT_EXTS))
    if not artifacts:
        print("No prompt artifacts found; skipping metadata enforcement.")
        return errors

    for path in artifacts:
        relative = path.relative_to(prompt_dir)
        if relative.parts and relative.parts[0] == "evals":
            continue
        stem = path.stem
        if VERSION_RE.search(stem) is None:
            errors.append(
                f"{path}: filename must include semantic version token like '-v1' or '-v1_0'"
            )
        text = path.read_text(encoding="utf-8")
        meta = parse_front_matter(text)
        missing_keys = [key for key in REQUIRED_PROMPT_KEYS if key not in meta]
        if missing_keys:
            errors.append(f"{path}: missing front-matter keys: {', '.join(sorted(missing_keys))}")
        if "adr" not in meta:
            errors.append(f"{path}: front-matter must link an ADR via 'adr'")
    return errors


def validate_contracts(skip_manifest: bool = False) -> list[str]:
    errors: list[str] = []
    contracts_dir = Path("contracts")
    if not contracts_dir.exists():
        return ["contracts directory is missing"]

    artifacts = list(iter_artifacts(contracts_dir, CONTRACT_EXTS))
    if not artifacts:
        print("No contract artifacts found; skipping schema enforcement.")
        return errors

    for path in artifacts:
        stem = path.stem
        version_match = VERSION_RE.search(stem)
        if version_match is None:
            relative_parts = path.relative_to(contracts_dir).parts
            version_match = next(
                (VERSION_RE.search(part) for part in relative_parts if VERSION_RE.search(part)),
                None,
            )
        if version_match is None:
            errors.append(
                f"{path}: provide a version token in the filename or one of the containing folders"
            )
            continue
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{path}: invalid JSON - {exc}")
                continue
            # Only enforce OpenAPI schema for HTTP API contracts
            rel_parts = path.relative_to(contracts_dir).parts
            if "http" in rel_parts and "openapi" not in data:
                errors.append(f"{path}: expected 'openapi' field for API contracts under contracts/http")
        else:
            # YAML support deferred; ensure placeholder files are obvious.
            text = path.read_text(encoding="utf-8")
            if "openapi" not in text:
                errors.append(f"{path}: expected to mention 'openapi' for schema traceability")
    
    if not skip_manifest:
        # Validate manifest fixtures against schema
        errors.extend(validate_manifest_fixtures())
    return errors
def _load_json(path: Path) -> Tuple[dict[str, Any] | list[Any], str | None]:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text), None
    except Exception as exc:  # noqa: BLE001
        return {}, f"{path}: failed to load JSON - {exc}"


def validate_ontology(only_contracts: bool = False) -> list[str]:
    """Validate ontology artifacts under contracts/ontology.

    Rules:
    - Each *.json (excluding README) in contracts/ontology is a collection object with optional version
      and arrays: tags[], affordances[] (either may be absent or empty).
    - Each tag validates against tag.v1.json; each affordance validates against affordance.v1.json.
    - Unknown top-level keys in tag / affordance objects rejected (schema has additionalProperties=false).
    - Duplicate IDs with identical canonical JSON (excluding ordering/whitespace) are idempotent.
    - Duplicate IDs with differing canonical forms produce hard error with short hash diff.
    Timing summary emitted for observability.
    """
    errors: list[str] = []
    ontology_dir = Path("contracts/ontology")
    if not ontology_dir.exists():
        return ["contracts/ontology directory is missing"]

    try:
        import jsonschema  # type: ignore
    except ImportError:
        return ["jsonschema not installed; cannot validate ontology"]

    tag_schema_path = ontology_dir / "tag.v1.json"
    afford_schema_path = ontology_dir / "affordance.v1.json"
    if not tag_schema_path.exists() or not afford_schema_path.exists():
        missing = [p.name for p in [tag_schema_path, afford_schema_path] if not p.exists()]
        return [f"missing ontology schema(s): {', '.join(missing)}"]

    tag_schema = json.loads(tag_schema_path.read_text(encoding="utf-8"))
    afford_schema = json.loads(afford_schema_path.read_text(encoding="utf-8"))

    collection_files = [
        p for p in sorted(ontology_dir.glob("*.json")) if p.name not in {"tag.v1.json", "affordance.v1.json"}
    ]
    if not collection_files:
        print("No ontology collection files found (ok if not yet authored).")
        return errors

    def canonical(obj: Any) -> str:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))

    tag_index: dict[str, str] = {}
    tag_source: dict[str, Path] = {}
    afford_index: dict[str, str] = {}
    afford_source: dict[str, Path] = {}

    timings: list[float] = []
    total_items = 0
    for file_path in collection_files:
        start = time.perf_counter()
        data, load_err = _load_json(file_path)
        if load_err:
            errors.append(load_err)
            continue
        if not isinstance(data, dict):
            errors.append(f"{file_path}: collection root must be an object")
            continue
        tags = data.get("tags", [])
        affords = data.get("affordances", [])
        if tags and not isinstance(tags, list):
            errors.append(f"{file_path}: 'tags' must be an array")
            tags = []
        if affords and not isinstance(affords, list):
            errors.append(f"{file_path}: 'affordances' must be an array")
            affords = []
        # Validate tags
        for i, tag in enumerate(tags):
            total_items += 1
            if not isinstance(tag, dict):
                errors.append(f"{file_path}: tags[{i}] must be an object")
                continue
            try:
                jsonschema.validate(tag, tag_schema)
            except jsonschema.ValidationError as exc:  # type: ignore
                errors.append(f"{file_path}: tags[{i}] schema violation - {exc.message}")
                continue
            tag_id = tag.get("tag_id")
            if not isinstance(tag_id, str):
                errors.append(f"{file_path}: tags[{i}] missing tag_id")
                continue
            canon = canonical(tag)
            prev = tag_index.get(tag_id)
            if prev is None:
                tag_index[tag_id] = canon
                tag_source[tag_id] = file_path
            else:
                if prev != canon:
                    prev_digest = hashlib.sha256(prev.encode("utf-8")).hexdigest()[:12]
                    new_digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]
                    errors.append(
                        f"conflict tag_id '{tag_id}' between {tag_source[tag_id].name} and {file_path.name} (sha256 {prev_digest} != {new_digest})"
                    )
        # Validate affordances
        for i, afford in enumerate(affords):
            total_items += 1
            if not isinstance(afford, dict):
                errors.append(f"{file_path}: affordances[{i}] must be an object")
                continue
            try:
                jsonschema.validate(afford, afford_schema)
            except jsonschema.ValidationError as exc:  # type: ignore
                errors.append(f"{file_path}: affordances[{i}] schema violation - {exc.message}")
                continue
            afford_id = afford.get("affordance_id")
            if not isinstance(afford_id, str):
                errors.append(f"{file_path}: affordances[{i}] missing affordance_id")
                continue
            canon = canonical(afford)
            prev = afford_index.get(afford_id)
            if prev is None:
                afford_index[afford_id] = canon
                afford_source[afford_id] = file_path
            else:
                if prev != canon:
                    prev_digest = hashlib.sha256(prev.encode("utf-8")).hexdigest()[:12]
                    new_digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]
                    errors.append(
                        f"conflict affordance_id '{afford_id}' between {afford_source[afford_id].name} and {file_path.name} (sha256 {prev_digest} != {new_digest})"
                    )
        elapsed = (time.perf_counter() - start) * 1000
        timings.append(elapsed)

    if timings:
        timings_sorted = sorted(timings)
        p95_index = int(len(timings_sorted) * 0.95) - 1
        p95_ms = timings_sorted[max(p95_index, 0)]
        avg_ms = sum(timings_sorted) / len(timings_sorted)
        print(
            f"ontology.validate summary: files={len(collection_files)} items={total_items} avg_ms={avg_ms:.2f} p95_ms={p95_ms:.2f}"
        )
    return errors


def validate_manifest_fixtures() -> list[str]:
    """Validate manifest fixtures against the manifest schema."""
    errors: list[str] = []
    
    try:
        import jsonschema
    except ImportError:
        # Skip manifest fixture validation if jsonschema is not available
        print("Note: Skipping manifest fixture validation (jsonschema not available)")
        return errors
    
    schema_path = Path("contracts/package/manifest.v1.json")
    if not schema_path.exists():
        return [f"manifest schema not found at {schema_path}"]
    
    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return [f"failed to load manifest schema: {exc}"]
    
    fixtures_dir = Path("tests/fixtures/import/manifest")
    if not fixtures_dir.exists():
        return [f"manifest fixtures directory not found at {fixtures_dir}"]
    
    # Validate happy-path fixture
    happy_path = fixtures_dir / "happy-path" / "package.manifest.json"
    if happy_path.exists():
        try:
            with open(happy_path, encoding="utf-8") as f:
                manifest = json.load(f)
            jsonschema.validate(manifest, schema)
            print(f"✓ {happy_path} validates against schema")
        except json.JSONDecodeError as exc:
            errors.append(f"{happy_path}: invalid JSON - {exc}")
        except jsonschema.ValidationError as exc:
            errors.append(f"{happy_path}: schema validation failed - {exc.message}")
        except OSError as exc:
            errors.append(f"{happy_path}: failed to read - {exc}")
    
    # Validate tampered fixture (should also pass schema but fail hash check later)  
    tampered_path = fixtures_dir / "tampered" / "package.manifest.json"
    if tampered_path.exists():
        try:
            with open(tampered_path, encoding="utf-8") as f:
                manifest = json.load(f)
            jsonschema.validate(manifest, schema)
            print(f"✓ {tampered_path} validates against schema")
        except json.JSONDecodeError as exc:
            errors.append(f"{tampered_path}: invalid JSON - {exc}")
        except jsonschema.ValidationError as exc:
            errors.append(f"{tampered_path}: schema validation failed - {exc.message}")
        except OSError as exc:
            errors.append(f"{tampered_path}: failed to read - {exc}")
    
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate prompt and contract artifacts")
    parser.add_argument(
        "--only-contracts",
        action="store_true",
        help="Validate only contracts (includes ontology & manifest) and skip prompt validation",
    )
    parser.add_argument(
        "--only-ontology",
        action="store_true",
        help="Validate only ontology collections (skips prompts, other contracts & manifest fixtures)",
    )
    parser.add_argument(
        "--skip-manifest-fixtures",
        action="store_true",
        help="Skip manifest fixture validation (useful during fixture edits)",
    )
    args = parser.parse_args()

    errors: list[str] = []
    if args.only_ontology:
        errors.extend(validate_ontology(only_contracts=True))
    else:
        if not args.only_contracts:
            errors.extend(validate_prompts())
        # contracts (optionally skipping manifest fixtures)
        errors.extend(validate_contracts(skip_manifest=args.skip_manifest_fixtures))
        # Always include ontology when running full or only-contracts validation
        errors.extend(validate_ontology())

    if errors:
        print("Artifact validation failed:", file=sys.stderr)
        for err in errors:
            print(f" - {err}", file=sys.stderr)
        return 1

    print("Prompt and contract artifacts passed validation checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
