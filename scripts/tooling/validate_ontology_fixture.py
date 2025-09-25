#!/usr/bin/env python3
"""Lightweight validator for ontology fixture directories used in readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_tags(tags: list[dict]) -> tuple[set[str], list[str]]:
    categories: set[str] = set()
    errors: list[str] = []
    seen_slugs: set[str] = set()

    for tag in tags:
        slug = tag.get("slug")
        category = tag.get("category")
        if not isinstance(slug, str) or not slug:
            errors.append("tag missing slug")
            continue
        if slug.lower() != slug:
            errors.append(f"tag slug not normalized lowercase: {slug}")
        if slug in seen_slugs:
            errors.append(f"duplicate tag slug: {slug}")
        else:
            seen_slugs.add(slug)
        if not isinstance(category, str) or not category:
            errors.append(f"tag {slug}: missing category")
        else:
            categories.add(category)
            if not slug.startswith(f"{category}."):
                errors.append(f"tag {slug}: slug/category mismatch")
        synonyms = tag.get("synonyms", [])
        for synonym in synonyms:
            if synonym.lower() != synonym:
                errors.append(f"tag {slug}: synonym not lowercase ({synonym})")
        provenance = tag.get("provenance", {})
        for key in ("source_package", "source_path", "content_sha256"):
            if key not in provenance:
                errors.append(f"tag {slug}: provenance missing {key}")
    return categories, errors


def validate_affordances(
    affordances: list[dict],
    tag_slugs: set[str],
) -> list[str]:
    errors: list[str] = []
    seen_slugs: set[str] = set()
    for affordance in affordances:
        slug = affordance.get("slug")
        if not isinstance(slug, str) or not slug:
            errors.append("affordance missing slug")
            continue
        if slug.lower() != slug:
            errors.append(f"affordance slug not normalized lowercase: {slug}")
        if slug in seen_slugs:
            errors.append(f"duplicate affordance slug: {slug}")
        else:
            seen_slugs.add(slug)
        for field in ("tags", "requires"):
            values = affordance.get(field, [])
            if not isinstance(values, list):
                errors.append(f"affordance {slug}: {field} must be a list")
                continue
            for value in values:
                if value not in tag_slugs:
                    errors.append(f"affordance {slug}: {field} reference missing tag {value}")
        provenance = affordance.get("provenance", {})
        for key in ("source_package", "source_path", "content_sha256"):
            if key not in provenance:
                errors.append(f"affordance {slug}: provenance missing {key}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixture_dir",
        type=Path,
        help="Path to ontology fixture directory (contains tags.json, optional affordances.json)",
    )
    args = parser.parse_args()

    fixture_dir: Path = args.fixture_dir
    if not fixture_dir.is_dir():
        parser.error(f"fixture directory not found: {fixture_dir}")

    tags_path = fixture_dir / "tags.json"
    if not tags_path.exists():
        parser.error(f"tags fixture missing at {tags_path}")

    tags_blob = load_json(tags_path)
    tags = tags_blob.get("tags")
    if not isinstance(tags, list):
        parser.error("tags.json: expected top-level 'tags' list")

    categories, tag_errors = validate_tags(tags)
    if tag_errors:
        for error in tag_errors:
            print(f"ERROR: {error}")
        return 1

    affordances_path = fixture_dir / "affordances.json"
    affordance_errors: list[str] = []
    affordance_count = 0
    if affordances_path.exists():
        affordances_blob = load_json(affordances_path)
        affordances = affordances_blob.get("affordances")
        if not isinstance(affordances, list):
            parser.error("affordances.json: expected top-level 'affordances' list")
        affordance_errors = validate_affordances(affordances, {t["slug"] for t in tags})
        affordance_count = len(affordances)

    if affordance_errors:
        for error in affordance_errors:
            print(f"ERROR: {error}")
        return 1

    normalization_message = (
        "Normalization \u2713 "
        f"categories={len(categories)} "
        f"tags={len(tags)} "
        f"affordances={affordance_count}"
    )
    print(normalization_message)
    print("Referential integrity \u2713")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
