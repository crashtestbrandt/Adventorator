# ARCH-CDA-002: Campaign Upload (Discord Admin Flow)

Status: Proposed
Date: 2025-09-27
Owners: Platform/Gameplay
Related:
- CDA-CORE-001 (deterministic event substrate)
- CDA-IMPORT-002 (campaign data import)
- docs/usage/campaign-data.md (Quickstart + tooling)
- Scripts: `scripts/{update_content_index,preflight_import,import_package}.py`

## Motivation

Guild admins should be able to upload a ZIP of campaign content and import it safely without touching the shell. We already have a deterministic, idempotent importer and authoring tools; this feature turns them into an admin-facing workflow in Discord.

## Goals and non-goals

Goals
- Accept a campaign ZIP from a Discord admin and import it into a selected campaign
- Safety: validate archives, avoid path traversal, enforce size/type limits
- Determinism/idempotency: the importer guarantees safe re-runs (manifest-hash short-circuit)
- Observability: stream progress back to the admin and persist a final summary

Non-goals
- Rich content editing in Discord (out of scope)
- Public user uploads (admin-only for now)

## High-level design

Interaction entry point (Discord):
- Slash command (admin-only): `/admin import-campaign`
  - Options: `campaign_id` (int), `archive` (attachment), `embeddings` (bool, default false)
  - Alternative: infer `campaign_id` from guild configuration if omitted

Backend handler:
1) AuthZ: verify invoker is guild admin (role/guild config)
2) Fetch attachment → write to a temp file with streaming (limit size, content-type allowlist)
3) Unpack ZIP into a unique temp directory
   - Strip leading components; reject absolute paths; block `..` traversal (zip-slip prevention)
   - Allow only files under: `entities/`, `edges/`, `ontology/|ontologies/`, `lore/`, and `README.md`
4) Run tooling (in-process equivalents of the scripts)
   - Update manifest hashes: `update_content_index`
   - Preflight DB: `preflight_import` (auto-migrate OFF in prod; return a clear error if missing)
   - Import: trigger the same importer pipeline used by `scripts/import_package.py` (DB-backed)
5) Observability
   - Stream phase transitions and counters to the admin (follow-up updates)
   - On completion, emit a concise summary and link to logs
6) Persistence
   - Store a per-upload summary row (campaign_id, manifest_hash, counts, status, duration, requester)
   - Importer already writes detailed `import_logs`; link them via manifest_hash

## Sequence (textual)

- Admin runs `/admin import-campaign archive=pack.zip campaign_id=1`
- Bot acknowledges, starts job, and posts “validating archive…”
- Server unpacks to a temp dir, runs `update_content_index`, then preflight
- If preflight passes, server runs importer; streams phase updates (entities/edges/ontology/lore/finalization)
- On success: posts final summary with `event_count`, `import_log_count`, `hash_chain_tip`, `idempotent_skip`
- On failure: posts error + first few validation issues (keep payload sizes safe)

## Contracts and inputs

- Input: ZIP archive with a valid `package.manifest.json` and any of: `entities/`, `edges/`, `ontology/|ontologies/`, `lore/`
- Output: seed events in DB, `import_logs` entries, and an admin-visible summary
- Idempotency: if the same canonical manifest is re-uploaded, importer short-circuits

## API and commands

Discord (admin-only):
- `/admin import-campaign`
  - campaign_id: integer (required if not inferred)
  - archive: attachment (required)
  - embeddings: boolean (optional; default false)

Optional status command:
- `/admin import-status` → returns recent uploads + latest result for a campaign

Server endpoints (internal)
- POST `/admin/import/campaign` (multipart) — used by the bot process only
- GET `/admin/import/status?campaign_id=…` — small JSON for the status command

## Security and limits

- AuthN/AuthZ: guild admin verification; reject non-admin callers
- Anti-zip-slip: sanitize all paths; reject absolute or parent-traversal
- Size limits: configurable max ZIP size; reject archives with too many files
- Type allowlist: `.json`, `.md`, `.txt`; block binaries and unexpected types
- Temp dirs: unique per upload; cleaned up after job
- DB migrations: disable auto-migrate in prod; return actionable error if missing

## Observability

- Log structured events for each phase, counters, and import summary
- Stream progress back to the admin with incremental follow-ups (throttled)
- Metrics: counts per phase, durations, success/failure, bytes processed, skipped via idempotency

## Failure modes

- Invalid ZIP or path traversal → reject; post user-facing guidance
- Manifest/content mismatch → surface first N mismatches; advise re-run after fixing
- Missing DB schema (e.g., `import_logs`) → advise running migrations; do not auto-migrate in prod
- Timeouts or large archives → fail gracefully and leave a job trace

## Config and flags

- Feature flags: `features.importer` must be true; `features.importer_embeddings` mirrors `embeddings` option
- Upload size/timeouts: per-environment limits
- Storage paths: temp root for unpacking; retention policy for uploaded archives (default: delete after import)

## Implementation notes

- Use existing importer code (as exercised by `scripts/import_package.py`) and `package_utils.update_content_index`
- Use existing logging helpers to emit structured events; prefer the same event names used during CLI imports
- Follow the command registry decorators and responder abstraction when adding the new slash command
- Do not introduce new external dependencies for ZIP handling; standard library `zipfile` + strict validation is sufficient

## Rollout plan

- Dev: behind a feature flag; test with small archives; validate idempotency skip on re-upload
- Staging: increase size limits; run through destructive/edge-case tests (bad ZIPs, huge file counts)
- Prod: enable for selected guilds; monitor metrics and log rates

## Acceptance criteria

- A Discord admin can upload a ZIP and see streaming progress and a final summary
- The upload is validated, unpacked safely, and imported into the target campaign
- Results are persisted and visible via `/admin import-status`
- Re-upload of identical content is idempotent (no duplicate seed events)

## Open questions

- Campaign selection UX: infer from guild or require explicit `campaign_id`?
- Do we allow “create new campaign” from the command (name + auto-ID)?
- Where to persist per-upload summaries (new table vs. reuse `import_logs` with synthetic entries)?
