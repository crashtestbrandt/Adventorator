# NLP Plan — Incremental and Defensive

Purpose: Introduce a deterministic, defensive NLP layer to translate freeform player text into validated Adventorator commands and arguments. The NLP system favors rules and schemas first, uses spaCy as a helper (not a source of truth), and integrates safely with the existing planner and command registry.

Guiding principles
- Deterministic-first: Prefer rules/regex/parsers; use spaCy for tokenization/NER as hints.
- Strict contracts: Pydantic models for parse results; validate against command schemas.
- Defense in depth: Input bounds, timeouts, allowlists, safe defaults, and rollbacks.
- Small steps: Phase-by-phase rollout; tests and metrics for each increment.
- Fast path: Keep request handlers fast; cache and defer where needed.
- Privacy & safety: No sensitive data logging; redact and cap payloads.

Key integrations
- Commands and registry: commanding.py, command_loader.py, all_commands().
- Planner and /act: planner output validation; NLP can assist or bypass with confidence gating.
- Orchestrator: allowed_actors, safety gates; no state mutation from NLP itself.
- Rules engine: Pure deterministic checks via rules/dice.py and rules/checks.py.
- Persistence: Use repos.py under async with session_scope() if NLP needs DB lookups (e.g., entity linking).
- Settings & flags: config.load_settings(), config.toml feature flags (e.g., [features].nlp=true).
- Metrics: metrics.py minimal counters; reset_counters() for tests.

Proposed schemas (Pydantic v2)
- Utterance(text: str, lang: Literal['en'], ts: datetime)
- TokenSpan(start: int, end: int, text: str, label: str)
- Intent(enum): roll, check, sheet_create, sheet_show, do, ooc, unknown
- ExtractedArgs: {dice_expr?: str, ability?: str, dc?: int, name?: str, json?: dict, reason?: str}
- ParseResult(intent: Intent, args: ExtractedArgs, entities: list[TokenSpan], conf: float, rationale?: str)
- ValidationResult(ok: bool, command?: str, options?: dict, errors?: list[str])

Phases

Phase N0 — Baseline & Deterministic Scaffold — status: planned
Goal: Establish a deterministic NLP scaffolding with tight bounds and observability.
Deliverables
- Pin spaCy (e.g., 3.x) and en_core_web_sm with exact versions; freeze requirements.
- Create nlp/ module (docs-only now) with adapters planned for:
  - tokenizer, regex matchers, lightweight entity patterns (list-based, whitelist).
  - deterministic extractors for dice expressions and numbers.
- Define Pydantic models above (nlp_schemas.py).
- Feature flag: [features].nlp=true (default false).
- Metrics counters: nlp.parse.requested, nlp.parse.succeeded, nlp.parse.failed, nlp.intent.unknown.
- Input bounds: max 1,000 chars; ASCII-safe normalization; strip control chars; reject binary.
Exit criteria
- Unit tests validate bounds, schema validation, and basic tokenization path.
- Metrics emitted on success/failure; feature flag disables all NLP behavior cleanly.
Rollback
- Flip [features].nlp=false → planner and commands work as today; NLP skipped.

Phase N1 — Dice Expression Extractor — status: planned
Goal: Robust, deterministic extraction of common dice expressions and modifiers.
Deliverables
- Regex + finite-state parsing for:
  - Patterns like XdY(+/-Z)? with optional labels (e.g., “for damage”).
  - Advantage/disadvantage cues: “with advantage”, “adv”, “disadvantage”.
  - Multi-expr handling; choose the most salient by heuristics (first or highest die).
- Return ExtractedArgs.dice_expr, advantage/disadvantage flags (only for single d20).
- Align with rules/dice.py (no implicit changes to semantics).
- Tests: property/fixture tests for a suite of utterances.
Exit criteria
- ≥95% correct extraction on a curated test set; zero nondeterminism.
Rollback
- If parsing fails, intent can fall back to unknown; planner (/act) remains unaffected.

Phase N2 — Intent Classification (Rules-First) — status: planned
Goal: Determine intent via deterministic cues and constrained patterns.
Deliverables
- Rule-based intent inference aligned to allowlist: roll, check, sheet.create, sheet.show, do, ooc.
- Synonym tables for verbs and nouns; locale = en only.
- Confidence score (0..1) computed from matched features; threshold configurable.
- Unknown remains the safe default.
- Tests for overlapping patterns and negations (“don’t roll”, “no check”).
Exit criteria
- Intent accuracy ≥90% on labeled set; unknown for ambiguous cases.
Rollback
- Low confidence (<τ) → return unknown; defer to planner if enabled.

Phase N3 — Argument Extraction per Intent — status: planned
Goal: Extract structured arguments consistent with command option models.
Deliverables
- roll: dice_expr (from N1), optional reason text.
- check: ability in {STR, DEX, CON, INT, WIS, CHA}, optional dc:int, adv/dis flags.
- sheet.show: name or selection hints.
- sheet.create: capture following JSON block (≤16KB), with early size bounds and safe parse.
- do/ooc: content message (≤2,000 chars after normalization).
- Strict validation via command option models (existing Pydantic in commanding.py).
- Tests for boundary inputs, malformed JSON, DC bounds.
Exit criteria
- High-fidelity argument extraction with round-trip validation against option models.
Rollback
- On validation error, produce ValidationResult with errors; caller returns ephemeral error.

Phase N4 — Entity Recognition & Linking — status: planned
Goal: Identify character names and link to known entities per scene/campaign.
Deliverables
- spaCy NER hints + deterministic gazetteer built from repos.list_character_names within session.
- Allowed_actors gating: reject unknown actors; unknown → leave unlinked but do not invent.
- Simple nickname mapping table (case-insensitive).
- Tests covering collisions and partial matches.
Exit criteria
- ≥95% precision on linking to known characters in test data; zero invented entities.
Rollback
- If repos fails or feature disabled, skip linking; intents that require linkage become unknown.

Phase N5 — Coreference & Reference Resolution (Minimal) — status: planned
Goal: Resolve “I”, “she”, “the rogue” to known participants where safe.
Deliverables
- Deterministic pronoun resolution rules within the current scene context (participants).
- Role descriptors mapping: “rogue”, “wizard” from character sheet class_name; cautious, opt-in.
- Confidence gating; fall back to leaving unresolved if uncertain.
- Tests with adversarial examples to avoid cross-player leakage.
Exit criteria
- Resolution precision ≥90% on a labeled set; low recall is acceptable.
Rollback
- Low confidence → leave unresolved; downstream uses allowed_actors as hard filter.

Phase N6 — Planner Interop & Decision Strategy — status: planned
Goal: Compose NLP with the existing planner to improve accuracy without regressions.
Deliverables
- Decision policy:
  - High-confidence intent+args → construct a validated command and dispatch.
  - Medium/low confidence → pass utterance + NLP hints to planner; validate as usual.
  - Planner disabled → return unknown with ephemeral guidance.
- 30s in-process cache keyed by (scene_id, normalized_text) to suppress duplicate parsing (reuse existing cache pattern).
- Metrics: nlp.decision.direct, nlp.decision.planner, nlp.decision.unknown.
- Soft timeout: 50–100ms budget for NLP; if exceeded, defer to planner.
Exit criteria
- Reduced planner invocations for common cases (roll/check) without accuracy drop.
Rollback
- Feature flag guards to disable direct-dispatch and force planner path.

Phase N7 — Safety, Bounds, and Redaction — status: planned
Goal: Hardening against malformed input and sensitive content.
Deliverables
- Input caps (length, JSON size), token normalization, control-char stripping.
- Redact tokens that look like secrets (common key formats) from logs/metrics.
- Narration/content filters for /do via existing policies (lines/veils in future phases).
- Metrics: nlp.safety.redacted, nlp.safety.rejected.
Exit criteria
- Unit tests for redaction; no sensitive content appears in logs.
Rollback
- Reject over-bounds inputs with ephemeral errors; no crashes.

Phase N8 — Evaluation Suite & Golden Fixtures — status: planned
Goal: Create reproducible evaluation and regression tests.
Deliverables
- Curated dataset: 200–500 utterances across intents; YAML/JSON fixtures.
- Golden outputs for ParseResult and ValidationResult; property tests for dice.
- CI gate: diff in evaluation metrics requires explicit approval.
Exit criteria
- Stable, reproducible results; failures are actionable.
Rollback
- Disable NLP gate in CI temporarily (flag) if blocking, while investigating.

Phase N9 — Rollout & Observability — status: planned
Goal: Safe production rollout with telemetry.
Deliverables
- Canary enablement in a dev guild; structured logging for parse decisions.
- Dashboards: request rates, unknown rates, fallback rates, latency, errors.
- Playbook for rollback (feature flag) and sampling logs for triage.
Exit criteria
- Error rate under threshold; no user-facing regressions; p50 NLP latency <20ms.
Rollback
- Flip [features].nlp=false; planner-only mode remains.

Defensive programming checklist
- Validate all inputs with strict Pydantic models; reject on bounds.
- Never invent entities; only link against repos-provided lists within session scope.
- Confidence thresholds default conservative; unknown is safe.
- Use allowlists for commands and options; validate via command registry shapes.
- Gate everything behind feature flags; keep defaults off until ready.
- Timeouts and early returns; never block the DEFERRED flow.
- Cache cautiously; 30s in-process only; include scene_id in key.
- Testing first; metrics for every decision path.

Testing plan
- Unit: regex parsers, schema validation, confidence scoring, bounds.
- Integration: planner interop, command dispatch via /act; monkeypatch repositories and caches.
- End-to-end: golden transcript fixtures; assert deferred ack and follow-up behavior.
- Property tests: dice and number extraction stability.
- Metrics: assert counters via metrics.reset_counters() and metrics.get_counter().

Security and privacy
- No PII or secrets in logs; redact suspected keys.
- No state mutation by NLP; only structured suggestions validated by existing command models.
- Prefer local models (spaCy) with pinned versions; no network calls in NLP path.
- Adhere to visibility flags (features.llm_visible) when surfacing outputs.

Future enhancements
- Multilingual support (phase-gated), richer entity types (items, locations), and domain lexicons.
- Disambiguation dialogs for low-confidence parses (ephemeral prompts).
- Per-guild defaults and custom synonyms.

Notes
- Keep diffs small; follow project conventions for async sessions and test patching.
- Do not commit secrets; mirror new settings to .env.example as needed.
