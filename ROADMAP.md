# Project Roadmap

This high-level roadmap summarizes major milestones: what is **done**, what is **in progress / near-term**, and what is **planned / aspirational**.

Authoritative sources of truth:
- Architecture & design decisions: `docs/architecture/` and `docs/adr/`
- Active Epics & Stories: `docs/implementation/epics/`
- Feature flags: `config.toml`
- Execution traceability scripts: `scripts/build_implementation_plan.py` & related quality gates

## Legend
- ✅ Complete
- 🔄 In Progress / Rolling Out
- 🧪 Experimental / Behind Feature Flag
- 🛣️ Planned (Issues Open)
- 🧭 Future / Intent (Not Yet Scheduled)

---
## 1. Core Foundations (Phases 0–2) — ✅ Complete
| Theme | Outcome |
|-------|---------|
| Secure Interaction Skeleton | Verified Discord signature handling, deferred replies, basic pong + metrics/logging. |
| Deterministic Mechanics Core | Dice & ability checks with seedable RNG and auditability. |
| Persistence & Sessions | Postgres schemas (campaigns, characters, scenes, transcripts) + restart-safe state. |

## 2. AI Introduction & Planning Layer (Phases 3–5) — ✅ Complete
| Theme | Outcome |
|-------|---------|
| Narrator Shadow Mode | Safe LLM proposals without state mutation; JSON contract & validation. |
| `/act` Planner & Tool Catalog | Freeform → validated command invocation with strict schema & caching. |
| Architectural Maturation | Containerization, Postgres parity, context-aware orchestrator groundwork. |

## 3. Execution & Safety Pipeline (Phases 7–9) — ✅ Complete
| Theme | Outcome |
|-------|---------|
| Executor (Dry Run) | ToolChain preview (no mutation) with structured contracts & metrics. |
| Confirmation Flow | PendingAction gating with TTL + idempotency and explicit confirm/cancel loop. |
| Event Sourcing Foundation | Append-only ledger for mutations + deterministic fold/replay helpers. |

## 4. Tactical Systems (Phases 10–11) — ✅ Complete
| Theme | Outcome |
|-------|---------|
| Encounter Engine | Turn sequencing, locking model, golden-log repeatability. |
| Minimal Combat Actions | Attack/damage pipeline via executor + consistent preview/apply cycle. |

## 5. Extended World & Content (Phases 6, 12–14) — Mixed Status
| Phase | Status | Scope |
|-------|--------|-------|
| Content Retrieval (Phase 6) | ✅ Complete | Retrieval context bundling (pre-CDA; superseded by ARCH-CDA-001 package import model). |
| Map Rendering MVP (Phase 12) | 🛣️ Planned | Static rendered encounter map via Pillow with cache invalidation. |
| Modal Scenes (Phase 13) | 🛣️ Planned | Exploration ↔ combat branching & merge semantics. |
| Campaign Package Import (EPIC-CDA-IMPORT-002) | ✅ Complete | Deterministic manifest/entity/edge/tag/chunk import with ledger-backed seed events (ADR-0011, ARCH-CDA-001). |
| Character Import / Sheet Normalization (Phase 14) | 🛣️ Planned | Structured character sheet ingestion building atop provenance & ImportLog patterns. |

## 6. GM Controls & Operational Hardening (Phases 15–16) — 🛣️ Planned
| Phase | Status | Scope |
|-------|--------|-------|
| GM Controls & Safety (Phase 15) | 🛣️ Planned | GM-only override tools, rewind via event cursor, content filters. |
| Hardening & Ops (Phase 16) | 🛣️ Planned | Rate limits, degraded modes, SLO instrumentation, cost guards. |

## 7. Cross-Cutting Epics — 🔄 / 🛣️
| Epic | Status | Purpose |
|------|--------|---------|
| Action Validation (EPIC-AVA-001) | 🔄 Maturing | Planner → Orchestrator → Executor validation chain (ADR-0001, ADR-0003, ADR-0004) with ActivityLog dependency. |
| Mechanics Activity Log (EPIC-ACTLOG-001) | 🛣️ Planned | Unified auditable mechanics ledger (taxonomy, schema, determinism, metrics). |
| Deterministic Event Substrate (EPIC-CDA-CORE-001) | ✅ Complete | Canonical JSON encoder, hash chain, idempotency, metrics (ADR-0006, ADR-0007, ARCH-CDA-001). |
| Campaign Package Import & Provenance (EPIC-CDA-IMPORT-002) | ✅ Complete | Deterministic package ingest + ledger-backed seed events + ImportLog (ADR-0011, ARCH-CDA-001). |
| Campaign Data Architecture (ARCH-CDA-001) | 🛣️ Planned | Unified event-sourced world model (ledger, importer, RNG, snapshots, provenance). |

## 8. Feature Flag Overview
| Flag | Default | Purpose |
|------|---------|---------|
| `features.planner` | on (prod controlled) | Enable `/plan` semantic routing. |
| `features.executor` | off (guarded) | Enable execution tool chain (preview/apply). |
| `features.executor_confirm` | on | Enforce confirmation gating for mutating actions. |
| `features.events` | true (rollback: set false) | Event-sourced persistence. |
| `features.combat` | off (progressive rollout) | Encounter + combat tool surface. |
| `features.map` | off | Map rendering pipeline. |
| `features.retrieval` | on (scoped) | Content retrieval context enrichment. |
| `features.activity_log` | true | Mechanics ledger instrumentation rollout (disable for rollback). |
| (See `config.toml` for authoritative list) |  |  |

## 9. Current Focus & Near-Term Priorities
1. Monitor EPIC-CDA-CORE-001 deployment (hash chain + idempotency telemetry) and socialize executor reuse patterns.
2. Roll out EPIC-CDA-IMPORT-002 importer tooling to staged campaigns and document operational runbooks.
3. Stand up ActivityLog (EPIC-ACTLOG-001) issue scaffolding to unblock Action Validation audit requirements.
4. Prepare map rendering MVP (benchmark render latency + snapshot tests).
5. Define character import schema (Phase 14) leveraging provenance & ImportLog patterns.
6. Introduce GM remediation tools atop event ledger (rewind primitives). 

## 10. Future / Intent (Exploratory — 🧭)
These are directional concepts not yet scheduled

### Campaign Data Pipeline

### Character Sheet Pipeline

### Godot Rules Engine

### Discord Activity for Encounters

### 5E SRD Implementation

### Full MCP Adoption

### Full OpenAI API Adoption

### Per-Guild Policy Configuration

### RP Conversation Stack

### Multi-system ruleset plugin architecture (5e SRD → other OGL systems).

### Enhanced Logging Solution

### Real-time streaming narration (incremental token flush with early mechanics block)

### Formal evaluation harness for planner/executor regression scoring.

### Speech-to-Text / Text-to-Speech

### Python Rules Engine

### Encounter Map Rendering (Pillow)

### Contextualizing Campaign/Party/"Whisper"/Individual Scenes/Threads

### Exports

* Campaign State
* Character Sheet

### Campaign Extraction/Creation Pipeline

### Party NPC Tools

### Admin Tools

## 11. Traceability & How to Update
When a planned item begins execution:
1. Open / link GitHub issue(s) under appropriate epic.
2. Update status icon (✅ / 🔄 / 🛣️) in this roadmap.
3. If architectural scope changes, add or amend an ADR in `docs/adr/`.
4. Run `make implementation-plan` (or `make quality-gates`) to verify epics remain consistent.
5. Reference new epic/story IDs in commits for audit continuity.

## 12. Changelog & Release Coordination
Release-visible changes should continue aggregating in `CHANGELOG.md`. The Roadmap captures directional intent; the changelog captures shipped deltas.

---
### Maintenance Notes
- Keep tables lean; if a section grows beyond a screen, consider splitting into a new epic doc and linking.
- Avoid duplicating fine-grained acceptance criteria—those live with the epic/story markdown files.
- Remove or graduate Future/Intent items once they become scheduled (move to Planned with an issue link).

_Last updated: (set during commit)_
