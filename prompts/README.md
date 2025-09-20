# Prompt Registry

The AIDD pipeline expects all AI prompt assets to be versioned and traceable. This directory is the canonical registry for Adventorator prompts.

## Structure
- Organize prompts by capability or feature, e.g., `encounter/`, `narrative/`.
- Store prompts as Markdown or JSON files with semantic version tags in the filename (for example, `planner-v1.md`).
- Include metadata blocks describing owner, intended model, guardrails, and evaluation coverage.

## Workflow Integration
- Reference prompt files from Tasks in the prompt registry checklist.
- Update version numbers whenever the prompt behavior changes in a non-backward-compatible way.
- Link prompts to their validating tests or evaluation harnesses to enable automated quality gates in later phases.
