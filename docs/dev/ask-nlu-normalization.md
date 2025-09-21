# Rule-based Ask NLU: Normalization Rules (Seed)

This document describes the initial deterministic rules used to parse `/ask` messages into an IntentFrame and AffordanceTags.

- Tokenization: ASCII alpha tokens via regex `[A-Za-z]+`, lower-cased.
- Stopwords: small closed set in code (`ask_nlu._STOPWORDS`).
- Actions: matched by ontology synonyms -> normalized action key (e.g., hit/strike -> attack).
- Targets: matched by ontology synonyms -> tag `target.<type>` with value namespace `npc:<id>` or `obj:<id>`.
- Modifiers: matched from a small list of adverbs (e.g., quickly, silently).
- Unknown tokens: surfaced as `unknown:<token>` tags.

Locations:
- Ontology seed: `contracts/ontology/seed.json`
- Tests/fixtures: `tests/fixtures/ask/`

Dev logging:
- Enable `[features.ask].nlu_debug = true` in `config.toml` to emit structured debug logs (no new metrics).

Limitations:
- No pronoun/alias resolution.
- No multi-word expressions.
- No external NLP or network calls.
