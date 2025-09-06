## Phase 3 — LLM “narrator” in shadow mode ([#9](https://github.com/crashtestbrandt/Adventorator/issues/9)) — status: open

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

## assumptions

- Feature flag `[features].llm` already gates LLM usage (default off).
- Use current llm.py (httpx) and transcripts in DB; do not add migrations.
- Commands go through app.py and `responder.followup_message()`.

## milestone 0 — scaffolding and safety (1 PR)

- Add pydantic models to `schemas.py`:
  - LLMProposal(action: Literal[…], ability: Literal[STR, DEX, …], suggested_dc: int, reason: str)
  - LLMNarration(narration: str)
  - LLMOutput(proposal: LLMProposal, narration: str)
- Guard helpers in llm.py or new `llm_utils.py`:
  - extract_first_json(text) → dict | None (strict JSON scan, size caps).
  - validate_llm_output(dict) → LLMOutput | None.
- Config caps in config.toml/Settings: max_prompt_tokens, max_response_chars.
- Tests:
  - JSON extraction/validation happy/invalid paths.
  - Settings precedence sanity (already added).
- Acceptance:
  - parse/validate works; invalid JSON yields None; feature flag off by default.

## milestone 1 — “fact clerk” prompt builder (branch: 42-p3-fact-clerk) (1–2 PRs)

- Module `src/Adventorator/llm_prompts.py`:
  - build_clerk_messages(transcripts[…], player_msg) → List[{"role","content"}]
    - Extracts recent N turns, compact summaries; trims to token cap.
- Repo helper in `repos.py`:
  - get_recent_transcripts(scene_id, limit=50) returning minimal rows for prompts.
- Tests:
  - Prompt includes last N turns, excludes GM-only/system content, respects length caps.
- Acceptance:
  - Deterministic prompt assembly for given fixture; snapshot test.

## milestone 2 — narrator prompt and JSON mode (1 PR)

- In `llm_prompts.py`:
  - build_narrator_messages(facts_bundle, player_msg) → messages with strict JSON-only instructions (no prose outside JSON).
  - System prompt enforces schema and enumerations; forbid unknown actors.
- Update llm.py client:
  - Add generate_json(messages) → dict | None (no prose; parse; validate against LLMOutput).
  - Timeouts and None on failure; log structured diagnostics (truncate).
- Tests:
  - Mocked httpx response with valid JSON returns LLMOutput.
  - Non-JSON/prose returns None.
- Acceptance:
  - End-to-end prompt → parse works with mocks; no state mutation.

## milestone 3 — orchestrator (1–2 PRs)

- New `src/Adventorator/orchestrator.py`:
  - plan:
    - fetch transcripts → facts via clerk prompt (optional log-only)
    - run narrator → LLMOutput
    - map proposal → rules request using `rules/checks.py`
    - compute mechanics (roll d20 w/adv/dis if indicated; use suggested_dc)
    - format mechanics block + narration stringgit pull
  - Reject if:
    - action/ability not in whitelist, DC out of range (e.g., 5–30), unknown actors, or missing required fields.
- Tests:
  - Given a fixed LLMOutput and dice seed, mechanics format matches expected.
  - Rejection paths yield safe, helpful message.
- Acceptance:
  - Orchestrator can run fully with mocked LLM, produces message blocks.

## milestone 4 — wire into /ooc shadow path (1 PR)

- In `app.py`:
  - For `/ooc`, if `features_llm`:
    - Defer.
    - Call orchestrator with scene/player context.
    - Post mechanics + narration follow-up.
    - Log bot transcript.
  - If LLM returns None/invalid → post polite ephemeral fallback and still log player transcript.
- Tests (async):
  - Interaction e2e with mocked LLM: follow-up payload contains mechanics and narration; no DB mutations (beyond transcripts).
  - Degraded path: None/timeout leads to ephemeral fallback.
- Acceptance:
  - Under 3s for defer; visible shadow output; no state changes.

## milestone 5 — prompt-injection defenses (1 PR)

- Enforce:
  - Max tokens/length on inputs/outputs; strip system text in user inputs.
  - Whitelisted tools/actions; reject references to unknown actors/items.
  - Disallow “change HP/inventory” verbs in proposal.
- Tests:
  - Inputs containing system leakage or tool misuse are rejected/neutralized.
- Acceptance:
  - Defense tests pass; orchestrator returns safe message on violations.

## milestone 6 — observability and budgets (1 PR)

- Logging: structlog events:
  - llm.request.enqueued, llm.response.received, llm.parse.failed, llm.defense.rejected, orchestrator.format.sent
- Metrics (simple counters/timers): requests, timeouts, parse_fail, defense_reject, shadow_visible.
- Cost guards:
  - Token budget caps; rate-limit identical prompts (e.g., 30s cache).
- Acceptance:
  - Logs visible with correlation IDs; counters increment in tests (or via a small hookable metrics shim).

## milestone 7 — rollout toggles and docs (1 PR)

- Sub-flag: `[features].llm_visible`:
  - false → log-only (shadow), true → post to Discord.
- Docs:
  - README/usage note; config.toml example and .env keys.
  - Copilot instructions: add narrator/clerk pointers (kept concise).
- Acceptance:
  - Toggling flag flips between log-only vs visible without deploy changes.

## risks and mitigations

- JSON drift/hallucination: enforce strict system prompt; validate and reject; degrade gracefully.
- Long responses/timeouts: low temperature for clerk; moderate for narrator; short timeout with fallback.
- Unknown actors/leaks: whitelist participants from scene; strip/verify.
- CI flakiness due to external LLM: mock httpx; keep external test disabled in CI.

## definition of done (maps to Phase 3 exit criteria)

- LLM visible only when `[features].llm` and `[features].llm_visible` are true.
- No DB mutations from LLM path; tests enforce.
- Manual spot-checks show ≥90% sensible proposals on a few canned transcripts.
- Degraded mode yields safe responses; no crashes.
- Structured logs and counters in place.

## suggested PR sequence

1) Schemas + JSON parsing + tests
2) Clerk prompt builder + tests
3) Narrator prompt + generate_json + tests
4) Orchestrator core + tests
5) /ooc integration (shadow visible gated) + interaction tests
6) Defenses + tests
7) Observability + docs + toggles

Each PR should be small, self-contained, and maintain green tests with `[features].llm=false` by default.