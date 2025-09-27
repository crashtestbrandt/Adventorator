# Encounters (Dev Notes)

Phase 10 introduces basic encounter tracking and initiative order display. These notes describe the current state and may be superseded by future architectural decisions and ADRs.

- Feature flag: enable combat via either of the following in `config.toml`:
  - Preferred: `[combat].enabled = true`
  - Legacy fallback: `[features].combat = true`
- Command: `/encounter status` shows current round, active combatant indicator, and the initiative order for the active scene.
- Output includes an arrow on the active combatant and lists initiative values. Use `--verbose` to include internal IDs.

## Seeding an Example Encounter

For quick demos, a helper script seeds combatants into the current scene:

- Make target: `make seed-encounter`
  - This runs `scripts/seed_encounter.py` with `PYTHONPATH=./src`.
  - Ensure your DB is initialized (e.g., `make db-upgrade`) and the server is running.

## Notes

- The command is FF-gated: you must enable combat features for it to appear.
- The status view is read-only. Turn progression and mutation commands will arrive in a later phase.
- Deterministic ordering is handled in `repos.sort_initiative_order`.
