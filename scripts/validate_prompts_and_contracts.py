#!/usr/bin/env python3
"""Validate prompt and contract registries for naming and metadata conventions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

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
    
    # Validate manifest fixtures against schema
    errors.extend(validate_manifest_fixtures())
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
        help="Validate only contracts and skip prompt validation",
    )
    args = parser.parse_args()

    errors: list[str] = []
    if not args.only_contracts:
        errors.extend(validate_prompts())
    errors.extend(validate_contracts())

    if errors:
        print("Artifact validation failed:", file=sys.stderr)
        for err in errors:
            print(f" - {err}", file=sys.stderr)
        return 1

    print("Prompt and contract artifacts passed validation checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
