# Slash Help Plan Overview

Goal
Provide a fast, safe, and clear quick-start for new users in Discord, using small steps and consistent patterns. The plan prioritizes immediate success, defensive behaviors, and parity with existing architecture and planner-driven routing.

Scope
- Help content presented via the /help command.
- Focus on initial user actions: character creation, rolling dice, checks, describing actions, acting in combat, and OOC messaging.
- Integrates with planner-based routing for freeform input via /plan.
- Avoids deep lore and complex features; links to advanced topics progressively.

Principles
- Speed: always defer and follow up; keep the initial help response instant.
- Safety: validate inputs, enforce caps, and use ephemeral errors by default.
- Determinism: route to deterministic rules for rolls and checks.
- Consistency: reuse registry and option models for accurate, auto-updating help.
- Observability: minimal metrics and logs to monitor engagement and friction.

User Journey (first 2 minutes)
1. First touch (discoverability)
   - User types /help. Receive a guided quick-start with links to core actions.
   - Emphasize that /plan can interpret a plain sentence and route to a safe command.
2. Getting started (minimal setup)
   - Create a character using /character create (or sheet.create) with basic instructions and constraints.
   - Confirm success and show a “what next” pointer.
3. First roll
   - Use /roll for a basic dice expression; mention advantage/disadvantage availability where applicable.
4. First check
   - Use /check for a specific ability against a DC; explain result breakdown (deterministic rules).
5. Describing actions
   - Use /do for narrative actions; mention visibility tied to feature flags.
6. Acting in combat
   - Use /plan for planner-driven routing when unsure which command fits.
7. OOC communication
   - Use /ooc to speak out of character; remind that this is persisted as transcripts.

Help Content Structure (within /help)
- Quick-start cards
  - Create character
  - Roll dice
  - Make a check
  - Describe an action
  - Plan (AI-assisted)
  - Speak OOC
- Next steps
  - View character sheet and stats
  - Learn about advantage/disadvantage and roll notation
  - Scene and transcript basics
- Troubleshooting
  - Common input errors and how to fix them
  - Feature flags disabled: what that means
  - Contact and logs (high-level)

Technical Alignment and Flow
- Interaction handling
  - Verify Discord signatures (ed25519) before any processing.
  - Respond within 3 seconds by deferring, then perform help generation in a background follow-up.
  - Route help subcommands via the existing registry to keep parity with other commands.
- Responder pattern
  - Use follow-up messages for actual help content; support ephemeral responses to prevent clutter.
- Deterministic rules
  - Reference rules engine for /roll and /check. Keep explanation short and deterministic; avoid hidden randomness outside rules.
- Persistence and transcripts
  - Reference that /ooc and /plan persist user text to transcripts when applicable; help text should set expectations accordingly.
- Planner integration
  - Explain that /plan can interpret a sentence and map to the closest supported tool, with strict validation and allowlists.
  - Clarify that rationale is never shown to users and errors are ephemeral.

Defensive Behaviors
- Input validation
  - Enforce length caps (message size, JSON payloads such as character sheets).
  - Validate options against the command’s option model; echo user-facing errors concisely and ephemerally.
- Allowlist and dispatcher safety
  - /plan only routes to a small set of approved commands (roll, check, sheet.create, sheet.show, do, ooc).
- Timeouts and fallbacks
  - Soft timeout on planner; fallback to a friendly error or a safe default action.
- Idempotency and duplicate suppression
  - Cache decisions briefly to avoid duplicate planner work on repeated inputs.
- Visibility and privacy
  - Respect feature flags for LLM usage and public narration. Default to ephemeral help content to avoid channel spam.

Content Guidelines
- Tone: concise, non-technical, actionable.
- Format: short headings, bullet lists, and brief descriptions.
- No source code examples. Command names are referenced by name only.
- Keep references to files and components strictly for maintainers; end users see concise instructions.

Metrics and Observability
- Counters
  - help.view: increment when help is requested.
  - help.action.click or selection: increment when users choose a quick-start path (if interactive components are used later).
  - planner-related counters when /plan is invoked from help.
- Logs
  - Structured, minimal, no PII; include command names and high-level decisions.

Feature Flags and Configuration
- LLM-enabled and visibility flags govern /plan and any narrated outputs.
- Planner feature flag allows instant disable without redeploy.
- Help content auto-updates by reading the command registry and option models where possible.

Error Messaging (ephemeral by default)
- Unknown command or disabled feature: clear, short message with next steps.
- Invalid options: brief explanation and example of a valid input pattern (no code).
- Planner undecided: suggest trying /roll or /check explicitly.

Rollout Plan
- Shadow in a dev guild first with visibility disabled for narration and planner decisions.
- Canary enablement in one production guild.
- Monitor counter baselines and error rates; iterate on help copy where confusion is observed.
- GA after stability; keep feature flags to support rollback.

Testing Strategy
- Unit
  - Help content builder handles empty and malformed inputs gracefully.
  - Registry-driven sections render without errors when commands change.
- Integration
  - End-to-end interaction test: /help defers and follows up within expected time.
  - Planner-driven /plan discovery path functions when triggered from help.
- Non-functional
  - Load: help responses remain quick; no unbounded payloads.
  - Security: signature checks enforced, no token leakage.

Maintenance and Versioning
- Update help copy when new commands are added or option shapes change.
- Keep examples aligned with deterministic rules and planner allowlist.
- Review metrics quarterly to refine the first-run experience.

Acceptance Criteria
- /help returns a deferred immediate response and a concise, structured quick-start.
- Guidance covers character creation, roll, check, do, act, and ooc with clear next steps.
- Defensive behaviors are enforced (validation, caps, ephemeral errors, allowlist).
- Metrics increment on help usage; logs capture decisions without PII.
- Planner-related explanations appear only if LLM features are enabled; otherwise, help states that planner features are disabled.
