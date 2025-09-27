# ARCH-SRD-001 — DnD 5e SRD Rules Engine

**Status:** Proposed

## Report
## Overview
Adventorator already wires a deterministic `Dnd5eRuleset` into every Discord invocation, exposing lightweight mechanics like dice rolling, ability checks, and simple combat previews through slash commands, the executor toolchain, and optional MCP adapters.






Bringing the full DnD 5e SRD into this environment means scaling those foundations into a governed, data-backed rules subsystem that covers every class, feature, spell, condition, and encounter rule while remaining deterministic and auditable.

## Current Baseline
- The existing rules package implements dice parsing, ability modifiers, basic checks, attack rolls, damage, initiative, and HP adjustments; the unit tests confirm only those limited behaviors today.





- Feature flags already gate mechanics, events, combat, and importer flows, giving safe rollout levers for a larger ruleset.


- The roadmap acknowledges “5E SRD Implementation” as a future intent, so delivering it will require new epic/story scaffolding before code work begins.


- Deterministic event ingestion, activity logging, and importer infrastructure are in place and explicitly tied to the campaign data architecture; they will be essential for storing SRD-derived assets and emitting auditable mechanics events.




## Strategy for Full SRD Coverage

### 1. Governance, Scope, and Source of Truth
1. Open a dedicated “EPIC-SRD-5E” under `docs/implementation/epics/` with DoR/DoD checklists that enumerate every SRD chapter (races, classes, equipment, spells, optional rules, monsters). Link it to the existing roadmap entry and ADRs governing the event substrate to maintain traceability.



2. Acquire the SRD 5.2.1 PDF provided by Wizards of the Coast, design a structured schema for each chapter (JSON/CSV/YAML), and codify provenance so that importer runs can re-derive the dataset deterministically. Treat the PDF as the authoritative upstream and document transformation steps inside the epic.

### 2. Canonical SRD Data Ingestion
1. Extend the campaign importer to support SRD payloads: add manifest types for “rulebook chapters” and “stat blocks,” reuse the deterministic hashing/idempotency helpers, and emit seed events describing each ingested rule element.


2. Store SRD entities in dedicated tables or JSONB documents (e.g., `srd_classes`, `srd_spells`, `srd_monsters`) keyed by ULID/slug so the rules engine can query them without hitting the PDF. Use the existing importer locks and event append logic to guarantee replayable ordering.


3. Create build tooling that converts the PDF into machine-readable files checked into the repo (or fetched at build time) with checksum verification to detect upstream changes.

### 3. Rules Engine Architecture Expansion
1. Refactor `Adventorator.rules` into submodules (e.g., `ability`, `combat`, `spells`, `conditions`, `resources`, `environment`) and formalize versioned interfaces so executor tools can call into them. Maintain backward compatibility with `Dnd5eRuleset` while adding richer methods (saving throws, damage resolution with resistances, rest handling, concentration checks, etc.).


2. Introduce immutable dataclasses for SRD constructs (class features, spell effects, condition definitions) and expose lookup APIs that pull from the ingested SRD data store.
3. Wire deterministic RNG seeding through every new mechanic, mirroring the existing dice and check helpers so tests and previews remain reproducible.



### 4. Mechanics Coverage Roadmap
Deliver SRD coverage in thematic increments, each hidden behind new feature flags until stable:

| Increment | Focus |
|-----------|-------|
| **Core Abilities** | Skill/saving throw proficiency rules, contested checks, passive scores, initiative variants. |
| **Combat Core** | Weapon properties, armor/AC calculation, conditions, exhaustion, grappling/shoving, critical/fumble tables. |
| **Spellcasting** | Spell attack rolls, save DCs, area effects, concentration, ritual casting, slot tracking. |
| **Classes & Races** | Level progression tables, hit dice, archetype features, racial traits, resting mechanics. |
| **Equipment & Economy** | Encumbrance, ammunition, consumables, crafting downtime activities. |
| **Monsters & NPCs** | Stat block execution (multiattack, legendary/lair actions), recharge mechanics, templates. |
| **Exploration & Social** | Travel pace, visibility, traps, downtime activities, tool proficiencies. |

For each block, define executor tool schemas (`attack`, `apply_condition`, `cast_spell`, etc.), rule-engine entry points, and event payloads before coding.

### 5. Integration with Commands, Executor, and MCP
1. Expand the in-memory tool registry and executor handlers to cover all SRD actions, mirroring the attack handler’s mechanics/events structure while keeping dry-run versus apply parity.



2. Update `/roll`, `/check`, `/do`, `/encounter`, and future commands to request richer previews (e.g., conditional saves, spell descriptions) and persist the resulting mechanics into both the events ledger and activity log once the corresponding feature flag is enabled.



3. Extend the MCP adapters so remote clients can offload heavy computations (e.g., spell area resolution) using the same deterministic logic shipped in-process, giving parity across deployments.



### 6. Testing, Validation, and Observability
1. For every mechanic, add golden-unit tests with fixed seeds and fixture data drawn from SRD examples (e.g., fireball damage, grappling DC). Combine them with scenario tests that drive slash commands end-to-end through the executor to guarantee event emission and narration formatting.



2. Build contract tests that replay full encounter transcripts and assert ledger parity to guard the deterministic event substrate described in EPIC-CDA-CORE-001.



3. Instrument new mechanics with metrics/logging tags (e.g., `rules.saves.success`, `rules.spells.concentration_failed`) following the existing observability patterns, and surface health dashboards before enabling feature flags globally.
4. Document migration guides, SRD ingestion reproducibility steps, and feature-flag rollout plans inside the epic and CHANGELOG.

### 7. Release & Maintenance Plan
1. Stage rollout behind granular `features.ruleset_5e.*` toggles layered under the existing `[features]` block so operations can enable subsystems independently.



2. Publish authoritative docs for builders and DMs explaining how Adventorator maps SRD terminology to executor tools, referencing the canonical SRD data store and event schemas.
3. Establish a periodic validation job that diff-checks the ingested SRD data against the upstream PDF checksum to detect licensing updates or errata.

## Risks & Dependencies
- **Licensing & Provenance**: Must respect Wizards’ SRD license—keep ingestion tooling and derived data auditable through importer logs and events.


- **Scope Creep**: SRD optional rules (e.g., feats, mass combat) should be explicitly triaged into later milestones to avoid blocking the core loop.
- **Performance**: Spell and monster resolution can be heavy; profile executor previews and consider caching static SRD lookups.
- **UX Consistency**: Ensure narration/orchestration logic keeps pace with the expanded mechanics so `/do` previews stay comprehensible.

## Testing
- ⚠️ Tests not run (read-only QA review)
