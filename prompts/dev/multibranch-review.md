---
id: PROMPT-MULTIBRANCH-REVIEW
version: 1
author: Brandt
purpose: TODO
---

Context
- Repo root: {REPO_ROOT}
- Active branch (do not modify): {ACTIVE_BRANCH}
- Story: {STORY_ID} — {STORY_TITLE}
- Story file: {STORY_FILE_PATH}

Constraints
- SAFE_MODE: {SAFE_MODE_TRUE_FALSE} (if true, do not modify any refs; analysis only).
- PATCH_OK: {PATCH_OK_TRUE_FALSE} (if true, allowed to edit only the chosen worktree/branch; never touch {ACTIVE_BRANCH}).
- License headers: If editing any file with a license header, preserve it exactly and warn in the reply (AGENTS.md compliance).

Branches to review (read-only unless PATCH_OK=true)
- Baseline for diff: {BASELINE_BRANCH}
- Candidate branches: {BRANCH_REFS_COMMA_SEPARATED}

Acceptance criteria (AC) to validate for this story are listed in the provided Story file.

Relevant Contract/architecture refs are contained in the provided Story file.

Agent actions requested
1) Fetch refs and create detached Git worktrees for each candidate branch under `.worktrees`.
2) For each branch:
   - Show diff summary vs {BASELINE_BRANCH} limited to {DIFF_SCOPE}.
   - Open and validate contract files against relevant AC, Contracts, Architecture, Epic(s), etc.
   - Run setup commands and tests. Capture pass/fail and key assertions (e.g., schema/mutation signatures).
   - Note any policy directives and unintended schema churn.
3) Produce a pass/gap matrix per branch against AC.
4) Recommend the best base branch with rationale (AC coverage, structure, minimal diff, docs/tests present).
5) If PATCH_OK=true:
   - Propose minimal, surgical patch plan to close gaps (no unrelated changes).
   - Apply in the chosen worktree on a new topic branch: {TOPIC_BRANCH_NAME_TEMPLATE}.
   - Re-run tests and report.
   - Push the topic branch and generate a concise PR summary.
6) Cleanup commands to remove worktrees safely.

Expected output
- For each branch:
  - Diff summary (top files)
  - Contract verification (key signatures/types)
  - Test results (counts, failures)
  - AC compliance (Pass/Gap with notes)
  - Risks or unrelated churn
- Overall:
  - Recommendation of best base branch
  - Minimal patch plan (if PATCH_OK=true)
  - Ready-to-paste PR summary
  - Cleanup instructions (git worktree remove/prune)

Example commands (Linux)
- Add worktrees:
  - git worktree add --detach {WORKTREES_DIR}/A {REF_A}
  - git worktree add --detach {WORKTREES_DIR}/B {REF_B}
- Per worktree:
  - git --no-pager diff --name-status {BASELINE_BRANCH}..{REF}
  - cd {WORKTREES_DIR}/{ALIAS}/{TEST_PKG_PATH} && {PREP_CMDS_CHAIN} && {TEST_CMD}
- Cleanup:
  - git worktree remove {WORKTREES_DIR}/{ALIAS}
  - git worktree prune

Please begin the analysis and confirm SAFE_MODE/PATCH_OK interpretation before making any modifications.
