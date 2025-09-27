"""Utilities for campaign package authoring and import prep.

Functions here avoid external deps and operate on paths/JSON.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

INGEST_DIRS = ("entities", "edges", "ontology", "ontologies", "lore")
INGEST_EXTS = {".json", ".md", ".txt"}


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _should_include(path: Path, package_root: Path) -> bool:
    if not path.is_file():
        return False
    if path.name == "package.manifest.json":
        return False
    try:
        rel = path.relative_to(package_root)
    except ValueError:
        return False
    if rel.parts and rel.parts[0] == ".git":
        return False
    if rel.parts and rel.parts[0] in ("__pycache__",):
        return False
    if rel.name.startswith("."):
        return False
    if rel.as_posix() == "README.md":
        return True
    # Only include files under known ingest dirs with allowed extensions
    if rel.parts and rel.parts[0] in INGEST_DIRS and path.suffix.lower() in INGEST_EXTS:
        return True
    return False


def enumerate_ingested_files(package_root: Path) -> list[Path]:
    package_root = package_root.resolve()
    paths: list[Path] = []
    # README at root is optional
    if (package_root / "README.md").exists():
        paths.append(package_root / "README.md")
    # Walk known dirs
    for d in INGEST_DIRS:
        p = package_root / d
        if not p.exists():
            continue
        for fp in p.rglob("*"):
            if _should_include(fp, package_root):
                paths.append(fp)
    return sorted(paths)


def rel_key(package_root: Path, file_path: Path) -> str:
    return file_path.resolve().relative_to(package_root.resolve()).as_posix()


def load_manifest(manifest_path: Path) -> dict:
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest_path: Path, manifest: dict) -> None:
    # Keep stable formatting for diff friendliness
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


@dataclass
class ContentIndexUpdate:
    added: dict[str, str]
    updated: dict[str, tuple[str, str]]  # key -> (old_hash, new_hash)
    removed: list[str]


def update_content_index(manifest_path: Path, package_root: Path) -> ContentIndexUpdate:
    manifest = load_manifest(manifest_path)
    content_index: dict[str, str] = dict(manifest.get("content_index", {}))

    files = enumerate_ingested_files(package_root)
    new_index: dict[str, str] = {}
    for fp in files:
        key = rel_key(package_root, fp)
        new_index[key] = compute_sha256(fp)

    added: dict[str, str] = {}
    updated: dict[str, tuple[str, str]] = {}
    removed: list[str] = []

    for key, new_hash in new_index.items():
        old_hash = content_index.get(key)
        if old_hash is None:
            added[key] = new_hash
        elif old_hash != new_hash:
            updated[key] = (old_hash, new_hash)

    for key in content_index.keys():
        if key not in new_index:
            removed.append(key)

    # Write back
    manifest["content_index"] = new_index
    save_manifest(manifest_path, manifest)

    return ContentIndexUpdate(added=added, updated=updated, removed=removed)
