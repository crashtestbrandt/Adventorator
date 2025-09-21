# ARCH-CDA-001 — Campaign Data & Deterministic World State Architecture

Status: Proposed (MVP scope locked)  
Last Updated: 2025-09-21  
Related Architecture: [ARCH-AVA-001](../architecture/ARCH-AVA-001-action-validation-architecture.md) (Action Validation Pipeline)  
Supersedes / Extends: Implicit legacy “flat tables as state” model (no prior ADR)  
Primary Audience: Engine / Rules / Persistence / AI pipeline contributors  

---

## 1. Executive Summary

This document defines the deterministic, auditable foundation for campaign world state powering the `/ask → /plan → /do` action‑validation pipeline ([ARCH-AVA-001](../architecture/ARCH-AVA-001-action-validation-architecture.md)).  
Core shift: move from “current DB rows = mutable truth” to a triad:

1. Immutable Campaign Package (seed provenance).
2. Append‑only Event Ledger (single mutation choke‑point: Executor).
3. Replayable Object Tree Projections + verifiable Snapshots (deterministic derived state).

This enables:
- Full audit / replay / fork.
- Deterministic RNG & canonical hashing.
- Contract-first evolution with event schema versioning.
- Capability/approval enforcement & feature‑flagged rollout.
- Future planner tiers and HTN expansion without state model churn.

---

## 2. High-Level Goals & Constraints

| Goal | Mechanism |
|------|-----------|
| Deterministic replay | Canonical JSON + dense replay_ordinal + hash chain |
| Audit-grade lineage | Origin metadata (package_id, source_path, file_hash) + import log + plan/execution FKs |
| Single writer safety | Executor-only event emission; planner/orchestrator read-only |
| Forkable worlds | Snapshot-based branching (no merge in MVP) |
| RNG reproducibility | Campaign-level seed + HKDF stream derivation |
| Strict contracts | JSON Schemas in `contracts/` + schema registry + parity CI |
| Observability & drift detection | Hash chain, idempotency keys, preview vs applied hash |
| Incremental extensibility | Reserved fields (phase_id, future beliefs store, compaction meta-event) |

Non-goals (MVP):
- Merge / cherry-pick of branches.
- Fog-of-war belief persistence (derive only).
- Physical (pre-materialized) snapshots (triggered later by SLO breach).
- Prompt-injection quarantine (basic audience gating only).
- Event compaction / pruning (reserved, not executed).

---

## 3. Core Representations

### 3.1 Campaign Package (Immutable Seed)
Filesystem bundle or registry artifact:
- `package.manifest.json` (versioned, signed, dependency-locked).
- `entities/` (Actor, Item, Space, Faction, Scene, RuleVariant).
- `edges/` (containment, adjacency, membership, bindings).
- `lore/` Markdown + front-matter (chunking hints, tags, audience).
- `ontologies/` (Tag taxonomy + Affordance definitions).
- Contracts snapshot (hash-pinned schemas).
- Optional recommended feature flag defaults (advisory only).

Manifest Key Fields:
```
package_id (ULID)
schema_version
engine_contract_range
signatures[]
dependencies[]
content_index (hash per file)
recommended_flags{}
ruleset_version
```

Deterministic Import:
Lexicographic ordering over (kind, stable_id). Synthetic `seed.*` events emitted; ImportLog retains audit granularity, but events alone suffice for replay.

### 3.2 Event Ledger (Authoritative Mutation History)
Append-only; each event envelope fields (MVP):

```
event_id (DB PK)
campaign_id (FK)
replay_ordinal (dense int, starts at 1 after genesis)
event_type
event_schema_version
world_time (ticks; may == replay_ordinal early)
wall_time_utc (audit)
prev_event_hash (SHA-256, 32 bytes; zeros for genesis)
payload_hash (canonical payload)
idempotency_key (16 bytes prefix of SHA-256 composite)
actor_id (FK actor/system)
plan_id (FK plans)
execution_request_id (FK execution_requests)
approved_by (nullable FK; required if requires_approval)
payload (JSON)
migrator_applied_from (nullable)
```

Deterministic invariants:
- Unique (campaign_id, replay_ordinal).
- Gap-free replay_ordinal (trigger enforces `new.replay_ordinal = last + 1`).
- Hash chain continuity (prev_event_hash == previous payload chain tip).
- Idempotency uniqueness (campaign scope).
- No floats / NaN / Infinity in payload (schema & encoder guard).

Genesis:
- `event_type = campaign.genesis`
- `prev_event_hash = 00…00`
- `payload = {}` (empty canonical object)
- Expected hash published in [ADR-0006](../adr/ADR-0006-event-envelope-and-hash-chain.md).

### 3.3 Object Tree (Derived Projections)
In-memory / optionally persisted read models built by folding events over seed:
- by_id: entity
- by_tag: tag → entity_ids
- containment_map: parent → children
- adjacency: space → neighbors
- actor_presence: scene → actor_ids (from movement / spawn events)
- affordances_index: entity_id → affordance tags
- retrieval_index: chunk_id → embeddings / metadata (audience enforced)

Projection regeneration:
- Full fold on restore.
- Incremental update per new event (reducers pure + deterministic).
- Validation hash: `state_digest = H(sorted(entity_id || entity_hash))`.

### 3.4 Snapshot (Logical)
Captures deterministic cut:
```
snapshot_id (ULID)
campaign_id
cutoff_event_id
cutoff_replay_ordinal
parent_snapshot_id (branch lineage)
package_manifest_hash
events_hash_chain_tip
state_digest
logical_snapshot_hash (self-hash; excludes this field in computation)
signature (optional ED25519)
key_id
created_at
```
Restore:
1. Load manifest (must match hash).
2. Replay seed events + subsequent events up to cutoff.
3. Recompute state_digest; assert equality.

Physical snapshot deferred; when implemented must embed `logical_snapshot_hash`.

---

## 4. Domain Model Essentials

Core entity canonical shape (runtime mirror of contract):
```
Entity {
  stable_id (ULID)
  kind (actor|item|space|faction|scene|rule_variant)
  name
  tags[]
  affordances[]
  props{}  (system neutral key-value)
  traits[] (lightweight descriptors)
  location_ref (stable_id or null)
  owner_ref (stable_id or null)
  visibility (player|gm|system)
  provenance { package_id, source_path, file_hash }
  status (active|deprecated|tombstoned)
  created_event_id
}
```

Edges:
```
Edge {
  stable_id
  type (contains|adjacent_to|member_of|bound_by_rule)
  src_ref
  dst_ref
  validity { start_event_id, end_event_id? }
  provenance { package_id, source_path, file_hash }
}
```

Affordances vs Tags:
- Tag: taxonomy / classification.
- Affordance: capability exposure (gate enabling certain event_type predicates).
Validation table binds (affordance, ruleset_version) → allowed_event_types[].

---

## 5. Determinism Layer

### 5.1 Canonical Serialization Policy
- UTF-8 NFC normalization.
- Object keys sorted lexicographically (byte-wise).
- Omit null fields.
- Integers only (64-bit signed range). Large > 2^53-1 stored as strings in props if unavoidable (not in core mutation fields).
- No floats permitted in event payload; fixed-point represented as integer minor units (e.g., *100).
- Booleans lowercase JSON (`true`/`false`).
- Arrays preserve order.
- Canonical hash: SHA-256 over encoded canonical JSON bytes.

### 5.2 Idempotency Key
`idempotency_key = first_16_bytes( SHA256(plan_id || campaign_id || event_type || tool_name || ruleset_version || canonical(args_json)) )`
Ensures network retries produce single ledger entry.

### 5.3 RNG Stream Derivation
Inputs:
- campaign_rng_seed (128-bit raw)
- stream_name (e.g., ability_check, loot, narration)
- ruleset_version
- tool_version
- replay_ordinal (big-endian 8 bytes)
Derivation:
`base_seed = HKDF_SHA256( campaign_rng_seed, info = "AV1|" + ruleset_version + "|" + tool_version + "|" + stream + "|" + replay_ordinal_be8 )`
Roll sequence:
`roll_i = SHA256(base_seed || i_be4)` → map to dice size via modulus.
Recorded in payload:
```
rng: {
  stream: "ability_check",
  base_seed_hex: "...",
  rolls: ["d20:13","d20:5"],
  inputs: { dc: 14, advantage: false }
}
```
No ambient randomness outside Executor path (lint rule).

---

## 6. Concurrency & Consistency

Optimistic Apply Contract:
`apply_execution(request, expected_last_event_id)`  
On mismatch: return conflict object
```
{
  status: "conflict",
  expected_last_event_id,
  actual_last_event_id,
  chain_tip_hash
}
```
Clients may rebase (re-run plan) or abort.

Dense ordering:
- DB trigger asserts `NEW.replay_ordinal = (SELECT COALESCE(MAX(replay_ordinal),0)+1 FROM events WHERE campaign_id=NEW.campaign_id)`
- Unique constraint enforces singularity.

---

## 7. Branching & Forking

Fork:
- Create new campaign row with reference `parent_snapshot_id`.
- Replay snapshot + optionally additional seed transformations (none in MVP).
- New replay_ordinal starts at 1 (fresh ledger context).
No merge in MVP; ADR documents deliberate exclusion.

Lineage:
- Derived by walking parent_snapshot_id chain to root (package manifest).

---

## 8. Capability & Approval Model

Tables:
- roles (gm, player, system)
- capabilities (event.*, tool.*)
- role_capabilities
- actor_role_assignments (discord_user_id, campaign_id, role_id)
- capability_denies (optional future extension)

Executor gate:
1. Resolve actor effective capabilities.
2. Validate required_capabilities from tool → event mapping.
3. If event_type requires approval and approved_by null → reject (DB CHECK ensures enforcement).
4. Record approved_by when GM or system grants.

---

## 9. Import Pipeline

Phases (all transactional & idempotent):

| Phase | Input | Output | Synthetic Events |
|-------|-------|--------|------------------|
| Manifest Validate | manifest + contracts | Parsed model | `seed.manifest.validated` (optional) |
| Entities | entity files | Entities table rows | `seed.entity_created` |
| Edges | edge files | Edge rows | `seed.edge_created` |
| Tags/Affordances | ontology files | Tag & affordance registries | `seed.tag_registered` |
| Lore Chunks | markdown | ContentChunk rows | `seed.content_chunk_ingested` |
| Finalize | all above | ImportLog entries | `seed.import.complete` |

Determinism:
- Sorted deterministic iteration.
- Collision policy: if stable_id exists with different file_hash → fail import.

ImportLog Fields:
`sequence_no, phase, object_type, stable_id, file_hash, action, timestamp, manifest_hash`

---

## 10. Retrieval / Knowledge Base

ContentChunk:
```
chunk_id
entity_ref (optional)
title
body_md
audience (player|gm|system)
tags[]
affordances_hints[]
source_path
content_hash
embedding_meta { model_id, index_strategy_id, built_at, source_hash }
```
Index provenance ensures stale detection when model or strategy changes. MVP: audience enforcement + simple tag filters; embeddings optional behind feature flag.

---

## 11. Planner & Orchestrator Integration

- `/ask` (future ImprobabilityDrive) consumes retrieval index (audience-filtered) + entity name resolution (canonical stable_ids).
- `/plan` emits Plan steps referencing stable_ids only (no fuzzy free text).
- Orchestrator enforces policies (banned verbs, DC bounds, capabilities).
- Executor produces an `ability_check_resolved` event (MVP) plus any narrative events (type `narration.emitted`).
- Plan lineage: plan_id FK → each ExecutionRequest → events referencing execution_request_id.

---

## 12. Event Schema Versioning & Migration

Registry:
`event_type -> { latest_version, write_enabled, migrator_ref }`

Replay:
1. Load raw event (original version).
2. If version < latest → apply pure migrator chain to current in-memory representation.
3. Reduce to projections.
4. Do not mutate stored payload (immutability).
5. Record `migrator_applied_from` if migration occurred.

Golden corpus fixtures ensure migrations remain reversible and idempotent.

Reserved future event types:
- `state_compacted`
- `belief_projection_updated`
- `package_dependency_upgraded`

---

## 13. Snapshot Lifecycle & Retention

Cadence:
- Every N=1000 events OR 24h OR manual trigger.
Retention:
- Keep last 5 full logical snapshots per branch initially (no pruning logic applied until compaction ADR executed).
Validation:
- `restore(snapshot) -> recompute state_digest` must match stored state_digest; CI gate.
Signing (optional early, recommended):
- ED25519 over canonical snapshot minus signature fields.
- Key rotation: new key_id; historical signatures retained.

---

## 14. Observability & Metrics

Counters:
- `importer.entities.created`
- `events.applied`
- `events.conflict`
- `replay.verify.ok/fail`
- `snapshot.create.ok/fail`
- `planner.tier.level.<n>`
- `executor.apply.latency_ms` (histogram)
- `rng.stream.<name>.rolls`

Logs (structured):
- plan_id, execution_request_id, event_id, replay_ordinal, chain_tip, state_digest
- conflict detail on optimistic concurrency failure
- hash_mismatch (critical alert)
- import divergence (collision)

Nightly Replay Verification Job:
1. Select latest snapshot.
2. Replay events to tip in isolated DB.
3. Compare state_digest + chain tip.
4. Emit `replay.verification` event or alert.

---

## 15. Performance & SLOs

| Operation | SLO (P95) | Breach Trigger |
|-----------|-----------|----------------|
| Import small pack (≤200 entities) | ≤ 3s | 3 consecutive breaches |
| Replay 2k events | ≤ 2s | Any > 2× SLO |
| Snapshot creation | ≤ 500ms | 5 consecutive breaches |
| Executor apply | ≤ 250ms | 5 consecutive breaches |

Escalation: if replay SLO breached and event count > threshold (50k), evaluate physical snapshot enablement.

---

## 16. Security & Trust

- Hash chain + snapshot signature for tamper evidence.
- Package signature (publisher key) + optional registry notarization (future).
- Capability enforcement at DB & application layers.
- Audience gating prevents GM/system content leakage.
- No secrets in events/snapshots (only `secret_ref` tokens).
- Tool sandbox (resource-limited) recommended; base policy: no outbound network.

---

## 17. Backward & Forward Compatibility

Backward:
- Legacy tables (ContentNode) shimmed → ContentChunk adapter; dual read until migration window closure.
- Events extended with nullable new columns initially; backfill stable_id & chain.

Forward:
- Reserved fields (phase_id, belief_state_ref).
- Reserved event types (compaction, belief projection) documented to avoid name collisions.

---

## 18. MVP Scope (Adopt Now)

Included:
- Campaign Package (manifest + entities + chunks) minimal schema.
- Deterministic importer + synthetic seed events.
- Extended events table (envelope fields, hash chain, idempotency).
- RNG derivation & recording.
- Capability model + approval DB CHECK.
- Logical snapshots + restore + state_digest.
- Branch (fork) support (no merge).
- Audience enforcement in retrieval.
- CI canonical JSON test vectors + parity schema checks.

Excluded (documented for future):
- Merge / cherry-pick logic.
- Physical snapshots.
- Belief persistence.
- Compaction meta-event logic.
- Transparency log signing policy enforcement (initial stub only).
- Prompt injection scrubbing.

---

## 19. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Canonical serialization drift | Golden test vectors; cross-platform CI |
| Replay performance degradation | SLO monitoring + threshold switch to physical snapshots |
| RNG misuse | Lint for disallowed randomness; unit tests assert stable sequences |
| Capability misconfig | Startup health check verifying expected grants |
| Hash chain corruption | On detection: halt applies; require admin intervention |
| Import partial failure | Transactional phases; idempotent detection via stable_id + file_hash |
| Event migration regressions | Golden corpus & migrator unit tests (pure functions) |

---

## 20. Acceptance Tests Matrix (MVP)

| Test | Assertion |
|------|-----------|
| Genesis hash | Matches documented constant |
| Idempotent retry storm | 1 event written; others return same event_id |
| Conflict apply | Returns conflict payload; no partial ledger write |
| Replay determinism | Restore -> state_digest stable |
| Unicode normalization | Composed/decomposed produce identical content_hash |
| Audience isolation | Player access to GM chunk denied |
| RNG determinism | Same plan_id & ordinal => identical roll sequence |
| Fork equivalence | Fork snapshot digest == baseline digest |
| Hash chain continuity | Each prev_event_hash matches prior payload hash |

---

## 21. Implementation Ordering (Condensed)

1. Canonical JSON encoder + test vectors.
2. Alembic migrations (events, snapshots, campaigns, content_chunks, roles/capabilities).
3. Genesis event emission on campaign creation.
4. RNG utilities + HKDF helper.
5. Importer (dry-run + apply) + synthetic seed events.
6. Capability enforcement & approval DB checks.
7. Executor: optimistic concurrency + idempotency key + roll capture.
8. Snapshot create/restore + digest.
9. Branch (fork) command.
10. CI parity & replay verification job.

---

## 22. Glossary

| Term | Definition |
|------|------------|
| Package | Immutable content bundle seeding a campaign |
| Seed Event | Synthetic `seed.*` ledger entry produced during import |
| Replay Ordinal | Dense per-campaign integer ordering events |
| State Digest | Canonical hash summarizing derived world state |
| Idempotency Key | Deterministic hash preventing duplicate event application |
| Fork | New campaign branch initialized from snapshot |
| Affordance | Tag enabling rules-governed action potential |
| Capability | Permission to emit an event/tool action |

---

## 23. ADR Cross-References

| ADR | Purpose |
|-----|---------|
| [ADR-0006](../adr/ADR-0006-event-envelope-and-hash-chain.md) | Deterministic Event Envelope & Hash Chain |
| [ADR-0007](../adr/ADR-0007-canonical-json-numeric-policy.md) | Canonical JSON & Numeric Policy |
| [ADR-0008](../adr/ADR-0008-rng-streams-seed-derivation.md) | RNG Streams & Seed Derivation |
| [ADR-0009](../adr/ADR-0009-capability-approval-enforcement.md) | Capability & Approval Enforcement |
| [ADR-0010](../adr/ADR-0010-snapshot-fork-lineage.md) | Snapshot & Fork Lineage |
| [ADR-0011](../adr/ADR-0011-package-import-provenance.md) | Package Import Provenance |
| [ADR-0012](../adr/ADR-0012-event-versioning-migration-protocol.md) | Event Versioning & Migration Protocol |

---

## 24. Epic Decomposition

Epic proposals (concise):

1. [EPIC-CDA-CORE-001](../implementation/epics/EPIC-CDA-CORE-001-deterministic-event-substrate.md) Deterministic Event Substrate  
Scope: Canonical JSON encoder, envelope fields, hash chain, idempotency key.  
ADRs: 0006, 0007.  
Deps: None (foundation).  
Acceptance focus: Golden serialization vectors; hash continuity test; rejection of floats/NaN.  
Enablers: Required by all downstream epics (Executor, Migration, Snapshots).

2. [EPIC-CDA-IMPORT-002](../implementation/epics/EPIC-CDA-IMPORT-002-package-import-and-provenance.md) Package Import & Provenance  
Scope: Manifest parsing, lexicographic deterministic ingest, synthetic seed events, ImportLog, provenance fields.  
ADRs: 0011 (+ 0006 for seed events).  
Deps: Core-001.  
Acceptance focus: Replay after import yields stable state_digest; collision (stable_id,file_hash) failure test; provenance fields present in events.

3. EPIC-CDA-RNG-003 Deterministic RNG Streams  
Scope: HKDF seed derivation, stream naming, roll recording in payload, lint to forbid ambient randomness.  
ADRs: 0008.  
Deps: Core-001 (envelope), partly usable before Import-002 completes.  
Acceptance focus: Same (plan_id,replay_ordinal,stream) ⇒ identical sequence; negative test for nondeterministic usage (lint/e2e).

4. EPIC-CDA-CAP-004 Capability & Approval Enforcement  
Scope: roles / capabilities / role_capabilities / assignments tables; approval CHECK; executor gate wiring.  
ADRs: 0009.  
Deps: Core-001 (events), Import-002 (optional seeding of baseline roles).  
Acceptance focus: Unauthorized event blocked; approval-required event rejected without approved_by; health check validates baseline grants.

5. EPIC-CDA-EXEC-005 Executor Concurrency & Apply Path  
Scope: Optimistic concurrency (`expected_last_event_id`), conflict object schema, idempotent replays, RNG integration, capability gate invocation.  
ADRs: 0006, 0008, 0009.  
Deps: Core-001, RNG-003, CAP-004.  
Acceptance focus: Conflict test returns stable payload; retry storm collapses to one event_id; roll capture present.

6. EPIC-CDA-SNAP-006 Logical Snapshots & Forking  
Scope: Snapshot creation, restore verification, fork lineage, state_digest computation, optional ED25519 signing scaffold.  
ADRs: 0010 (fork), 0006 (hash chain).  
Deps: Executor path (events must exist), Import-002.  
Acceptance focus: Snapshot → restore → identical state_digest; fork digest equivalence test; signature verification (if enabled).

7. EPIC-CDA-MIG-007 Event Versioning & Migration Framework  
Scope: Registry, pure migrator chain, `migrator_applied_from` recording, golden corpus fixtures.  
ADRs: 0012, 0006 (envelope immutability).  
Deps: Core-001, Executor stable.  
Acceptance focus: Round-trip migration idempotency; downgrade absence (immutability); mixed-history replay parity.

8. EPIC-CDA-OBS-008 Observability & Replay Verification  
Scope: Nightly replay job, metrics (`events.applied`, `replay.verify.ok/fail`, SLO latency histograms), hash_mismatch alert, structured log fields.  
ADRs: 0006 (hash chain canonical signals).  
Deps: Snapshots (for baseline), Executor.  
Acceptance focus: Induced mismatch triggers alert; metrics surfaced; runbook snippet for incident classification.

9. EPIC-CDA-RET-009 Retrieval / Knowledge Base Index  
Scope: ContentChunk audience enforcement, optional embeddings (flag), provenance invalidation rules, integration with `/ask` (ImprobabilityDrive) and `/plan`.  
ADRs: (Indirectly uses provenance: 0011).  
Deps: Import-002 (chunks), IPD / AVA epics for consumer flows.  
Acceptance focus: Player vs GM audience isolation test; stale index invalidation on manifest change; feature flag rollback (disable embeddings).

10. EPIC-CDA-SEC-010 Integrity & Signing Hardening  
Scope: Mandatory snapshot signing, package signature validation pipeline, transparency log stub.  
ADRs: 0010 (snapshot), 0011 (package provenance).  
Deps: Snapshots, Import.  
Acceptance focus: Tampered snapshot detection; unsigned package rejection; audit log of verification steps.

11. EPIC-CDA-COMP-011 Compaction & Physical Snapshots (Deferred)  
Scope: Physical snapshot format, compaction meta-events, retention policy.  
ADRs: Future (to be authored).  
Deps: Snapshots, Migration framework.  
Acceptance focus: Replay from physical snapshot == logical baseline; compaction preserves hash chain invariants.

12. EPIC-CDA-MERGE-012 Branch Merge & Belief State (Deferred)  
Scope: Out-of-scope MVP (documented), future fork merge semantics, belief persistence store.  
ADRs: New future ADR(s).  
Deps: Snapshots, Forking, Migration.  
Acceptance focus: Prototype merge conflict classification; belief store deterministic projection tests.

13. EPIC-CDA-ONT-013 Ontology & Affordance Governance Integration  
Scope: Affordance validation table (affordance,ruleset_version) → allowed_event_types; alignment with future planner semantics & ImprobabilityDrive tags.  
ADRs: Leverages 0011 (ontology provenance); may require new ADR.  
Deps: Import, Retrieval (ontology exposure), AVA and IPD data contracts.  
Acceptance focus: Attempt disallowed event_type → predicate failure; ontology version bump invalidates stale affordances cache.

Cross-epic dependency highlights:
- Foundational chain: CORE-001 → IMPORT-002 → EXEC-005 → SNAP-006 → MIG-007 → OBS-008.
- RNG (RNG-003) and CAP-004 integrate early to reduce retrofit risk.
- Retrieval (RET-009) gates planner/improbability enhancements but is orthogonal to hash chain.
- Deferred epics (COMP-011, MERGE-012) explicitly isolated to avoid blocking MVP acceptance criteria in Section 18 of the architecture.
- Ontology (ONT-013) bridges CDA and AVA/IPD, enabling richer predicate gating later without altering ledger invariants.

Feature flag strategy (concise):
- executor / action_validation flags already present (reuse for gating event emission path changes).
- New flags: `features.retrieval.enabled`, `features.snapshots.signing`, `features.event_migrations` (write-enable switch), `features.compaction` (future), `features.rng.strict` (enforce lint fail vs warn).

Minimal acceptance test alignment (mapping to architecture Section 20):
- CORE-001: Genesis hash, Unicode normalization, Hash chain continuity.
- EXEC-005: Idempotent retry storm, Conflict apply.
- RNG-003: RNG determinism.
- SNAP-006: Fork equivalence.
- IMPORT-002 + RET-009: Audience isolation (with content chunks).
- OBS-008: Replay determinism nightly job.

Traceability integration:
- Each epic file added under epics following existing template.
- ADR references embedded per epic (avoid duplicating full rationale).
- Update roadmap (ROADMAP.md) section “Current Focus & Near-Term” to list active CDA epics once created.

---

## 24. Open Questions (Deferred Explicitly)

| Topic | Deferred Decision |
|-------|-------------------|
| Merge semantics | Out-of-scope MVP |
| Belief state persistence | Post-MVP |
| Physical snapshot format | Triggered by replay SLO breach |
| Compaction process | After retention policy ADR |
| Prompt injection mitigation | After initial retrieval hardening |

---

## 25. Conclusion

This architecture establishes a deterministic, auditable substrate tightly aligned with action validation. It isolates volatility (content, planning sophistication) from invariants (ledger, canonical hashing, replay). It supplies measurable checkpoints (SLOs) and clear extension seams (forking, migrations, compaction) without overcommitting to premature complexity.