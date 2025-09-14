"""FastAPI app entrypoint for Adventorator."""

import asyncio
import time
import uuid
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request

from Adventorator import repos
from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, Responder, find_command
from Adventorator.config import load_settings
from Adventorator.crypto import verify_ed25519
from Adventorator.db import session_scope
from Adventorator.discord_schemas import Interaction
from Adventorator.llm import LLMClient
from Adventorator.logging import redact_settings, setup_logging
from Adventorator.metrics import get_counters
from Adventorator.responder import followup_message, respond_deferred, respond_pong
from Adventorator.rules.dice import DiceRNG

rng = DiceRNG()  # TODO: Seed per-scene later

log = structlog.get_logger()
settings = load_settings()
setup_logging(settings)
app = FastAPI(title="Adventorator")

llm_client = None
if settings.features_llm:
    llm_client = LLMClient(settings)


@app.on_event("startup")
async def startup():
    # Log startup configuration with secrets redacted
    try:
        log.info("app.startup", config=redact_settings(settings))
    except Exception:
        # Avoid crashing startup due to logging issues
        pass
    load_all_commands()


@app.on_event("shutdown")
async def shutdown_event():
    if llm_client:
        await llm_client.close()


DISCORD_SIG_HEADER = "X-Signature-Ed25519"
DISCORD_TS_HEADER = "X-Signature-Timestamp"


@app.post("/interactions")
async def interactions(request: Request):
    raw = await request.body()
    sig = request.headers.get(DISCORD_SIG_HEADER)
    ts = request.headers.get(DISCORD_TS_HEADER)
    # Log receipt before signature validation
    try:
        log.info(
            "discord.request.received",
            http_path=str(request.url.path),
            http_method=request.method,
            has_sig=bool(sig),
            has_ts=bool(ts),
        )
    except Exception:
        pass
    if not sig or not ts:
        log.error("Missing signature headers", sig=sig, ts=ts)
        raise HTTPException(status_code=401, detail="missing signature headers")

    if not verify_ed25519(settings.discord_public_key, ts, raw, sig):
        log.error("Invalid signature", sig=sig, ts=ts)
        raise HTTPException(status_code=401, detail="bad signature")

    try:
        inter = Interaction.model_validate_json(raw)
    except Exception as err:
        # Include tiny preview for debugging only; avoid full body spam
        preview = (
            raw[:200].decode("utf-8", errors="replace")
            if isinstance(raw, (bytes | bytearray))
            else str(raw)[:200]
        )
        log.error("discord.request.parse_error", raw_body_preview=preview)
        raise HTTPException(status_code=400, detail="invalid interaction payload") from err
    log.info("discord.request.validated", interaction=inter.model_dump())

    async with session_scope() as s:
        guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)
        campaign = await repos.get_or_create_campaign(s, guild_id)
        await repos.ensure_scene(s, campaign.id, channel_id)
        # Content can be reconstructed from command name/options; store a compact form:
        # msg = f"/{inter.data.name}" if inter.data and inter.data.name else "<interaction>"
    # await repos.write_transcript(
    #     s, campaign.id, scene.id, channel_id,
    #     "player", msg, str(user_id), meta=inter.model_dump()
    # )

    # Ping = 1
    if inter.type == 1:
        return respond_pong()

    # Anything else: immediately DEFER (type 5) to satisfy the 3s budget.

    if inter.type == 2 and inter.data is not None and inter.data.name is not None:
        asyncio.create_task(_dispatch_command(inter))
    return respond_deferred()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Assign a request_id, bind it to structlog context, and measure duration.

    Also adds X-Request-ID header to the response for correlation.
    """
    from structlog.contextvars import bind_contextvars, clear_contextvars

    request_id = str(uuid.uuid4())
    start = time.perf_counter()
    bind_contextvars(request_id=request_id)
    status_code = 500
    try:
        response = await call_next(request)
        status_code = getattr(response, "status_code", 200)
        return response
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        try:
            log.info(
                "http.request.completed",
                http_path=str(request.url.path),
                http_method=request.method,
                http_status_code=status_code,
                duration_ms=duration_ms,
            )
        except Exception:
            pass
        try:
            # Add header on the way out; FastAPI Response may not be available if exception
            if 'response' in locals():
                response.headers["X-Request-ID"] = request_id
        except Exception:
            pass
        clear_contextvars()


async def _dispatch_command(inter: Interaction):
    # Safe: _dispatch_command only called when inter.data and name are present
    assert inter.data is not None and inter.data.name is not None
    name = inter.data.name

    # 0) Registry-backed commands (new pattern): if a command module exists under
    #    Adventorator.commands and is registered, dispatch here and return.
    #    This keeps handlers transport-agnostic and shared with the CLI.
    # Extract potential subcommand (Discord encodes SUB_COMMAND as first option type=1)
    sub = _subcommand(inter)
    cmd = find_command(name, sub)
    if cmd is not None:
        # Build options map from Discord interaction (flatten SUB_COMMAND if present)
        options: dict[str, Any] = {}
        opts: list[dict[str, Any]] = (
            inter.data.options or [] if inter.data is not None else []
        )
        if opts and isinstance(opts[0], dict) and opts[0].get("type") == 1:
            # SUB_COMMAND: options one level deeper
            opts = opts[0].get("options", []) or []
        for o in opts:
            n = o.get("name")
            if isinstance(n, str):
                options[n] = o.get("value")

        class DiscordResponder(Responder):  # type: ignore[misc]
            def __init__(self, application_id: str, token: str):
                self.application_id = application_id
                self.token = token

            async def send(self, content: str, *, ephemeral: bool = False) -> None:  # noqa: D401
                await followup_message(
                    self.application_id,
                    self.token,
                    content,
                    ephemeral=ephemeral,
                )

        guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)
        inv = Invocation(
            name=name,
            subcommand=sub,
            options=options,
            user_id=str(user_id),
            channel_id=str(channel_id) if channel_id else None,
            guild_id=str(guild_id) if guild_id else None,
            responder=DiscordResponder(inter.application_id, inter.token),
            settings=settings,
            llm_client=llm_client,
        )
        # Structured command invocation lifecycle logging
        start = time.perf_counter()
        status = "success"
        try:
            opts_obj = cmd.option_model.model_validate(options)
        except Exception:
            status = "options_error"
            await followup_message(
                inter.application_id,
                inter.token,
                f"❌ Invalid options for `{name}`.",
                ephemeral=True,
            )
            try:
                log.info(
                    "command.completed",
                    command_name=name,
                    subcommand=sub,
                    options=options,
                    user_id=str(user_id),
                    guild_id=str(guild_id) if guild_id else None,
                    status=status,
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
            except Exception:
                pass
            return
        try:
            log.info(
                "command.initiated",
                command_name=name,
                subcommand=sub,
                options=options,
                user_id=str(user_id),
                guild_id=str(guild_id) if guild_id else None,
            )
            await cmd.handler(inv, opts_obj)
        except Exception:  # Let FastAPI/global handlers decide further
            status = "error"
            log.error(
                "command.error",
                command_name=name,
                subcommand=sub,
                options=options,
                user_id=str(user_id),
                guild_id=str(guild_id) if guild_id else None,
                exc_info=True,
            )
            raise
        finally:
            try:
                log.info(
                    "command.completed",
                    command_name=name,
                    subcommand=sub,
                    options=options,
                    user_id=str(user_id),
                    guild_id=str(guild_id) if guild_id else None,
                    status=status,
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
            except Exception:
                pass
    return


def _subcommand(inter: Interaction) -> str | None:
    # options[0].name for SUB_COMMAND
    if inter.data is not None and inter.data.options:
        first = inter.data.options[0]
        if isinstance(first, dict) and first.get("type") == 1:
            name = first.get("name")
            return str(name) if name is not None else None
    return None


def _option(inter: Interaction, name: str, default: Any | None = None) -> Any | None:
    # If you’re inside a SUB_COMMAND, options are nested one level deeper
    opts: list[dict[str, Any]] = inter.data.options or [] if inter.data is not None else []
    if opts and isinstance(opts[0], dict) and opts[0].get("type") == 1:
        opts = opts[0].get("options", [])
    for opt in opts or []:
        if opt.get("name") == name:
            return opt.get("value", default)
    return default


def _infer_ids_from_interaction(inter):
    guild_id = int(inter.guild.id) if inter.guild else 0
    channel_id = int(inter.channel.id) if inter.channel else 0
    user = inter.member.user if inter.member and inter.member.user else None
    user_id = int(user.id) if user else 0
    username = user.username if user else "Unknown"
    return guild_id, channel_id, user_id, username


async def _resolve_context(inter: Interaction):
    guild_id = int(inter.guild.id) if inter.guild else 0
    channel_id = int(inter.channel.id) if inter.channel else 0
    user = inter.member.user if inter.member and inter.member.user else None
    user_id = int(user.id) if user else 0
    username = user.username if user else "Unknown"

    # Discord Interaction payloads carry these in different places depending on type.
    # For slash commands: guild_id & channel_id are in "guild_id"/"channel" fields
    # (add to schemas if needed).
    # For simplicity here, we assume you extended Interaction to include guild_id/channel.id/user.id
    # If not, adapt based on your actual payload.

    # TODO: parse from raw JSON fields in your Interaction model if missing.

    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id, name="Default")
        player = await repos.get_or_create_player(s, user_id, username)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        await repos.write_transcript(
            s,
            campaign.id,
            scene.id,
            channel_id,
            "player",
            "<user message>",
            str(user_id),
        )
        return campaign, player, scene


@app.get("/healthz")
async def healthz():
    # Basic checks: commands loaded, DB reachable
    try:
        load_all_commands()
        async with session_scope() as s:
            # lightweight query
            await repos.healthcheck(s)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"unhealthy: {err}") from err
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    if not getattr(settings, "metrics_endpoint_enabled", False):
        raise HTTPException(status_code=404, detail="metrics disabled")
    # Return a simple JSON dump of counters for local ops
    return get_counters()
