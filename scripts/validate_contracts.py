#!/usr/bin/env python3
"""Validate contract registries for naming and metadata conventions.

This script validates artifacts under `contracts/` and specific test fixtures for schema correctness.
It intentionally does NOT validate prompt files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Legacy artifacts that are intentionally ignored (temporary allowlist)
IGNORED_RELATIVE_PATHS: set[str] = set()

CONTRACT_EXTS = {".json", ".yaml", ".yml"}
VERSION_RE = re.compile(r"v(\d+)(?:[._](\d+))?", re.IGNORECASE)


def iter_artifacts(root: Path, exts: set[str]):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "README.md":
            continue
        if path.suffix.lower() in exts:
            yield path


def validate_contracts() -> list[str]:
    errors: list[str] = []
    contracts_dir = Path("contracts")
    if not contracts_dir.exists():
        return ["contracts directory is missing"]

    artifacts = list(iter_artifacts(contracts_dir, CONTRACT_EXTS))
    if not artifacts:
        print("No contract artifacts found; skipping schema enforcement.")
        return errors

    for path in artifacts:
        rel_path = path.as_posix()
        if rel_path in IGNORED_RELATIVE_PATHS:
            continue
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
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{path}: invalid JSON - {exc}")

    errors.extend(validate_manifest_fixtures())
    return errors


def validate_manifest_fixtures() -> list[str]:
    """Validate manifest fixtures against the manifest schema."""
    errors: list[str] = []

    try:
        import jsonschema
    except ImportError:
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

    for sub in ("happy-path", "tampered"):
        path = fixtures_dir / sub / "package.manifest.json"
        if not path.exists():
            errors.append(f"manifest fixture missing: {path}")
            continue
        try:
            with open(path, encoding="utf-8") as f:
                manifest = json.load(f)
            jsonschema.validate(manifest, schema)
            print(f"\u2713 {path} validates against schema")
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON - {exc}")
        except jsonschema.ValidationError as exc:
            errors.append(f"{path}: schema validation failed - {exc.message}")
        except OSError as exc:
            errors.append(f"{path}: failed to read - {exc}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate contract artifacts")
    parser.parse_args()

    errors = validate_contracts()
    if errors:
        print("Artifact validation failed:", file=sys.stderr)
        for err in errors:
            print(f" - {err}", file=sys.stderr)
        return 1
    print("Contract artifacts passed validation checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
