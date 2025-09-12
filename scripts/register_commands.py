#!/usr/bin/env python3

import os
import sys
from pathlib import Path

import httpx
import orjson
from dotenv import load_dotenv

# Load environment variables from the project root .env file and ensure src on sys.path
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
sys.path.insert(0, str(project_root / "src"))

if not env_path.exists():
    print(f"Error: .env file not found at {env_path}")
    sys.exit(1)
load_dotenv(dotenv_path=env_path)

# Fetch required environment variables with error handling
try:
    # Prefer the more explicit name; fallback to legacy if present
    APP_ID = os.environ.get("DISCORD_APPLICATION_ID") or os.environ["DISCORD_APP_ID"]
    BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
except KeyError as e:
    print(f"Error: Missing required environment variable: {e}")
    print(f"Path of .env file: {env_path}")
    sys.exit(1)

# Fetch optional environment variables with a default fallback
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")

from typing import Any

from pydantic.fields import FieldInfo

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import all_commands

# Discord API constants
CMD_CHAT_INPUT = 1
OPT_STRING = 3
OPT_INTEGER = 4
OPT_BOOLEAN = 5
OPT_NUMBER = 10
SUB_COMMAND = 1


def _map_pydantic_to_discord(field_name: str, f: FieldInfo) -> dict[str, Any]:
    # Map Pydantic annotations to Discord option types
    ann = f.annotation
    if ann in (int,):
        t = OPT_INTEGER
    elif ann in (float,):
        t = OPT_NUMBER
    elif ann in (bool,):
        t = OPT_BOOLEAN
    else:
        t = OPT_STRING
    desc = (f.description or "").strip()
    required = f.is_required()
    return {"name": field_name, "description": desc or field_name, "type": t, "required": required}


def build_commands_payload() -> list[dict[str, Any]]:
    load_all_commands()
    by_name: dict[str, list] = {}
    meta_by_name: dict[str, dict[str, Any]] = {}
    # Bucket commands by top-level name and detect subcommands
    for cmd in all_commands().values():
        by_name.setdefault(cmd.name, []).append(cmd)
        meta_by_name.setdefault(cmd.name, {"description": cmd.description})

    payload: list[dict[str, Any]] = []
    for name, cmds in by_name.items():
        # If any has a subcommand, emit as SUB_COMMANDs
        subs = [c for c in cmds if c.subcommand]
        if subs:
            sub_opts = []
            for c in subs:
                # Build subcommand option entry
                sc_opts = []
                for n, f in c.option_model.model_fields.items():
                    sc_opts.append(_map_pydantic_to_discord(n, f))
                sub_opts.append(
                    {
                        "type": SUB_COMMAND,
                        "name": c.subcommand,
                        "description": c.description,
                        "options": sc_opts,
                    }
                )
            payload.append(
                {
                    "name": name,
                    "description": meta_by_name[name]["description"],
                    "type": CMD_CHAT_INPUT,
                    "options": sub_opts,
                }
            )
        else:
            # Single, ungrouped command
            c = cmds[0]
            options = []
            for n, f in c.option_model.model_fields.items():
                options.append(_map_pydantic_to_discord(n, f))
            payload.append(
                {
                    "name": name,
                    "description": c.description,
                    "type": CMD_CHAT_INPUT,
                    "options": options,
                }
            )
    return payload

async def main():
    # Use guild-scoped registration if DISCORD_GUILD_ID is set; otherwise register globally
    if GUILD_ID:
        url = f"https://discord.com/api/v10/applications/{APP_ID}/guilds/{GUILD_ID}/commands"
        scope = f"guild {GUILD_ID}"
    else:
        url = f"https://discord.com/api/v10/applications/{APP_ID}/commands"
        scope = "global"

    headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=10) as client:
        # Clear existing commands
        clear_response = await client.put(url, headers=headers, content=orjson.dumps([]))
        if clear_response.status_code in (200, 204):
            print(f"Cleared existing commands ({scope})")
        else:
            print(f"Failed to clear commands for {scope}. Status: {clear_response.status_code}")
            print("Response:", clear_response.text)
            return

        # Register new commands
        for cmd in build_commands_payload():
            r = await client.post(url, headers=headers, content=orjson.dumps(cmd))
            if r.status_code in (200, 201):
                print(f"Registered: {cmd.get('name', '<unknown>')} ({scope}) — status {r.status_code}")
            else:
                print(f"Failed to register command '{cmd.get('name', '<unknown>')}' to {scope}. Status: {r.status_code}")
                print("Response:", r.text)

if __name__ == "__main__":
        import asyncio
        asyncio.run(main())
