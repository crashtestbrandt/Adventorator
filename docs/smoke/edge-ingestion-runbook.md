# Smoke Runbook — Edge ingestion & temporal validity (STORY-CDA-IMPORT-002C)

This runbook verifies the edge ingestion pipeline on a fresh branch before promoting changes.

## Prerequisites
- Python 3.12+
- `git`
- `make`

## Environment setup
1. Clone the repository and checkout the feature branch:
   ```bash
   git clone <repo-url>
   cd Adventorator
   git checkout <feature-branch>
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install tooling dependencies:
   ```bash
   pip install -r requirements.txt
   pip install jsonschema types-jsonschema
   ```

## Validation steps
1. **Lint & formatting** — ensure code style and contract formatting are clean:
   ```bash
   make format
   make lint
   ```
2. **Static typing** — confirm the importer and manifest helpers type-check:
   ```bash
   make type
   ```
3. **Targeted importer tests** — run only the new edge ingestion suites for quick feedback:
   ```bash
   pytest tests/importer/test_edge_parser.py \
          tests/importer/test_edge_seed_events.py \
          tests/importer/test_edge_metrics.py
   ```
4. **End-to-end regression** — execute the full manifest→entity→edge workflow and existing importer suites:
   ```bash
   make test
   ```
   _Expected outcome:_ 379 tests pass, 5 skipped, 0 failures (warnings about `pytest.mark.slow` are acceptable).
5. **Manual artifact inspection** — optional but recommended:
   - Open `contracts/edges/edge.v1.json` and verify taxonomy-aligned edge types.
   - Inspect `docs/implementation/stories/STORY-CDA-IMPORT-002C-edge-ingestion.md` for the DoR/DoD analysis update.

## Rollback guidance
If any step fails:
- Record the failing command output.
- Restore the working tree via `git reset --hard HEAD` to drop local modifications.
- Re-run the failing command after addressing the root cause (e.g., missing dependency, schema mismatch).
- If the branch becomes unrecoverable, create a new branch from `main` and cherry-pick validated commits.

## Sign-off checklist
- [ ] `make format`
- [ ] `make lint`
- [ ] `make type`
- [ ] `make test`
- [ ] Edge smoke tests inspected (parser, events, metrics)

