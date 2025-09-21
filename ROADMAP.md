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
| Content Retrieval (Phase 6) | ✅ Complete | Ingestion & retrieval context bundling (now historical; may evolve under future ingestion epic). |
| Map Rendering MVP (Phase 12) | 🛣️ Planned | Static rendered encounter map via Pillow with cache invalidation. |
| Modal Scenes (Phase 13) | 🛣️ Planned | Exploration ↔ combat branching & merge semantics. |
| Campaign & Character Ingestion (Phase 14) | 🛣️ Planned | Structured import with preview-confirm tool chain. |

## 6. GM Controls & Operational Hardening (Phases 15–16) — 🛣️ Planned
| Phase | Status | Scope |
|-------|--------|-------|
| GM Controls & Safety (Phase 15) | 🛣️ Planned | GM-only override tools, rewind via event cursor, content filters. |
| Hardening & Ops (Phase 16) | 🛣️ Planned | Rate limits, degraded modes, SLO instrumentation, cost guards. |

## 7. Cross-Cutting Epics — 🔄 / 🛣️
| Epic | Status | Purpose |
|------|--------|---------|
| Action Validation (EPIC-AVA-001) | 🔄 Maturing | Planner → Orchestrator → Executor validation chain; evolving with ActivityLog dependency. |
| Activity Log Mechanics Ledger (EPIC-ACTLOG-001) | 🛣️ Planned | Unified auditable mechanics ledger (taxonomy, schema, determinism, metrics). |

## 8. Feature Flag Overview
| Flag | Default | Purpose |
|------|---------|---------|
| `features.planner` | on (prod controlled) | Enable `/act` planning. |
| `features.executor` | off (guarded) | Enable execution tool chain (preview/apply). |
| `features.executor_confirm` | on | Enforce confirmation gating for mutating actions. |
| `features.events` | on (with kill-switch) | Event-sourced persistence. |
| `features.combat` | off (progressive rollout) | Encounter + combat tool surface. |
| `features.map` | off | Map rendering pipeline. |
| `features.retrieval` | on (scoped) | Content retrieval context enrichment. |
| `features.activity_log` | off | Mechanics ledger instrumentation rollout. |
| (See `config.toml` for authoritative list) |  |  |

## 9. Current Focus & Near-Term Priorities
1. Stand up ActivityLog epic scaffolding (issues, tasks, CI traceability integration).
2. Prepare map rendering MVP (benchmark render latency + snapshot tests).
3. Define ingestion/import preview-confirm tool patterns (Phase 14 alignment with executor).
4. Introduce GM remediation tools atop event ledger (rewind primitives). 

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
