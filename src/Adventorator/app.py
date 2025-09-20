"""FastAPI app entrypoint for Adventorator."""

import asyncio
import contextvars
import time
import uuid
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request

from Adventorator import repos
from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, Responder, find_command
from Adventorator.config import Settings, load_settings
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

# Stash the current request for downstream helpers (initialized in middleware)
_current_request_var: contextvars.ContextVar | None = None

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
DEV_KEY_HEADER = "X-Adventorator-Use-Dev-Key"


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

    # Allow a trusted dev header to opt-in to an alternate public key for local CLI
    use_dev_key = request.headers.get(DEV_KEY_HEADER) == "1"
    # Compute which public key will be used (dev key allowed only in dev)
    use_dev_pub = (
        use_dev_key
        and getattr(settings, "env", None) == "dev"
        and bool(getattr(settings, "discord_dev_public_key", None))
    )
    dev_key: str = getattr(settings, "discord_dev_public_key", "") or ""
    prod_key: str = getattr(settings, "discord_public_key", "") or ""
    pubkey_used: str = dev_key if use_dev_pub else prod_key
    pubkey = pubkey_used
    log.info(
        "signature.verification",
        use_dev_key=use_dev_key,
        env=getattr(settings, "env", None),
        has_dev_public_key=bool(getattr(settings, "discord_dev_public_key", None)),
        pubkey_used=pubkey_used,
        dev_header=request.headers.get(DEV_KEY_HEADER),
    )
    if not verify_ed25519(pubkey, ts, raw, sig):
        log.error("Invalid signature", sig=sig, ts=ts, pubkey_used=pubkey, use_dev_key=use_dev_key)
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

    # Ping = 1
    if inter.type == 1:
        return respond_pong()

    # Anything else: immediately DEFER (type 5) to satisfy the 3s budget.

    if inter.type == 2 and inter.data is not None and inter.data.name is not None:
        # dev_request True only when the dev public key was used (local CLI),
        # ensuring settings-based webhook override is ignored for real Discord traffic.
        asyncio.create_task(_dispatch_command(inter, dev_request=use_dev_pub))
    return respond_deferred()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Assign a request_id, bind it to structlog context, and measure duration."""
    from structlog.contextvars import bind_contextvars, clear_contextvars

    # Stash request in a ContextVar for downstream helpers that need headers
    global _current_request_var
    if _current_request_var is None:
        _current_request_var = contextvars.ContextVar("current_request")

    req_token = _current_request_var.set(request)
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
        # Reset the request ContextVar so it doesn't leak across requests
        try:
            _current_request_var.reset(req_token)
        except Exception:
            pass
        clear_contextvars()


async def _dispatch_command(inter: Interaction, *, dev_request: bool = False):
    # Safe: _dispatch_command only called when inter.data and name are present
    assert inter.data is not None and inter.data.name is not None
    name = inter.data.name
    sub = _subcommand(inter)
    cmd = find_command(name, sub)
    if cmd is not None:
        options: dict[str, Any] = {}
        opts: list[dict[str, Any]] = inter.data.options or [] if inter.data is not None else []
        if opts and isinstance(opts[0], dict) and opts[0].get("type") == 1:
            opts = opts[0].get("options", []) or []
        for o in opts:
            n = o.get("name")
            if isinstance(n, str):
                options[n] = o.get("value")

        class DiscordResponder(Responder):  # type: ignore[misc]
            def __init__(
                self,
                application_id: str,
                token: str,
                settings: Settings,
                webhook_base_url: str | None = None,
                dev_request: bool = False,
            ):
                self.application_id = application_id
                self.token = token
                self.settings = settings
                # Allows trusted callers (e.g., internal CLI) to request a per-interaction sink
                self.webhook_base_url = webhook_base_url
                self.dev_request = dev_request

            async def send(self, content: str, *, ephemeral: bool = False) -> None:
                try:
                    await followup_message(
                        self.application_id,
                        self.token,
                        content,
                        ephemeral=ephemeral,
                        settings=self.settings,
                        webhook_base_url=self.webhook_base_url,
                        allow_settings_override=self.dev_request,
                    )
                except TypeError:
                    # Test spies may not accept the keyword-only 'settings' parameter
                    await followup_message(
                        self.application_id,
                        self.token,
                        content,
                        ephemeral=ephemeral,
                        # mypy: test spies monkeypatch this symbol without the 'settings' kwarg
                        # which is intentional in tests; ignore the type mismatch here.
                        # type: ignore[call-arg]
                    )

        guild_id, channel_id, user_id, username = _infer_ids_from_interaction(inter)
        # Allow a trusted caller to provide a one-off webhook base via header
        webhook_base_url = request_header_override()
        from Adventorator.rules.engine import Dnd5eRuleset

        inv = Invocation(
            name=name,
            subcommand=sub,
            options=options,
            user_id=str(user_id),
            channel_id=str(channel_id) if channel_id else None,
            guild_id=str(guild_id) if guild_id else None,
            responder=DiscordResponder(
                inter.application_id,
                inter.token,
                settings,
                webhook_base_url,
                dev_request=dev_request,
            ),
            settings=settings,
            llm_client=llm_client,
            ruleset=Dnd5eRuleset(),
        )
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
                settings=settings,
                allow_settings_override=dev_request,
            )
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
        except Exception:
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
    return


def request_header_override() -> str | None:
    """Placeholder for propagating a per-request webhook base URL.

    When the web CLI calls /interactions, it can include a custom header
    (e.g., X-Adventorator-Webhook-Base) that we trust in dev to route the
    follow-up to the local sink service. In production, callers won't set it,
    and the app falls back to Discord.
    """
    try:
        # A small shim: stash the current request in a contextvar in middleware
        global _current_request_var
        if _current_request_var is None:
            return None
        req = _current_request_var.get(None)
        if not req:
            return None
        val = req.headers.get("X-Adventorator-Webhook-Base")
        return val
    except Exception:
        return None


def _subcommand(inter: Interaction) -> str | None:
    if inter.data is not None and inter.data.options:
        first = inter.data.options[0]
        if isinstance(first, dict) and first.get("type") == 1:
            name = first.get("name")
            return str(name) if name is not None else None
    return None


def _infer_ids_from_interaction(inter):
    guild_id = int(inter.guild.id) if inter.guild and inter.guild.id else 0
    channel_id = int(inter.channel.id) if inter.channel and inter.channel.id else 0
    user = inter.member.user if inter.member and inter.member.user else None
    user_id = int(user.id) if user and user.id else 0
    username = user.username if user else "Unknown"
    return guild_id, channel_id, user_id, username


@app.get("/healthz")
async def healthz():
    try:
        load_all_commands()
        async with session_scope() as s:
            await repos.healthcheck(s)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"unhealthy: {err}") from err
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    if not getattr(settings, "metrics_endpoint_enabled", False):
        raise HTTPException(status_code=404, detail="metrics disabled")
    return get_counters()


_LAST_DEV_WEBHOOK: dict[str, dict] = {}


@app.post("/dev-webhook/webhooks/{application_id}/{token}")
async def dev_webhook(application_id: str, token: str, request: Request):
    """Local development sink for follow-up webhook messages.

    This endpoint is only used when running with the environment variable
    DISCORD_WEBHOOK_URL_OVERRIDE set to a base like
    http://127.0.0.1:18000/dev-webhook

    The production flow (Discord callbacks) is unaffected because the
    override is opt-in and the real Discord domain is still the default
    when the override is not set.
    """
    try:
        ctype = request.headers.get("content-type", "")
        payload: dict | None = None
        if ctype.startswith("multipart/form-data"):
            form = await request.form()
            pj = form.get("payload_json")
            if pj:
                if isinstance(pj, bytes):
                    import orjson as _oj  # local import to avoid unused if branch never hit
                    payload = _oj.loads(pj)
                else:  # str
                    import orjson as _oj
                    payload = _oj.loads(pj.encode())
        else:
            try:
                payload = await request.json()
            except Exception:
                raw = await request.body()
                if raw:
                    import orjson as _oj
                    try:
                        payload = _oj.loads(raw)
                    except Exception:
                        payload = {"_raw": raw[:200].decode(errors="replace")}
        content_val = None
        if isinstance(payload, dict):
            content_val = payload.get("content")
        log.info(
            "dev_webhook.received",
            application_id=application_id,
            token_preview=token[:8],
            content_len=len(content_val or ""),
        )
        # Store latest payload per token for local polling by web_cli
        if isinstance(payload, dict):
            _LAST_DEV_WEBHOOK[token] = payload
        # Echo back minimal acknowledgement so callers treat it as success
        return {"status": "ok", "echo": content_val}
    except Exception as err:  # Defensive: never crash dev sink
        log.error("dev_webhook.error", error=str(err))
        raise HTTPException(status_code=400, detail=f"bad dev webhook payload: {err}") from err


@app.get("/dev-webhook/latest/{token}")
async def dev_webhook_latest(token: str):
    """Retrieve the most recent dev webhook payload for a token (local only)."""
    payload = _LAST_DEV_WEBHOOK.get(token)
    if not payload:
        return {"status": "empty"}
    return {"status": "ok", "payload": payload}
