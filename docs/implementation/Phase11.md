# Phase 11: Low-Level Implementation Plan

## Objectives

- Add a single, safe “attack” path end-to-end: propose → preview → confirm → apply → events/folds.
- Keep scope tight: no positioning, AoE, resistances, or complex conditions beyond a simple “apply/remove/clear”.
- Everything gated by feature flags, deterministic in tests, and idempotent on re-apply.

## Status (snapshot)

- [x] Phase 11.1 — Foundations: Implemented end-to-end (attack tool preview/apply, crits, adv/dis, predicted events). Tests green.
- [x] Phase 11.2 — Orchestrator integration: Implemented (LLM attack proposals, ToolCallChain with confirm, idempotent re-apply). Tests green.
- [x] Phase 11.3 — Conditions (simple): Implemented (apply/remove/clear wired into orchestrator; preview/confirm flow; unit + integration tests added).
- [x] Phase 11.4 — Observability and docs: Metrics validated; README combat section added; preview fallback messaging distinguishes executor disabled vs preview error.

## Phasing and acceptance criteria

Phase 11.1 — Foundations
- Add an executor tool “attack” that computes to‑hit vs AC, handles crit (natural 20), and rolls damage on hit.
- Predicted events from the tool: on hit → apply_damage; on miss → attack.missed.
- Preview shows mechanics (d20 rolls, attack bonus, AC, total, hit/miss, crit), plus damage breakdown on hit.
- Apply appends predicted events when `features_events=true`.
- Tests: unit for tool mechanics (including adv/dis), and basic apply appending events.

Phase 11.2 — Orchestrator integration
- Permit LLM proposals with action=attack; validate tight bounds on all fields.
- Orchestrator returns a ToolCallChain with one step: attack (requires_confirmation=true).
- End-to-end preview → confirm → apply; re-apply is a no-op (pending dedup key persists).
- Tests: integration for `/do "I attack X"` with mocked LLM output; idempotent re-apply.

Phase 11.3 — Conditions (simple)
- Reuse existing tools: apply_condition, remove_condition, clear_condition (already in executor).
- Add a minimal `/do` scenario where LLM proposes condition application (optional for Phase 11 if time permits).
- Tests: unit for condition folds; integration for condition apply/clear via executor chain.

Phase 11.4 — Observability and docs
- Ensure per-tool counters increment for attack in preview/apply.
- Confirm events.append.ok/error metrics increments on apply.
- Update README and implementation plan notes; add FF guidance and helpful error stubs when disabled.

## Design contracts

Attack tool (executor)
- Input args
  - attacker: string (display ref or id/name)
  - target: string (same)
  - attack_bonus: int (bounded: -5..+15)
  - target_ac: int (bounded: 5..30)
  - damage: { dice: string (XdY[+Z]), mod: int (-5..+10), type?: string }  — mod optional; support crit doubling roll
  - advantage?: bool (default false)
  - disadvantage?: bool (default false) — mutually exclusive; if both set, treat as neutral
  - seed?: int (deterministic tests)
- Output preview mechanics
  - “Attack +X vs AC Y” line
  - d20 roll(s) with pick and total
  - “HIT/CRIT/MISS”
  - If hit/crit: damage expression, raw rolls, total damage
- Predicted events
  - On hit: { type: "apply_damage", payload: { target, amount, source: attacker, crit?: bool, damage_type?: str } }
  - On miss: { type: "attack.missed", payload: { attacker, target } }
- Apply behavior
  - If `features_combat` false → return helpful mechanics stub; no events
  - If `features_events` true → append predicted events (or generic mechanics fallback)
  - No direct HP mutations; folds compute derived views
- Metrics
  - executor.preview.tool.attack, executor.apply.tool.attack
  - events.append.ok/error (existing)
- Error modes
  - Invalid schema: preview returns “Unknown tool/Invalid args” mechanics line, no events
  - Advantage/disadvantage both: neutral path
  - Damage dice parse error: treat as 0 damage with clear mechanics note (defensive)

Orchestrator changes
- Extend LLM output schema to allow action ∈ {attack, apply_condition, remove_condition, clear_condition} with minimal bounded fields (no hidden free-form mutation).
- Validation
  - action ∈ {ability_check, attack, apply_condition, remove_condition, clear_condition}
  - attack_bonus ∈ [-5, 15], target_ac ∈ [5, 30], damage.mod ∈ [-5, 10], dice length ≤ 16 and pattern checked
  - advantage XOR disadvantage (or neutral)
  - for conditions: require target + condition; optional duration small integer (defensive clamp)
  - Reject unsafe narration text still (banned verbs remain; only structured tool authorizes mutation)
- Preview path (executor.dry_run): builds chain with a single attack step, requires_confirmation=true, visibility ephemeral by default.
- Apply path: flows through existing `/confirm`, appends events if `features_events=true`.
- Feature flags
  - If `features_combat=false`, produce helpful error (no chain).

## Defensive bounds and guardrails

- Feature gates:
  - `[combat].enabled` or `[features].combat`: guard the attack tool registration and orchestrator acceptance.
  - `features_executor` and `features_executor_confirm`: ensure preview/confirm gating (still required for attack).
  - `features_events`: control event ledger writes, not preview.
- Input validation:
  - Regex-check damage dice; cap at sensible limits: X ≤ 10, Y ∈ {4,6,8,10,12}, mod ∈ [-5..+10].
  - AC 5–30; attack bonus -5–+15; refuse absurd values.
- Determinism:
  - Accept seed input for deterministic tests; preserve dice roll details in mechanics.
- Idempotency:
  - PendingAction dedup hash uses normalized chain JSON; re-apply => no duplicate pending; apply is append-only but safe to call again from the same pending flow (confirm path enforces state).
- Safety:
  - Orchestrator continues banning free-text “deal/apply damage” unless paired with a validated attack action.

## Implementation steps

1) Executor: register attack tool
- Add to executor.py
  - ToolSpec("attack", schema=…) with a handler that:
    - Reads and bounds args; resolves advantage flags
    - Uses `Dnd5eRuleset` to roll d20 with adv/dis, computes total = d20 + attack_bonus
    - Hit if total ≥ target_ac; crit if natural 20; miss if < AC; fumble = natural 1 → miss (no special penalty; optional text)
    - Damage: roll damage dice; on crit, roll dice again (don’t double modifiers) per current ruleset
    - Build mechanics string and predicted events (apply_damage on hit)
  - Per-tool counters increment automatically via executor

2) Orchestrator: accept attack proposals
- Extend validation function to allow action=attack with tight bounds
- When attack: produce `ToolCallChain` with attack step, requires_confirmation=true; executor preview for mechanics; concise narration from LLM
- If combat disabled: reject with helpful mechanics/narration stub

3) LLM schema and prompts
- Update the output model (where LLM JSON is parsed) to include:
  - action: "attack"
  - attacker, target, attack_bonus, target_ac, damage: { dice, mod, type? }, advantage?, disadvantage?
- Prompt: a “mechanics-aware but minimal” example for both attack and ability_check; emphasize not to invent actors and to keep reasonable stats
- Maintain strict JSON-only parsing; continue to log rationale but not expose it

4) Tests
- Unit (rules/executor)
  - Adv/dis advantage pick behavior; crit on 20; miss on 1; proper crit damage (dice doubled, not mod)
  - Attack tool predicted events: shape and payload correctness
  - Invalid inputs bounded to errors or neutral mechanics, no events
- Integration
  - Mock LLM to propose an attack; `/do` → pending preview (requires_confirmation) → `/confirm` → events appended
  - Re-apply confirm on same pending returns no duplicate (idempotent)
  - FF gating: with `features_combat=false`, attack path returns stub
- Folds
  - Using `fold_hp_view`, verify resulting net HP change for the target after an applied hit event

5) Observability and docs
- Ensure counters observed in tests: executor.preview.ok, executor.apply.ok, per-tool, events.append.ok
- README/implementation notes: how to enable combat; brief example of the preview mechanics and confirm/apply

## Risks and deferrals

- Resistances/immunities/vulnerabilities: explicitly TODO; not in Phase 11.
- Conditions beyond simple stack/duration: defer complex timing (end-of-turn decrements) to a later phase.
- AC/attack bonus inference from sheets: start with explicit numbers in the proposal; add sheet inference later.
- Multiattack or reactions: out of scope.

## Rollout

- Default off: `[combat].enabled=false`
- Dev can flip `[combat].enabled=true`, `features_executor=true`, `features_executor_confirm=true`, `features_events=true` to exercise full flow
- Start with unit/integration tests; then manual smoke via CLI/web CLI:
  - `/do "I attack the goblin"` → preview
  - `/confirm <id>` → events written
- Rollback: set `features.combat=false`; non-combat paths unaffected.

---

## What’s next (concise)

- Post‑11: Consider planner defaults and sheet‑driven inference for attack bonuses/AC.
- Optional: Add folds-based assertions for condition stacks over time if needed.

## Quick try/verify

- Enable flags: `[combat].enabled=true`, `features_executor=true`, `features_executor_confirm=true`, `features_events=true`.
- Smoke via CLI or Discord:
  - `/do "I attack the goblin"` → expect mechanics starting with “Attack +X vs AC Y …” and a pending action to confirm.
  - `/confirm` → expect apply_damage or attack.missed event appended.
  - `/do "I knock the goblin prone"` → expect an apply_condition chain with a short mechanics preview; `/confirm` applies and emits a `condition.applied` event.
  - `/do "I remove poison from the goblin"` → expect a remove_condition chain; `/confirm` emits `condition.removed`.
- Tests to watch: `tests/test_executor_attack.py`, `tests/test_orchestrator_attack.py`, `tests/test_executor_conditions.py`, `tests/test_orchestrator_conditions.py`, `tests/test_do_confirm_attack.py`.

## Troubleshooting

- If preview reports “Combat tools unavailable” while combat is enabled, ensure damage.mod may be null; executor defaults it to 0. This was fixed by handling `None` for `damage.mod` in the attack handler.
- If preview reports “Condition tools unavailable,” set `features_executor=true` or check logs if a “preview error” message appears.
