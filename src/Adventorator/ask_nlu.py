"""Rule-based NLU and affordance tagging scaffold (deterministic, offline).

Implements:
- Tokenization and stopword filtering
- Ontology-backed action and target matching with simple synonym maps
- Modifier capture
- Unknown token surfacing via unknown:* tags

No external libraries and no network calls by design.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import structlog

from Adventorator.schemas import AffordanceTag, IntentFrame

_STOPWORDS: set[str] = {
    "i",
    "we",
    "you",
    "he",
    "she",
    "they",
    "it",
    "me",
    "him",
    "them",
    "the",
    "a",
    "an",
    "to",
    "with",
    "and",
    "then",
    "please",
    "at",
    "on",
    "in",
    "into",
    "of",
    "from",
    "that",
    "this",
    "those",
    "these",
    "my",
    "your",
    "our",
    "their",
    "his",
    "her",
    "its",
}


@dataclass(frozen=True)
class _Ontology:
    actions: dict[str, list[str]]
    targets: dict[str, dict]
    modifiers: list[str]

    @staticmethod
    def load() -> _Ontology:
        """Load the seed ontology from contracts/ontology/seed.json.

        The file is intentionally small and offline. If not present, a minimal
        built-in fallback is used so tests remain deterministic.
        """
        path = Path("contracts/ontology/seed.json")
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {
                "actions": {
                    "attack": ["attack", "hit", "strike", "swing"],
                    "move": ["move", "go", "walk", "run"],
                    "cast": ["cast", "spell", "castspell"],
                },
                "targets": {
                    "goblin": {"type": "npc", "synonyms": ["goblin", "gobo"]},
                    "guard": {"type": "npc", "synonyms": ["guard", "watchman"]},
                    "door": {"type": "object", "synonyms": ["door", "gate"]},
                },
                "modifiers": ["carefully", "quickly", "silently", "stealthily"],
            }
        actions = {k: [s.lower() for s in v] for k, v in (data.get("actions") or {}).items()}
        targets = {
            k: {
                "type": (v or {}).get("type", "entity"),
                "synonyms": [s.lower() for s in (v or {}).get("synonyms", [k])],
            }
            for k, v in (data.get("targets") or {}).items()
        }
        modifiers = [m.lower() for m in (data.get("modifiers") or [])]
        return _Ontology(actions=actions, targets=targets, modifiers=modifiers)


_ONTOLOGY = _Ontology.load()
_log = structlog.get_logger()


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z]+", text)]


def _first_non_stop(tokens: Iterable[str]) -> str | None:
    for t in tokens:
        if t not in _STOPWORDS:
            return t
    return None


def _match_action(tokens: list[str]) -> str:
    # Prefer ontology synonyms → normalized action key
    for t in tokens:
        if t in _STOPWORDS:
            continue
        for action, syns in _ONTOLOGY.actions.items():
            if t in syns:
                return action
    # Fallback to first non-stopword token or a safe default
    return _first_non_stop(tokens) or "say"


def _match_actions(tokens: list[str]) -> list[str]:
    """Return all normalized actions found in token order (unique, stable)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for t in tokens:
        if t in _STOPWORDS:
            continue
        for action, syns in _ONTOLOGY.actions.items():
            if t in syns and action not in seen:
                seen.add(action)
                ordered.append(action)
    return ordered


def _match_target(tokens: list[str]) -> tuple[str | None, AffordanceTag | None]:
    for t in tokens:
        if t in _STOPWORDS:
            continue
        for norm, meta in _ONTOLOGY.targets.items():
            if t in meta.get("synonyms", [norm]):
                t_type = str(meta.get("type", "entity"))
                if t_type == "npc":
                    key = "target.npc"
                    value = f"npc:{norm}"
                elif t_type == "object":
                    key = "target.object"
                    value = f"obj:{norm}"
                else:
                    key = "target.entity"
                    value = f"ent:{norm}"
                return norm, AffordanceTag(key=key, value=value, confidence=1.0)
    return None, None


def _collect_modifiers(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t in _ONTOLOGY.modifiers]


def parse_and_tag(text: str, debug: bool = False) -> tuple[IntentFrame, list[AffordanceTag]]:
    """Parse user text into an IntentFrame and AffordanceTags.

    Deterministic and offline: relies only on local ontology and simple rules.
    """
    toks = _tokens(text)
    actions = _match_actions(toks)
    action = actions[0] if actions else _match_action(toks)
    target_ref, target_tag = _match_target(toks)
    modifiers = _collect_modifiers(toks)

    # Tag all recognized actions; first is the primary in the IntentFrame
    action_set = actions or [action]
    tags: list[AffordanceTag] = [
        AffordanceTag(key=f"action.{a}") for a in dict.fromkeys(action_set)
    ]
    if target_tag:
        tags.append(target_tag)

    # Surface unknown tokens that aren't action/target/modifier/stopwords
    known: set[str] = set(_STOPWORDS)
    # Consider synonyms for all recognized actions as known (not unknown tokens)
    for a in dict.fromkeys(action_set):
        known.update(_ONTOLOGY.actions.get(a, []))
    for meta in _ONTOLOGY.targets.values():
        known.update(meta.get("synonyms", []))
    known.update(_ONTOLOGY.modifiers)

    for t in toks:
        if t not in known:
            tags.append(AffordanceTag(key=f"unknown.{t}"))

    intent = IntentFrame(action=action, actor_ref=None, target_ref=target_ref, modifiers=modifiers)
    if debug:
        _log.debug(
            "ask_nlu.debug",
            tokens=toks,
            action=action,
            target_ref=target_ref,
            modifiers=modifiers,
            tags=[t.model_dump() for t in tags],
        )
    return intent, tags
