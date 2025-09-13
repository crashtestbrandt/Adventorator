# Implementation Plan — Phase Descriptions

This document aggregates the “Phase N” issues from GitHub with their full descriptions for easy reference. Each section links back to the original issue.

## Phase 0 — Project skeleton & safety rails (no gameplay) ([#15](https://github.com/crashtestbrandt/Adventorator/issues/15)) — status: closed

**Goal:** A minimal, secure Discord Interactions handler with observability.

**Deliverables**
* Interactions endpoint (FastAPI/Express) that:
 * Verifies Ed25519 signatures
 * Immediately defer replies
 * Sends a trivial follow-up (“pong”)
 * Secrets via env; config via config.toml with feature flags (e.g., ff.rules=false, ff.llm=false)
* Logging/metrics:
 * Structured logs with correlation IDs per interaction
 * Basic metrics: ack latency, follow-up latency, error rate
 * CI: lint, tests, container build
 * Dev harness: make tunnel (ngrok/Cloudflare) and a tiny “fake Discord” payload replayer

**Exit criteria**
* ≥99% acks under 1.5s locally
* Replay tool can re-inject a captured interaction and produce the same output (idempotency).

**Rollback**
* Only this phase is active; revert to stub reply if anything fails.

---

## Phase 1 — Deterministic core (dice & checks), no LLM ([#16](https://github.com/crashtestbrandt/Adventorator/issues/16)) — status: closed

**Goal:** Useful bot with /roll and basic ability checks—pure rules, no AI.

**Deliverables**
* Rules Service v0 (library + HTTP tool endpoints):
  * Dice parser XdY+Z, adv/dis, crits; seedable RNG; audit log
  * Ability checks (proficiency, expertise), DC comparison
  * Slash commands: /roll, /check ability:<STR…> adv:<bool> dc:<int?>
* Unit & property tests (e.g., distribution tests for d20)

**Exit criteria**
* 100% deterministic from seed; property tests pass; audit log shows inputs/outputs.

**Rollback**
* Flip ff.rules=false → commands respond with an explanatory stub.

---

## Phase 2: Persistence & Session Plumbing ([#8](https://github.com/crashtestbrandt/Adventorator/issues/8)) — status: closed

**Goal:** Store characters/campaigns; keep transcripts; structure for later context.

**Deliverables**

* Postgres (or SQLite to start) schemas: campaigns, players, characters(jsonb), scenes, turns, transcripts
* Character CRUD: /sheet create|show|update
* Transcript writer: every bot I/O saved; golden log fixture for tests
* Thread orchestration: scene_id = channel_or_thread_id

**Exit criteria**

 * DB up via Docker; alembic upgrade head succeeds.
 * On any interaction, bot:
 * Verifies signature
 * Defers immediately
 * Resolves {campaign, player, scene} and logs a player transcript
 * /sheet create validates JSON via Pydantic and upserts to characters.
 * /sheet show fetches by name and returns a compact summary (ephemeral).
 * Bot writes a system transcript for sheet operations.
 * Tests pass on SQLite; app runs against Postgres.
 * Restart-safe: kill the app, restart, run /sheet show—the sheet persists.

**Rollback**

* If DB fails, commands degrade to ephemeral error without crashing the process.

---

## Phase 3 — LLM “narrator” in shadow mode ([#9](https://github.com/crashtestbrandt/Adventorator/issues/9)) — status: closed

**Goal:** Introduce the model without letting it change state.

**Deliverables**

* LLM client with JSON/tool calling: tools registered but disabled from mutating
* Clerk prompt (low temperature) for extracting key facts from transcripts
* Narrator prompt (moderate temperature) that proposes DCs and describes outcomes, but outputs:

  ```json
  {
    "proposal": {
      "action": "ability_check",
      "ability": "DEX",
      "suggested_dc": 15,
      "reason": "well-made lock"
    },
      "narration": "..."
  }
  ```

* Orchestrator compares proposal to Rules Service v0 and posts:
  * Mechanics block (actual roll, DC, pass/fail)
  * Narration text
* Prompt-injection defenses: tool whitelist, max tokens, strip system role leakage, reject proposals that reference unknown actors or fields

**Exit criteria**

* Shadow logs show ≥90% proposals sensible (manual spot-check)
* No unauthorized state mutations possible (unit tests enforce)

**Rollback**

* ff.llm=false returns rules-only responses.

---

## Phase 4 — Planner Layer and `/act` Command ([#56](https://github.com/crashtestbrandt/Adventorator/issues/56)) — status: open

Introduce an **LLM-driven planner** that can translate freeform user input into valid Adventorator commands. The implementation is incremental and defensive, with strong validation and rollback options.

**Key steps:**

* **Groundwork fixes:** clean up small issues (OpenAI client response path, Pydantic API changes, timezone-aware timestamps, safe Pydantic defaults) to reduce noise during rollout.
* **Planner contract:** define strict Pydantic models (`Plan`, `PlannerOutput`) and a system prompt that forces the LLM to output JSON with a single command and validated arguments.
* **Tool catalog:** auto-generate a schema catalog from the command registry (`all_commands()`), ensuring the planner cannot invent unknown shapes.
* **Planner service:** implement a `plan()` helper that builds prompts, invokes the LLM, and parses/validates JSON output defensively.
* **New `/act` command:** route freeform input through the planner, validate the selected command and args against the existing option models, then dispatch safely. Player input is persisted to transcripts before planning, like `/ooc`.
* **Parity:** `register_commands.py` and `cli.py` pick up `/act` automatically; users can test locally or in Discord with identical behavior.
* **Guardrails:** enforce an allowlist of commands (`roll`, `check`, `sheet.create`, `sheet.show`, `do`, `ooc`), size caps (≤16KB sheet JSON), and ephemeral errors for unknown or invalid plans. Planner “rationale” is logged but never shown to users.
* **Observability:** add structlog events and metrics counters (requests, parse failures, accepted/rejected decisions). Add a 30s cache to suppress duplicate LLM calls for identical input.
* **Latency & resilience:** keep the DEFERRED flow, apply a soft timeout, and fall back gracefully (default roll or user-friendly error). Feature flag `FEATURE_PLANNER_ENABLED` allows instant disable.
* **Testing:** unit tests for schema validation, plan parsing, and allowlist; integration tests with mocked LLM output; optional E2E test with SQLite to confirm transcripts and dispatches.
* **Rollout:** shadow in a dev guild, then canary in production with monitoring, before full availability. Document `/act` usage and examples. Rollback plan: flip the feature flag to disable without redeploy.
* **User experience:** freeform input like
  – `roll 2d6+3 for damage` → `/roll`
  – `make a dexterity check against DC 15` → `/check`
  – `create a character named Aria` → `/sheet.create` (or prompt for JSON)
  – `I sneak quietly` → `/do`
  …with deterministic rules resolving outcomes if `features_llm_visible` is enabled.

**Security considerations:** no direct tool execution; all planner output validated through option models; ephemeral error handling; strict input bounds; planner decisions logged with confidence but without leaking sensitive content.

**Future enhancements:** disambiguation mode for low-confidence plans, few-shot examples to improve stability, and per-guild defaults for planner behavior.

**Definition of done:** `/act` works in CLI and Discord, only allowlisted commands can be executed, invalid inputs are handled gracefully, caching and telemetry are in place, and feature flag control is available.

---

### Phase 4: Milestone 0 — Groundwork

**Why:** eliminate avoidable noise while rolling out the planner.

* Fix `LLMClient.generate_json` (OpenAI path): use `response.choices[0].message.content`.
* In `scripts/cli.py`, treat `FieldInfo.is_required` as a **callable** (Pydantic v2).
* Make naive timestamps timezone-aware (`Turn.started_at`).
* Switch mutable Pydantic defaults to `default_factory` in `discord_schemas.py`.

**Acceptance:** unit tests green; no behavior change to existing commands.

---

### Phase 4: Milestone 1 — Define a minimal planner contract

**Files to add**

1. `src/Adventorator/planner_schemas.py`

```python
from pydantic import BaseModel, Field
from typing import Dict, Any, Literal, Optional

class Plan(BaseModel):
    command: str = Field(description="Command name, e.g., 'roll' or 'sheet.create'")
    args: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)  # optional
    rationale: Optional[str] = None  # optional, never shown to Discord users

class PlannerOutput(BaseModel):
    plan: Plan
```

2. `src/Adventorator/planner_prompts.py`

```python
SYSTEM_PLANNER = (
    "You are the Router. Map the user's message to ONE known tool (command) "
    "and valid JSON args. Respond with ONLY a single JSON object matching:\n"
    '{ "plan": { "command": "<name>", "args": { ... }, "confidence": <0..1>, "rationale": "<short>" } }\n'
    "Never invent tools. Prefer the closest supported tool.\n"
    "If the user implies dice or an ability check, choose the appropriate tool.\n"
    "If the request is unfulfillable, choose the closest safe tool with minimal args."
)
```

**Acceptance:** types import cleanly; no runtime use yet.

---

### Phase 4: Milestone 2 — Introspect tools safely for the LLM

**Goal:** generate a **grounding catalog** from the command registry; never let the model invent shapes.

**File to add** `src/Adventorator/planner.py`

```python
from __future__ import annotations
from typing import Any
import orjson

from Adventorator.commanding import all_commands
from Adventorator.planner_prompts import SYSTEM_PLANNER
from Adventorator.planner_schemas import PlannerOutput
from Adventorator.llm_utils import extract_first_json
from Adventorator.llm import LLMClient

def _catalog() -> list[dict[str, Any]]:
    cat = []
    for cmd in all_commands().values():
        name = cmd.name if not cmd.subcommand else f"{cmd.name}.{cmd.subcommand}"
        cat.append({
            "name": name,
            "description": cmd.description,
            "options_schema": cmd.option_model.model_json_schema(),
        })
    return cat

def build_planner_messages(user_msg: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_PLANNER},
        {"role": "user", "content": "TOOLS:\n" + orjson.dumps(_catalog()).decode() + "\n\nUSER:\n" + user_msg},
    ]

async def plan(llm: LLMClient, user_msg: str) -> PlannerOutput | None:
    msgs = build_planner_messages(user_msg)
    text = await llm.generate_response(msgs)
    data = extract_first_json(text or "")
    if not data:
        return None
    try:
        return PlannerOutput.model_validate(data)
    except Exception:
        return None
```

**Acceptance:** dev test—`plan()` returns `PlannerOutput | None` using a mocked `LLMClient`.

---

### Phase 4: Milestone 3 — Implement `/act` command (planner → dispatcher)

**File to add** `src/Adventorator/commands/act.py`

```python
from pydantic import Field
from Adventorator.commanding import Invocation, Option, slash_command, find_command
from Adventorator.planner import plan
from Adventorator.db import session_scope
from Adventorator import repos

class ActOpts(Option):
    message: str = Field(description="Freeform action/request")

@slash_command(name="act", description="Let the DM figure out what to do.", option_model=ActOpts)
async def act(inv: Invocation, opts: ActOpts):
    # 0) prerequisites
    if not (inv.settings and getattr(inv.settings, "features_llm", False) and inv.llm_client):
        await inv.responder.send("❌ LLM planner is disabled.", ephemeral=True)
        return
    user_msg = (opts.message or "").strip()
    if not user_msg:
        await inv.responder.send("❌ Provide a message.", ephemeral=True)
        return

    # 1) ensure scene + persist player's input like /ooc does
    guild_id = int(inv.guild_id or 0)
    channel_id = int(inv.channel_id or 0)
    user_id = int(inv.user_id or 0)
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.write_transcript(s, campaign.id, scene.id, channel_id, "player", user_msg, str(user_id))
        scene_id = scene.id

    # 2) call planner
    out = await plan(inv.llm_client, user_msg)  # type: ignore[arg-type]
    if not out:
        await inv.responder.send("🤖 I couldn't decide on an action.", ephemeral=True)
        return

    # 3) resolve command safely (allowlist using registry)
    cmd_name = out.plan.command.replace(":", ".")
    top, _, sub = cmd_name.partition(".")
    cmd = find_command(top, sub or None)
    if not cmd:
        await inv.responder.send(f"❌ Unknown or unsupported command: `{cmd_name}`", ephemeral=True)
        return

    # 4) validate args with the command's own Option model
    try:
        opts_obj = cmd.option_model.model_validate(out.plan.args)
    except Exception as e:
        await inv.responder.send(f"❌ Invalid options for `{cmd_name}`: {e}", ephemeral=True)
        return

    # 5) dispatch; preserve same Invocation (Responder, ids, settings, llm_client)
    await cmd.handler(inv, opts_obj)
```

**Acceptance:**

* `/act` appears in CLI and behaves like an orchestrated router.
* It can successfully route:
  “roll 2d6+3” → `/roll`,
  “dex check dc 15” → `/check`,
  “create sheet …” → `/sheet.create`,
  “I sneak quietly” → `/do`.

---

### Phase 4: Milestone 4 — Registration & CLI parity

* `register_commands.py` picks up `act` automatically via `load_all_commands()` (no schema tricks needed).
* **CLI support**: the existing CLI auto-discovers commands; `act` works there too.

**Acceptance:** `scripts/cli.py act --message "roll 2d6+3"` invokes planner then `/roll`.

---

### Phase 4: Milestone 5 — Guardrails & allowlists

**Add** a planner allowlist (defense in depth) to `planner.py`:

```python
_ALLOWED = {"roll", "check", "sheet.create", "sheet.show", "do", "ooc"}

def _is_allowed(name: str) -> bool:
    return name in _ALLOWED
```

Update `/act` to enforce `_is_allowed(cmd_name)` before `find_command`.

**Edge cases handled**

* Unknown/made-up tools → error ephemerally.
* Oversized args (reuse existing caps: sheet JSON ≤ 16KB).
* Planner “rationale” never shown in Discord (log only).

**Acceptance:** fuzz messages can’t invoke out-of-policy commands.

---

### Phase 4: Milestone 6 — Telemetry, logs, and sampling

**Add** structured logs (no user PII) in `/act`:

```python
import structlog
log = structlog.get_logger()

# after planning:
log.info("planner.decision",
         cmd=cmd_name,
         confidence=out.plan.confidence,
         rationale=(out.plan.rationale or "")[:120])
```

**Counters** (reuse `metrics.py`):

* `inc_counter("planner.request")`
* `inc_counter("planner.parse_failed")`
* `inc_counter("planner.decision.accepted")`
* `inc_counter("planner.decision.rejected")`

**Acceptance:** visible increments in unit/integration tests.

---

### Phase 4: Milestone 7 — Caching (duplicate suppression)

Mirror the orchestrator cache: **30s** per `(scene_id, user_msg)`.

```python
# planner.py
import time
_CACHE: dict[tuple[int, str], tuple[float, dict]] = {}
_TTL = 30.0

def _cache_get(scene_id: int, msg: str):
    k = (scene_id, msg.strip())
    v = _CACHE.get(k)
    return v[1] if v and (time.time() - v[0]) <= _TTL else None

def _cache_put(scene_id: int, msg: str, plan_json: dict):
    _CACHE[(scene_id, msg.strip())] = (time.time(), plan_json)
```

Call cache in `/act` after we have `scene_id`.

**Acceptance:** repeated `/act` with same text within 30s doesn’t re-prompt LLM.

---

### Phase 4: Milestone 8 — Latency management & fallbacks

* Keep the **DEFERRED (type 5)** flow; `/act` runs in the background.
* Add a **soft timeout** for planning (e.g., 4–6s). If timeout:

  * Fallback: route to `/roll 1d20` (or a friendly “couldn’t decide”).
  * Or: send ephemeral error; do **not** drop silently.

**Acceptance:** chaos test—artificially delay LLM; app still returns a useful message.

---

### Phase 4: Milestone 9 — Tests

**Unit**

* `planner_schemas` validates strict shapes.
* `planner.plan()` parses valid JSON, rejects non-JSON.
* Allowlist enforces policy.

**Integration**

* Mock `LLMClient` to return plans for:

  * roll/check/sheet.create/sheet.show/do/ooc
  * bad tool name (“bananas”) → error
  * bad args (wrong type) → error

**E2E (optional)**

* Spin SQLite aiosqlite; hit `/act` via CLI and ensure transcripts written, handlers invoked.

**Acceptance:** tests cover happy paths + failures; no DB leaks.

---

### Phase 4: Milestone 10 — Safety knobs

* **Rate limit per user** (simple memory counter; reset per minute).
* **Args sanitation**: truncate user-visible echoes; keep system logs full.
* **LLM visibility**: `/act` should respect `features_llm_visible` like `/ooc` does if it ultimately calls the narrator path.

**Acceptance:** load test shows graceful degradation, not spam.

---

### Phase 4: Milestone 11 — Observability & ops

* Add a `/healthz` (if we keep FastAPI public) to assert DB + command registry load.
* A minimal **/metrics** dump (`metrics.get_counter`) gated behind an env flag for local ops.

**Acceptance:** health and counters verifiable in staging.

---

### Phase 4: Milestone 12 — Rollout plan

1. **Shadow** in a dev guild:

   * Enable `features_llm=True` and **keep** `features_llm_visible=False` initially.
   * Exercise `/act` with varied prompts; compare with manual `/roll`, `/check`, `/do`.
2. **Canary**:

   * Enable in 1 production guild with low traffic.
   * Watch `planner.parse_failed` & `planner.decision.rejected` rates and latency.
3. **General availability**:

   * Document `/act` usage and examples.
   * Keep an env flag `FEATURE_PLANNER_ENABLED` (boolean) so we can hard-disable without redeploy.

**Rollback:** toggle `FEATURE_PLANNER_ENABLED=False`; `/act` returns an ephemeral “disabled” message while other commands continue working.

---

### Phase 4: User experience (copy-ready examples)

* `/act "roll 2d6+3 for damage"` → **routes to** `/roll --expr 2d6+3`
* `/act "make a dexterity check against DC 15"` → **routes to** `/check --ability DEX --dc 15`
* `/act "create a character named Aria the rogue"` → **routes to** `/sheet create --json '{...}'` (if we support templating) or returns a helpful error telling user to paste JSON
* `/act "I sneak along the wall, quiet as a cat"` → **routes to** `/do --message "..."`

  * Orchestration runs; if `features_llm_visible=True`, user sees **Mechanics + Narration**.

---

### Phase 4: Security & abuse considerations

* **No direct tool execution**: planner can only choose from `_ALLOWED` and **must** pass `option_model` validation.
* **Ephemeral errors**: never leak raw exception traces to users.
* **Input bounds**: continue enforcing size caps (sheet JSON ≤16KB; message length cap if needed).
* **Logging**: log planner decisions with confidence + truncated rationale (≤120 chars). Avoid storing full raw prompts unless needed for debugging (and gate behind env flag).

---

### Phase 4: Nice-to-haves (later)

* **Disambiguation mode**: if the planner is low confidence (<0.5), ask the user with buttons (“Roll d20” / “Make DEX check vs DC 15?”). This requires Discord components.
* **Few-shot hints**: augment `SYSTEM_PLANNER` with 3–5 examples drawn from real usage to stabilize routing.
* **Per-guild defaults**: allow guilds to opt out of `/act` or restrict which tools it may call.

---

### Phase 4: Done = Done checklist

* [ ] `/act` appears and works in CLI and Discord.
* [ ] Planner allowlist enforced.
* [ ] Option validation errors are user-friendly, ephemeral.
* [ ] Caching prevents duplicate LLM calls.
* [ ] Latency and error metrics recorded.
* [ ] Feature flag to disable planner instantly.
* [ ] E2E happy paths for roll/check/do/sheet.\* pass.

---

## Phase 5 — Initiative & turn engine (synchronous queue) ([#10](https://github.com/crashtestbrandt/Adventorator/issues/10)) — status: open

**Goal:** Combat with strict turn order and timeouts; still minimal rules.

**Deliverables**
* Rules Service v1:
  * Initiative queue; start/end-of-turn hooks
  * Attacks: to-hit vs AC; damage; simple conditions (prone, restrained)
  * HP/resource mutation endpoints
  * Redis locks: per-scene turn lock; TTL-based timeout → auto-Dodge or configured fallback
* Commands/UI:
  * /start-combat (spawns a combat thread)
  * Buttons/selects for common actions; ephemeral per-player panels
* Recovery: if the worker dies mid-turn, lock expiry yields safe fallback

**Exit criteria**
* Concurrency tests (two users act “simultaneously”) don’t break the queue
* Golden log for a canned encounter plays identically across runs

**Rollback**
* ff.combat=false falls back to exploration-only; command returns helpful message.

---

## Phase 6 — Content ingestion & retrieval (memory without hallucinations) ([#11](https://github.com/crashtestbrandt/Adventorator/issues/11)) — status: open

**Goal:** Feed the bot structured adventure info and prior sessions safely.

**Deliverables**
* Ingestion pipeline:
  * Markdown/HTML → normalized nodes (location, npc, encounter, lore)
  * Separate player-facing vs gm-only fields
  * Vector store (pgvector/Qdrant) + retriever with filters (campaign_id, node_type)
* Clerk summarizer job producing neutral session summaries with key_facts, open_threads
* Orchestrator context bundle cap (~8–12k tokens): {current scene node, active PC sheets (pruned), last N turns, house rules} + top-k retrieved

**Exit criteria**
* Retrieval accuracy: spot-check that top-k includes the correct node in canned tests
* No GM-only leaks in player messages (unit test: redaction passes)

**Rollback**
* If vector DB down, fall back to last session summary only.

---

## Phase 7 — Modal solo scenes + merge to combat ([#12](https://github.com/crashtestbrandt/Adventorator/issues/12)) — status: open

**Goal:** Players can act in personal threads; merge to shared combat when needed.

**Deliverables**
* Scene model: {scene_id, participants[], location_node, mode:'exploration'|'combat', clock}
* Merge/branch ops:
  * branch_scene(from, player) → solo thread
  * merge_scenes([ids]) → new combat thread; rebase clocks if you track time
  * Conflict policy: if asynchronous scenes diverge, prompt the human GM to resolve or soft-retcon (configurable)

**Exit criteria**
* Merging two solo scenes into one combat scene keeps initiative & HP correct
* Audit trail shows how/when merges occurred

**Rollback**
* Disable branching: all actions happen in one shared channel.

---

## Phase 8 — GM controls, overrides, & safety tooling ([#13](https://github.com/crashtestbrandt/Adventorator/issues/13)) — status: open

**Goal:** Human-in-the-loop when it matters.

**Deliverables**
* /gm commands (permission-gated): set HP, add/remove condition, modify inventory, end turn, reroll
* Pause & rewind last N mutations (event-sourced ledger → rebuild)
* Lines/Veils & content filters applied to narration
* “Why” panel: include the roll and rule citation the LLM used (from your proposal + rules call)

**Exit criteria**
* Rewind restores pre-change state in ≤1s in test; mutation ledger replays cleanly
* Permissions tested against role IDs

**Rollback**
* GM overrides always available even if LLM/tools are off.

---

## Phase 9 — Hardening & productionization ([#14](https://github.com/crashtestbrandt/Adventorator/issues/14)) — status: open

**Goal:** Operate at small scale without surprises.

**Deliverables**
* Rate limiting per user/channel; exponential backoff on Discord 429s
* Idempotency keys for interactions; safe retry on network flaps
* Circuit breakers per external dependency (LLM, vector DB). Degraded modes:
 * LLM down → rules-only, factual responses
 * Vector DB down → no retrieval, rely on last summary
 * Chaos tests: kill the worker mid-turn; drop the vector DB; random 500s from LLM client
* Cost guards:
 * Token budgeter (hard caps); refusal → ask for shorter actions
 * Cache last narration for identical prompts within 30s (spam control)

**Exit criteria**
* Degraded modes keep the bot usable (no crashes, just reduced features)
* SLOs defined: ack <3s, p95 narration <X sec, error rate <Y%

**Rollback**
* Feature flags per dependency; turn off the breaker to restore normal flow.

---

Notes
- This file is generated from GitHub issues to keep the implementation plan close to source. Update the issues to refresh content.
