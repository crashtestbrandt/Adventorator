# Manual Smoke Tests

This doc outlines a quick manual smoke suite using both the Web CLI (`scripts/web_cli.py`) and the actual Discord client. Skip `scripts/cli.py` for now; focus on the same network path Discord uses.

Prereqs
- .env configured (Discord app ID, public key, bot token, webhook override for dev optional)
- App running locally (`make run`) or via docker compose (`docker compose up -d --build db app`)
- Tunnel running (`make tunnel`) if testing from Discord

## Part A — Web CLI (local HTTP to /interactions)

Why: Exercise FastAPI `/interactions` and follow-up webhooks without Discord.

1) Ping/pong health
- Run: `PYTHONPATH=./src python scripts/web_cli.py ping`
- Expect: Deferred ACK then a follow-up "pong" (or success log) to the webhook sink.

2) Roll dice
- Run: `PYTHONPATH=./src python scripts/web_cli.py roll --expr 2d6+3`
- Expect: Follow-up content with rolls and total.

3) Ability check
- Run: `PYTHONPATH=./src python scripts/web_cli.py check --ability DEX --dc 15`
- Expect: Mechanics block with d20, mod, total, verdict.

4) Planner routing
- Run: `PYTHONPATH=./src python scripts/web_cli.py plan --text "make a dexterity check vs DC 12"`
- Expect: Routed to /check with validated args; follow-up result.

5) Orchestrator OOC
- Run: `PYTHONPATH=./src python scripts/web_cli.py ooc --text "Describe the ancient door."`
- Expect: LLM-generated narration (visible only if `features.llm_visible=true`, otherwise shadow).

6) Pending confirm flow (if enabled)
- Run: `PYTHONPATH=./src python scripts/web_cli.py do --text "I try to pick the lock"`
- Expect: Preview with an action ID; then confirm/cancel via:
  - `PYTHONPATH=./src python scripts/web_cli.py confirm --id <pending_id>`
  - `PYTHONPATH=./src python scripts/web_cli.py cancel --id <pending_id>`

Notes
- For dev, you can route follow-ups to a local sink by setting the `X-Adventorator-Webhook-Base` header; see `config.toml` and `responder.py` override behavior.

## Part B — Discord client (end-to-end)

Why: Verify real user experience, intents, and permissions with signed requests.

Setup
- Run `python scripts/register_commands.py` to register slash commands in your dev guild.
- Start the tunnel and set the tunnel URL as your interaction endpoint in the Discord Developer Portal.

Smoke steps
1) `/roll 1d20` — Expect deferred, then a clean follow-up with total.
2) `/check ability:DEX dc:15` — Expect correct mechanics block.
3) `/plan "sneak past the guard"` — Expect /do route with guarded narration + mechanics.
4) `/ooc "Where does the corridor lead?"` — Expect OOC narration with transcript entry.
5) `/sheet show` — Expect compact character summary (ephemeral) if a sheet exists.
6) (If enabled) `/do "pick the lock"` — Expect preview with confirm/cancel commands.

Troubleshooting
- If no follow-up arrives, check logs for webhook errors; ensure `DISCORD_BOT_TOKEN` is set and not using an override URL accidentally.
- If signature verification fails, confirm Public Key and the tunnel path are correct and the trusted dev headers are only used in dev.
