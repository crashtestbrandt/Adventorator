#!/usr/bin/env python3
"""
Dynamic CLI that discovers Adventorator slash commands and runs them by issuing
signed HTTP requests to a running instance of the application.

This script acts as a mock Discord client and includes a "webhook sink" to
capture the final command output and print it to stdout.

Prerequisites:
 1. Docker Compose services must be running (`make compose-up`).
 2. Your .env file must be configured with DISCORD_APP_ID and a development-only
    DISCORD_PRIVATE_KEY. Run `scripts/generate_keys.py` to create a keypair.
"""
from __future__ import annotations

import asyncio
import os
import inspect
import json
import multiprocessing
import time
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin
from urllib.parse import urlparse

import click
import httpx
import nacl.encoding
import nacl.signing
import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel

# Ensure src is on the path to import Adventorator modules
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Command, all_commands
from Adventorator.config import load_settings

# --- Configuration ---
# Bind to 0.0.0.0 so Docker container can reach the host via host.docker.internal
SINK_HOST = "0.0.0.0"
SINK_PORT = 19000  # may be overridden after settings load
RESPONSE_TIMEOUT_SECONDS = 15

try:
    settings = load_settings()
    APP_ID = settings.discord_app_id
    APP_PORT = settings.app_port
    APP_URL = f"http://127.0.0.1:{APP_PORT}"

    if not APP_ID:
        raise ValueError("DISCORD_APP_ID must be set in your .env file.")
    if not settings.discord_private_key:
        raise ValueError(
            "DISCORD_PRIVATE_KEY is required for signing requests.\n"
            "Run `python scripts/generate_keys.py` to create one for local dev."
        )

    PRIVATE_KEY_HEX = settings.discord_private_key.get_secret_value()
    SIGNING_KEY = nacl.signing.SigningKey(
        PRIVATE_KEY_HEX, encoder=nacl.encoding.HexEncoder
    )
except Exception as e:
    click.echo(click.style(f"Error loading settings: {e}", fg="red", bold=True))
    exit(1)

# If an override webhook URL is configured, or a CLI_SINK_PORT env var is set,
# align the local sink's port so the app posts back to the right place.
override_url = os.getenv("DISCORD_WEBHOOK_URL_OVERRIDE", settings.discord_webhook_url_override or "")
try:
    if override_url:
        parsed = urlparse(override_url)
        if parsed.port:
            SINK_PORT = int(parsed.port)
    # Allow manual override for quick troubleshooting without editing compose
    SINK_PORT = int(os.getenv("CLI_SINK_PORT", SINK_PORT))
except Exception:
    pass

# --- CLI flags (pre-parse) ---
SINK_ONLY = False
NO_SINK = False
CLI_WEBHOOK_BASE = os.getenv("CLI_WEBHOOK_BASE")  # e.g., http://cli-sink:19000

def _preparse_args(argv: list[str]) -> list[str]:
    global SINK_ONLY, NO_SINK, CLI_WEBHOOK_BASE, SINK_PORT
    remaining: list[str] = []
    it = iter(argv)
    for a in it:
        if a == "--sink-only":
            SINK_ONLY = True
            continue
        if a == "--no-sink":
            NO_SINK = True
            continue
        if a == "--webhook-base":
            try:
                CLI_WEBHOOK_BASE = next(it)
            except StopIteration:
                pass
            continue
        if a == "--sink-port":
            try:
                SINK_PORT = int(next(it))
            except Exception:
                pass
            continue
        remaining.append(a)
    return remaining

# --- Webhook Sink Server ---
# A FastAPI app that receives follow-up webhooks. We share an Event between
# processes via a multiprocessing.Manager, but it's created at runtime to avoid
# spawn/import issues on macOS. The child process receives the Event and sets a
# module-global reference so the route handler can signal completion.
sink_app = FastAPI()
webhook_received = None  # set in child process by run_sink_server(event)

@sink_app.post("/webhooks/{application_id}/{token}")
async def receive_webhook(request: Request):
    """Catches the follow-up message from the main application."""
    payload = await request.json()
    content = payload.get("content", "No content found in webhook.")
    ephemeral = bool(payload.get("flags", 0) & 64)

    # Use click.echo in a process-safe way
    output = [
        "\n--- Follow-up Message Received ---",
        "(Ephemeral)" if ephemeral else "",
        content,
        "----------------------------------",
    ]
    print("\n".join(line for line in output if line))
    
    webhook_received.set()
    return {"status": "ok"}

def run_sink_server(event):
    """Runs the Uvicorn server (target for the new process).

    The parent process passes in a Manager().Event proxy; we stash it in a
    module-global so the route handler can set() it when a webhook arrives.
    """
    global webhook_received
    webhook_received = event
    uvicorn.run(sink_app, host=SINK_HOST, port=SINK_PORT, log_level="warning")


async def _send_interaction(command: Command, options: dict[str, Any]):
    """Optionally starts a local sink, sends the interaction, and waits for the response."""
    # Decide whether to run local sink
    manager = None
    server_process = None
    event = None
    if not NO_SINK:
        manager = multiprocessing.Manager()
        event = manager.Event()
        # Use a separate process for the sink server for robust cleanup.
        server_process = multiprocessing.Process(target=run_sink_server, args=(event,), daemon=True)
        server_process.start()
        await asyncio.sleep(0.7)  # Give server a moment to start and bind to the port.
        if not server_process.is_alive():
            click.echo(click.style(
                f"Webhook sink failed to start on {SINK_HOST}:{SINK_PORT} (port busy?).\n"
                "Tip: ensure nothing else is listening on that port, or restart Docker Desktop.",
                fg="red",
                bold=True,
            ))
            try:
                server_process.join(timeout=0.2)
            except Exception:
                pass
            try:
                if manager:
                    manager.shutdown()
            except Exception:
                pass
            return

    try:
        if command.subcommand:
            data_payload = { "id": "1", "name": command.name, "type": 1, "options": [{"name": command.subcommand, "type": 1, "options": [{"name": k, "value": v} for k, v in options.items()]}] }
        else:
            data_payload = { "id": "1", "name": command.name, "type": 1, "options": [{"name": k, "value": v} for k, v in options.items()] }

        full_payload = { "id": "2", "type": 2, "token": "fake-token", "application_id": APP_ID, "data": data_payload, "guild_id": "1", "channel_id": "1", "member": {"user": {"id": "1", "username": "cli_user"}, "roles": [], "joined_at": "2025-01-01T00:00:00Z"}, "guild": {"id": "1"}, "channel": {"id": "1"} }
        body = json.dumps(full_payload, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        message = timestamp.encode() + body
        signed = SIGNING_KEY.sign(message)
        headers = { "X-Signature-Ed25519": signed.signature.hex(), "X-Signature-Timestamp": timestamp, "Content-Type": "application/json" }
        # Signal to the server that this request should be verified with the dev public key (if configured)
        headers["X-Adventorator-Use-Dev-Key"] = "1"
        # Per-request webhook base override so app routes follow-ups back to our sink
        # Priority: explicit --webhook-base > mode default
        if CLI_WEBHOOK_BASE:
            headers["X-Adventorator-Webhook-Base"] = CLI_WEBHOOK_BASE
        else:
            if NO_SINK:
                # Use the sidecar service inside the compose network
                headers["X-Adventorator-Webhook-Base"] = "http://cli-sink:19000"
            else:
                # Local sink on host; containers can reach it via host.docker.internal
                headers["X-Adventorator-Webhook-Base"] = f"http://host.docker.internal:{SINK_PORT}"

        cmd_name_str = f"{command.name}{'.' + command.subcommand if command.subcommand else ''}"
        click.echo(f"-> POST {APP_URL}/interactions (command: {cmd_name_str})")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{APP_URL}/interactions", content=body, headers=headers)
        
        if response.status_code >= 400:
            click.echo(click.style(f"<- HTTP {response.status_code} Error: {response.text}", fg="red"))
            return
        click.echo(f"<- HTTP {response.status_code} {response.json()}")

        # Wait for the webhook to be received by the local sink, with a timeout.
        if event is not None:
            received = event.wait(timeout=RESPONSE_TIMEOUT_SECONDS)
            if not received:
                click.echo(click.style(f"\nWarning: Did not receive a follow-up message within {RESPONSE_TIMEOUT_SECONDS} seconds.", fg="yellow"))
        else:
            click.echo("(Follow-up will be delivered to sink service; check docker logs for cli-sink)")

    except httpx.ConnectError:
        click.echo(click.style(f"Connection Error: Is the app running at {APP_URL}?", fg="red", bold=True))
    finally:
        # Crucially, ensure the server process is terminated.
        if server_process is not None and server_process.is_alive():
            server_process.terminate()
            server_process.join()
        # Shut down the manager to clean up its server process.
        try:
            if manager is not None:
                manager.shutdown()
        except Exception:
            pass

# --- CLI Building Logic (unchanged) ---
# ... (rest of the file is identical)

def _click_type_for(annotation: Any):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is None:
        if annotation in (str, int, float): return {str: str, int: int, float: float}[annotation]
        if annotation is bool: return bool
        if inspect.isclass(annotation) and issubclass(annotation, Enum):
            return click.Choice([e.value for e in annotation], case_sensitive=False)
        return str
    if origin in (list, tuple, dict): return str
    if origin in (Union, UnionType) and args:
        return _click_type_for(next((a for a in args if a is not type(None)), str))
    return str

def _params_from_model(option_model: type[BaseModel]) -> list[click.Parameter]:
    params: list[click.Parameter] = []
    fields = getattr(option_model, "model_fields", {})
    if len(fields) == 1:
        name, field = next(iter(fields.items()))
        if field.annotation is str and field.is_required() and not field.alias:
            return [click.Argument([name])]
    for name, field in fields.items():
        opt_name = f"--{(field.alias or name).replace('_', '-')}"
        if field.annotation is bool:
            params.append(click.Option([opt_name], is_flag=True, default=field.default or False, help=field.description))
            continue
        params.append(click.Option(
            [opt_name], type=_click_type_for(field.annotation),
            required=field.is_required(), default=field.default,
            show_default=field.default is not None, help=field.description,
        ))
    return params

def _make_click_command(command: Command) -> click.Command:
    params = _params_from_model(command.option_model)
    def _callback(**kwargs: Any):
        # Manager/Event are created per invocation inside _send_interaction.
        asyncio.run(_send_interaction(command, kwargs))
    return click.Command(name=command.subcommand or command.name, params=params, callback=_callback, help=command.description)

def build_app() -> click.Group:
    load_all_commands()
    app = click.Group()
    bucket: dict[str, list[Command]] = {}
    for cmd in all_commands().values():
        bucket.setdefault(cmd.name, []).append(cmd)
    for name, cmds in sorted(bucket.items()):
        subs = [c for c in cmds if c.subcommand]
        if subs:
            grp = click.Group(name=name, help=cmds[0].description)
            for c in sorted(subs, key=lambda cmd: cmd.subcommand or ''):
                grp.add_command(_make_click_command(c))
            app.add_command(grp)
        elif cmds:
            app.add_command(_make_click_command(cmds[0]))
    return app

def main() -> None:
    # Pre-parse custom flags then hand the rest to click
    argv = sys.argv[1:]
    argv = _preparse_args(argv)

    # Sink-only mode: just run the sink server and exit
    if SINK_ONLY:
        # Use a local event that never gets waited on
        manager = multiprocessing.Manager()
        event = manager.Event()
        click.echo(f"Starting webhook sink on {SINK_HOST}:{SINK_PORT} ...")
        run_sink_server(event)
        return

    app = build_app()
    # Invoke click with the remaining args
    app(standalone_mode=True, prog_name="web-cli", args=argv)

if __name__ == "__main__":
    main()

