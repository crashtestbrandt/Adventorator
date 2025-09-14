# Encounters & Turn Engine (Phase 10)

This phase introduces two new tables and a minimal deterministic turn engine behind a feature flag.

## Schema

- encounters
  - id (pk)
  - scene_id (fk scenes.id)
  - status enum: setup | active | ended
  - round int (default 1)
  - active_idx int (default 0)
  - created_at, updated_at (tz)

- combatants
  - id (pk)
  - encounter_id (fk encounters.id)
  - character_id (nullable fk characters.id)
  - name text
  - initiative int nullable (None during setup)
  - hp int (default 0)
  - conditions JSON (default {})
  - token_id (optional)
  - order_idx int (stable insertion order; tiebreak for initiative)

Indexes:
- encounters: (scene_id), (status)
- combatants: (encounter_id), (encounter_id, initiative, order_idx), (name)

## Feature flags

- features.combat: enables tools and apply mutations in the executor.
- features.events: appends predicted or generic events during apply.

## Manual smoke checklist

1) Start encounter
- Build a ToolCallChain with tool: start_encounter, args: {scene_id}.
- Preview: "Start encounter (scene_id=...)".
- Apply (with features.combat=true): mechanics reports encounter started; predicted event: encounter.started.

2) Add combatants (setup only)
- add_combatant (encounter_id, name, hp?, character_id?, token_id?)
- Check DB: combatants added, order_idx increments.
- Preview shows add; apply emits combatant.added.

3) Set initiative
- set_initiative (encounter_id, combatant_id, initiative)
- After all have initiative, encounter becomes active with active_idx=0 and encounter.advanced predicted event.

4) Next turn
- next_turn (encounter_id)
- active_idx increments; on wrap, round++.
- Mechanics: "Round r, Active: <name> (id=...)"; predicted event: encounter.advanced.

5) End encounter
- end_encounter (encounter_id)
- status -> ended; predicted event: encounter.ended.

6) Concurrency (optional)
- Fire two next_turn apply calls concurrently; only one transition should win (advisory + asyncio locks). Metrics include locks.acquire.* and histo.locks.wait_ms.*.

## Metrics

- executor.preview.tool.<name>
- executor.apply.tool.<name>
- executor.preview.duration_ms (counter) + histo.executor.preview.ms.*
- executor.apply.duration_ms (counter) + histo.executor.apply.ms.*
- locks.acquire.success|timeout|error|mode
- histo.locks.wait_ms.*

## Notes

- SQLite: advisory locks are skipped; only in-process lock is used.
- Postgres: advisory lock uses class=1001 and key=encounter_id with bounded polling.
