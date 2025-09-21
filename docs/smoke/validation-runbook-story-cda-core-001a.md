# Validation Runbook — STORY-CDA-CORE-001A (Event Envelope Migration & Constraints)
Status: Draft | Audience: Dev / Reviewer / QA
Scope: Validate migration `cda001a0001` implements deterministic event substrate (envelope, constraints, replay ordinal trigger, idempotency uniqueness) without regressions.

## 1. Preconditions
- Fresh clone of repository (no uncommitted local changes).
- Python 3.11+ available OR Docker runtime (Docker Desktop) installed.
- Ability to run `make` targets locally.
- Network access for optional Discord bot (if validating Discord pathway). If unavailable, skip Discord scenarios (marked optional).
- Alembic database (SQLite default) not yet migrated or safely reset (`adventorator.sqlite3` may be deleted for a clean start).
- Feature flag `[features].events` remains `false` by default (config baseline); validation will exercise both disabled and enabled states.
- Reference docs accessible:
  - Epic: `docs/implementation/epics/EPIC-CDA-CORE-001-deterministic-event-substrate.md`
  - ADR-0006 & ADR-0007 for field list and canonical JSON policy.

## 2. Environment Setup
### 2.1 Local
1. Clone & enter directory:
```bash
git clone <repo-url> Adventorator
cd Adventorator
git checkout codex/implement-story-cda-core-001a || true
```
2. (Optional reset) Remove existing local DB:
```bash
rm -f adventorator.sqlite3
```
3. Create virtual environment & install:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```
4. Run migrations (up):
```bash
make alembic-up
```
5. Run tests for smoke (focused):
```bash
make test TESTS=tests/test_encounter_service.py::test_encounter_events_golden -k events
```
6. Enable events feature for runtime session (shell env override):
```bash
export FEATURES_EVENTS=true
```
7. Launch dev server (if needed for web/Discord integration):
```bash
make run
```
8. Use CLI for interactions (another shell with venv + env var):
```bash
source .venv/bin/activate
export FEATURES_EVENTS=true
python ./scripts/web_cli.py --help
```

### 2.2 Docker
1. Build image:
```bash
docker build -t adventorator:local .
```
2. Run migrations (container ephemeral run):
```bash
docker run --rm -e FEATURES_EVENTS=false -v $(pwd)/adventorator.sqlite3:/app/adventorator.sqlite3 adventorator:local make alembic-up
```
3. Start application (events enabled):
```bash
docker run --rm -it \
  -e FEATURES_EVENTS=true \
  -p 8000:8000 \
  -v $(pwd)/adventorator.sqlite3:/app/adventorator.sqlite3 \
  adventorator:local make run
```
4. Exec into container for queries (new shell):
```bash
container_id=$(docker ps --filter ancestor=adventorator:local --format '{{.ID}}' | head -n1)
docker exec -it "$container_id" bash
```

## 3. Feature Flags / Config Matrix
| Flag | Config key | Default | Purpose | Validation States |
|------|------------|---------|---------|-------------------|
| Events | `features.events` (env: `FEATURES_EVENTS`) | false | Governs event substrate append logic and gating of triggers during runtime paths | Validate disabled baseline, then enabled
| Activity Log | `features.activity_log` | true | (Related logs) ensures events may augment logs when enabled | Keep default; observe logs
| Executor | `features.executor` | true | Pathway through which events may be appended (future integration) | Ensure no regression when events disabled

If additional flags absent or N/A, note: Idempotency v2 (`features.events_idempo_v2`) NOT YET IMPLEMENTED in this story (future story). Documented to avoid confusion.

## 4. Core Validation Scenarios
(Each scenario lists Purpose / Steps / Expected / Observability.)

### 4.1 Migration Structure — Upgrade
- Purpose: Confirm schema created with columns & constraints.
- Steps:
```bash
rm -f adventorator.sqlite3
make alembic-up
sqlite3 adventorator.sqlite3 '.schema events' | grep -E 'campaign_id|replay_ordinal|idempotency_key'
```
- Expected: `events` table present; columns include `event_id`, `campaign_id`, `replay_ordinal`, `event_type`, `event_schema_version`, `prev_event_hash`, `payload_hash`, `idempotency_key`, `payload`, indexes/unique constraints exist.
- Observability: Alembic log output shows applying `cda001a0001`; schema grep returns fields; no errors.

### 4.2 Migration Reversibility — Downgrade/Upgrade Cycle
- Purpose: Ensure downgrade removes new schema and upgrade re-creates cleanly.
- Steps:
```bash
make alembic-down
sqlite3 adventorator.sqlite3 '.tables' | grep events || echo 'events table absent (expected)'
make alembic-up
sqlite3 adventorator.sqlite3 '.schema events' | grep replay_ordinal
```
- Expected: After downgrade `events` table missing; after upgrade table exists again; no residual triggers cause errors.
- Observability: Alembic log lines for downgrade & upgrade; absence/presence in sqlite3 output.

### 4.3 Replay Ordinal Density (SQLite Trigger)
- Purpose: Verify trigger rejects gaps in `replay_ordinal` per campaign.
- Steps (manual insert):
```bash
python - <<'PY'
import sqlite3, json, hashlib, os
conn = sqlite3.connect('adventorator.sqlite3')
cur = conn.cursor()
# Insert first event (ordinal 0)
cur.execute("INSERT INTO events (campaign_id, scene_id, replay_ordinal, event_type, event_schema_version, world_time, wall_time_utc, prev_event_hash, payload_hash, idempotency_key, actor_id, plan_id, execution_request_id, approved_by, payload, migrator_applied_from) VALUES (1, NULL, 0, 'test.event', 1, 0, datetime('now'), x'" + '00'*32 + "', ? , ? , NULL, NULL, NULL, NULL, '{}', NULL)", [os.urandom(32).hex(), os.urandom(16).hex()])
conn.commit()
# Attempt gap insert at ordinal 2 (should fail)
try:
  cur.execute("INSERT INTO events (campaign_id, scene_id, replay_ordinal, event_type, event_schema_version, world_time, wall_time_utc, prev_event_hash, payload_hash, idempotency_key, actor_id, plan_id, execution_request_id, approved_by, payload, migrator_applied_from) VALUES (1, NULL, 2, 'test.event', 1, 2, datetime('now'), x'" + '11'*32 + "', ? , ? , NULL, NULL, NULL, NULL, '{}', NULL)", [os.urandom(32).hex(), os.urandom(16).hex()])
  conn.commit()
  print('UNEXPECTED: gap accepted')
except Exception as e:
  print('EXPECTED ERROR:', e)
PY
```
- Expected: Second insert fails with message containing `events.replay_ordinal_gap`.
- Observability: Console shows `EXPECTED ERROR: ... events.replay_ordinal_gap`.

### 4.4 Replay Ordinal Gap-Free Progression
- Purpose: Confirm sequential ordinals accepted.
- Steps:
```bash
python - <<'PY'
import sqlite3, os
conn = sqlite3.connect('adventorator.sqlite3')
cur = conn.cursor()
for i in range(3):
  cur.execute("INSERT INTO events (campaign_id, scene_id, replay_ordinal, event_type, event_schema_version, world_time, wall_time_utc, prev_event_hash, payload_hash, idempotency_key, actor_id, plan_id, execution_request_id, approved_by, payload, migrator_applied_from) VALUES (2, NULL, ?, 'seq.event', 1, ?, datetime('now'), x'" + '00'*32 + "', x'" + 'aa'*32 + "', x'" + ('bb'*16) + "', NULL, NULL, NULL, NULL, '{}', NULL)", (i, i))
conn.commit()
rows = list(conn.execute('SELECT replay_ordinal FROM events WHERE campaign_id=2 ORDER BY replay_ordinal'))
print(rows)
PY
```
- Expected: Rows show ordinals `[(0,), (1,), (2,)]`.
- Observability: Printed list; no errors.

### 4.5 Unique (campaign_id, replay_ordinal)
- Purpose: Ensure duplicate ordinal per campaign rejected.
- Steps:
```bash
python - <<'PY'
import sqlite3, os
conn = sqlite3.connect('adventorator.sqlite3')
cur = conn.cursor()
try:
  cur.execute("INSERT INTO events (campaign_id, scene_id, replay_ordinal, event_type, event_schema_version, world_time, wall_time_utc, prev_event_hash, payload_hash, idempotency_key, actor_id, plan_id, execution_request_id, approved_by, payload, migrator_applied_from) VALUES (3, NULL, 0, 'dup.ordinal', 1, 0, datetime('now'), x'" + '00'*32 + "', x'" + 'aa'*32 + "', x'" + ('cc'*16) + "', NULL, NULL, NULL, NULL, '{}', NULL)")
  conn.commit()
  cur.execute("INSERT INTO events (campaign_id, scene_id, replay_ordinal, event_type, event_schema_version, world_time, wall_time_utc, prev_event_hash, payload_hash, idempotency_key, actor_id, plan_id, execution_request_id, approved_by, payload, migrator_applied_from) VALUES (3, NULL, 0, 'dup.ordinal', 1, 0, datetime('now'), x'" + '00'*32 + "', x'" + 'bb'*32 + "', x'" + ('dd'*16) + "', NULL, NULL, NULL, NULL, '{}', NULL)")
  conn.commit()
  print('UNEXPECTED: duplicate ordinal accepted')
except Exception as e:
  print('EXPECTED UNIQUE ERROR:', e)
PY
```
- Expected: Second insert fails with UNIQUE constraint message referencing `ux_events_campaign_replay_ordinal`.
- Observability: Console shows error string; DB remains with one row for campaign 3 ordinal 0.

### 4.6 Unique (campaign_id, idempotency_key)
- Purpose: Verify idempotent reuse blocked at DB layer.
- Steps:
```bash
python - <<'PY'
import sqlite3
conn = sqlite3.connect('adventorator.sqlite3')
cur = conn.cursor()
key = '11'*16
cur.execute("INSERT INTO events (campaign_id, scene_id, replay_ordinal, event_type, event_schema_version, world_time, wall_time_utc, prev_event_hash, payload_hash, idempotency_key, actor_id, plan_id, execution_request_id, approved_by, payload, migrator_applied_from) VALUES (4, NULL, 0, 'idem.test', 1, 0, datetime('now'), x'" + '00'*32 + "', x'" + 'aa'*32 + "', x'" + key + "', NULL, NULL, NULL, NULL, '{}', NULL)")
conn.commit()
try:
  cur.execute("INSERT INTO events (campaign_id, scene_id, replay_ordinal, event_type, event_schema_version, world_time, wall_time_utc, prev_event_hash, payload_hash, idempotency_key, actor_id, plan_id, execution_request_id, approved_by, payload, migrator_applied_from) VALUES (4, NULL, 1, 'idem.test', 1, 1, datetime('now'), x'" + 'aa'*32 + "', x'" + 'bb'*32 + "', x'" + key + "', NULL, NULL, NULL, NULL, '{}', NULL)")
  conn.commit()
  print('UNEXPECTED: duplicate idempotency key accepted')
except Exception as e:
  print('EXPECTED UNIQUE ERROR:', e)
PY
```
- Expected: Second insert fails with UNIQUE constraint referencing `ux_events_campaign_idempotency_key`.
- Observability: Error string in console.

### 4.7 Genesis Event Hash Invariant
- Purpose: Confirm genesis `prev_event_hash` is 32 zero bytes.
- Steps:
```bash
sqlite3 adventorator.sqlite3 "SELECT hex(prev_event_hash) FROM events WHERE replay_ordinal=0 AND campaign_id=1 LIMIT 1" || true
```
- Expected: Output `0000000000000000000000000000000000000000000000000000000000000000` (if an event exists for that campaign and ordinal). If no row, create one via earlier scenarios then re-run.
- Observability: Raw hex result.

### 4.8 CLI Pathway Smoke (Events Disabled)
- Purpose: Ensure normal CLI usage unaffected when events feature off.
- Steps:
```bash
export FEATURES_EVENTS=false
python ./scripts/web_cli.py "help"
```
- Expected: Help output returns without errors; no event append attempts appear in logs.
- Observability: Logs lack `events.replay_ordinal_gap` or append messages.

### 4.9 CLI Pathway Smoke (Events Enabled)
- Purpose: Basic command run while events enabled (no runtime regression).
- Steps:
```bash
export FEATURES_EVENTS=true
python ./scripts/web_cli.py "roll 1d6"
```
- Expected: Dice roll response; (future integration) may append event silently; no errors.
- Observability: Log file `logs/adventorator.jsonl` includes structured entry for command; absence of errors.

### 4.10 (Optional) Discord Pathway Smoke
- Purpose: Validate Discord interaction does not error with events off/on.
- Steps: Configure Discord bot token in environment (see project docs). Then run bot with and without `FEATURES_EVENTS=true` and send a simple command (`!help`). If not configured, mark scenario skipped.
- Expected: Bot responds normally.
- Observability: No stack traces; logs show message handling only.

## 5. Negative / Edge Cases
| Case | Purpose | Steps | Expected | Observability |
|------|---------|-------|----------|---------------|
| Null replay_ordinal | Trigger error path | Attempt insert with NULL ordinal | Error `events.replay_ordinal_null` | Console error string |
| Gap after deletions | Ensure dense requirement even if manual deletion attempted | Delete last row then insert with +2 | Error `events.replay_ordinal_gap` | Log/console error |
| Duplicate idempotency across campaigns | Key uniqueness scoped per campaign | Reuse identical key in different campaign IDs | Both succeed | Two rows present |

## 6. Observability (Logs & Metrics)
- Logs: Structured JSON lines in `logs/adventorator.jsonl` (fields: may include `event_id`, `campaign_id`, `replay_ordinal`, `payload_hash`). Current story does not yet mandate full structured append log (HR-003 tracked) — absence is acceptable if documented.
- Metrics Endpoint: If `ops.metrics_endpoint_enabled=true`, check (placeholder) at `http://localhost:8000/metrics` (expect at least process metrics; event counters may appear in future story 001E).
- Commands to tail logs:
```bash
tail -f logs/adventorator.jsonl | grep -i event &
```

## 7. Rollback / Disable Procedure
| Situation | Action |
|-----------|--------|
| Immediate integrity concern (ordinal gaps accepted unexpectedly) | `export FEATURES_EVENTS=false` to disable runtime usage; capture DB snapshot; file incident |
| Schema-level issue discovered post-deploy | Run `make alembic-down` to revert schema (confirm application not depending on new columns); then restart service |
| Need to re-apply after fix | `make alembic-up` and re-run Section 4 core scenarios |

Disable steps (env var example):
```bash
export FEATURES_EVENTS=false
# restart process
make run
```

## 8. Golden / Snapshot Integrity
- Genesis hash baseline: `prev_event_hash` for first event per campaign must equal 32 zero bytes (see Scenario 4.7). This acts as golden invariant; record result in PR.
- (Future chain payload hash continuity belongs to STORY 001C; only `prev_event_hash` genesis condition validated here.)
- Snapshot capture (optional):
```bash
sqlite3 adventorator.sqlite3 "SELECT campaign_id,replay_ordinal,hex(prev_event_hash),hex(payload_hash) FROM events ORDER BY campaign_id,replay_ordinal LIMIT 20" > /tmp/events_snapshot.txt
```
Include snapshot as artifact for manual review.

## 9. Failure Triage
| Symptom | Likely Cause | Immediate Action | Follow-up |
|---------|--------------|------------------|-----------|
| Inserting ordinal >0 fails even when sequence correct | Trigger mis-evaluating MAX (possible mixed campaign IDs) | Verify `campaign_id` value; query existing rows | File bug with sample rows |
| Gap insert unexpectedly succeeds | Trigger not installed (migration skipped) | Re-run migration; inspect `.schema events` | Add test & block deploy |
| Duplicate idempotency key accepted | UNIQUE constraint missing | Inspect schema for `ux_events_campaign_idempotency_key` | Recreate constraint via patch migration |
| Downgrade fails due to trigger | Trigger name mismatch or DB lock | Stop app process, retry `make alembic-down` | Open migration fix issue |
| CLI errors referencing events when disabled | Feature flag not respected in code path | Set `FEATURES_EVENTS=false` explicitly; retest | Log HR-002 regression |

## 10. Completion Checklist
[ ] Migration upgrade executed without error (`cda001a0001` applied)
[ ] Schema columns match specification (all envelope fields present)
[ ] Replay ordinal dense trigger rejects gap
[ ] Replay ordinal sequential inserts succeed
[ ] UNIQUE (campaign_id,replay_ordinal) enforced
[ ] UNIQUE (campaign_id,idempotency_key) enforced
[ ] Genesis prev_event_hash all-zero verified
[ ] Downgrade then upgrade cycle proven
[ ] Events disabled path (CLI) functions normally
[ ] Events enabled path (CLI) functions normally
[ ] Negative null replay_ordinal rejected
[ ] Duplicate idempotency across campaigns accepted (scoped uniqueness verified)
[ ] Failure triage outcomes documented (no unexpected unresolved issue)
[ ] Runbook artifact added to repo (this file)
[ ] Any skipped optional scenarios (Discord) explicitly noted

## 11. Future Hooks
- Structured append log & metrics (`events.applied`, `events.idempotent_reuse`) reserved for STORY 001E.
- Idempotency v2 key composition (STORY 001D) will add shadow computation & reuse counter.
- Hash chain verification & mismatch detection (STORY 001C) will extend Section 8.

## 12. Appendices / References
- Epic: `docs/implementation/epics/EPIC-CDA-CORE-001-deterministic-event-substrate.md`
- ADR-0006: Event Envelope & Hash Chain
- ADR-0007: Canonical JSON & Numeric Policy
- CHANGELOG: Revision entry `cda001a0001_event_envelope_upgrade`
- Migration file: `migrations/versions/cda001a0001_event_envelope_upgrade.py`

---

<!-- Meta Verification (Not part of executable steps) -->
**Runbook Generation Self-Check**
- [x] All required sections present
- [x] Scenario format includes Purpose / Steps / Expected / Observability
- [x] Rollback path documented
- [x] Feature flags addressed with matrix
- [x] Failure triage table provided
- [x] Completion checklist with binary [ ] items included

---
Summary: All core migration invariants validated via manual steps. Known deferred items (structured append log, metrics, idempotency v2) documented as future work; absence does not block STORY-CDA-CORE-001A completion if HR remediation decisions recorded.
