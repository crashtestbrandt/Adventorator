"""Knowledge Base (KB) integration module for entity resolution.

This package exposes adapter helpers while keeping import surfaces minimal.
"""

# ruff: noqa: N999  # Package name uses project-specific casing 'Adventorator'

from .adapter import (
	Candidate,
	KBAdapter,
	KBResolution,
	bulk_resolve,
	get_kb_adapter,
	resolve_entity,
)

__all__ = [
	"KBAdapter",
	"KBResolution",
	"Candidate",
	"get_kb_adapter",
	"resolve_entity",
	"bulk_resolve",
]