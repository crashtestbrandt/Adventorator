#!/usr/bin/env python3


"""
Discord Command Management Script

This script provides functionality to manage Discord slash commands for a bot, including registering, unregistering, validating, and checking the status of commands.

Features:
- Register commands globally or for a specific guild.
- Unregister commands globally or for a specific guild.
- Check the status of registered commands against local definitions.

Usage:
  - To check the status of commands:
    python register_commands.py --status [--global|--guild [GUILD_ID]]
  - To register commands:
    python register_commands.py --register [--global|--guild [GUILD_ID]] [--commands command1,command2]
  - To unregister commands:
    python register_commands.py --unregister [--global|--guild [GUILD_ID]] [--commands command1,command2]

Arguments:
  --status       Check the status of commands.
  --register     Register commands.
  --unregister   Unregister commands.
  --global       Apply action to global commands (default).
  --guild        Apply action to guild commands. Optionally specify a guild ID.
  --commands     Comma-separated list of commands to process.

Environment Variables:
  - DISCORD_APPLICATION_ID or DISCORD_APP_ID: The application ID of the Discord bot.
  - DISCORD_BOT_TOKEN: The bot token for authentication.
  - DISCORD_GUILD_ID (optional): The guild ID for guild-scoped commands.

Examples:
  - Check the status of commands:
    python register_commands.py --status
  - Register all commands globally:
    python register_commands.py --register --global
  - Register specific commands for a guild:
    python register_commands.py --register --guild [GUILD_ID] --commands command1,command2
  - Unregister all commands globally:
    python register_commands.py --unregister --global
  - Validate commands:
    python register_commands.py --status

Dependencies:
  - httpx: For making HTTP requests to the Discord API.
  - orjson: For fast JSON serialization.
  - python-dotenv: For loading environment variables from a .env file.
  - pydantic: For command option validation.
  - prettytable: For displaying command status in a table format.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import orjson
from dotenv import load_dotenv
from prettytable import PrettyTable

# Load environment variables from .env.local (preferred) or fallback to legacy .env
project_root = Path(__file__).parent.parent
env_local = project_root / ".env.local"
env_legacy = project_root / ".env"
env_path = env_local if env_local.exists() else env_legacy
sys.path.insert(0, str(project_root / "src"))

if not env_path.exists():
    print(
        f"Error: neither .env.local nor .env found at project root (looked for {env_local} and {env_legacy})."
    )
    sys.exit(1)
load_dotenv(dotenv_path=env_path)

# Fetch required environment variables with error handling
try:
    # Prefer the more explicit name; fallback to legacy if present
    APP_ID = os.environ.get("DISCORD_APPLICATION_ID") or os.environ["DISCORD_APP_ID"]
    BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
except KeyError as e:
    print(f"Error: Missing required environment variable: {e}")
    print(f"Path of env file used: {env_path}")
    sys.exit(1)

# Fetch optional environment variables with a default fallback
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")

from typing import Any

from pydantic.fields import FieldInfo

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import all_commands
from Adventorator.config import load_settings

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

def _get_command_url(scope: str, guild_id: str = None) -> str:
    """Helper to construct the appropriate Discord API URL based on scope."""
    base_url = f"https://discord.com/api/v10/applications/{APP_ID}"
    if scope == "global":
        return f"{base_url}/commands"
    elif scope == "guild" and guild_id:
        return f"{base_url}/guilds/{guild_id}/commands"
    else:
        raise ValueError("Invalid scope or missing guild_id for guild commands.")

async def _fetch_commands(client, url, headers) -> list[dict]:
    """Fetch registered commands from Discord API."""
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        print(f"HTTP error while fetching commands: {e.response.status_code}")
    except Exception as e:
        print(f"Unexpected error while fetching commands: {e}")
    return []

async def _process_commands(client, url, headers, commands, action: str):
    """Process commands for registration or unregistration."""
    for cmd in commands:
        try:
            if action == "register":
                response = await client.post(url, headers=headers, content=orjson.dumps(cmd))
            elif action == "unregister":
                delete_url = f"{url}/{cmd['id']}"
                response = await client.delete(delete_url, headers=headers)
            else:
                raise ValueError("Invalid action specified.")

            if response.status_code in (200, 201, 204):
                print(f"{action.capitalize()}ed: {cmd.get('name', '<unknown>')} ({url})")
            else:
                print(f"Failed to {action} {cmd.get('name', '<unknown>')} ({url}). Status: {response.status_code}")
        except Exception as e:
            print(f"Error during {action} for {cmd.get('name', '<unknown>')}: {e}")

async def _validate_and_get_commands(local_commands, registered_commands, action: str) -> list[dict]:
    """Validate and filter commands based on the action."""
    if action == "register":
        return [cmd for cmd in local_commands if not any(rc['name'] == cmd['name'] for rc in registered_commands)]
    elif action == "unregister":
        return [cmd for cmd in registered_commands if cmd['name'] in [lc['name'] for lc in local_commands]]
    else:
        raise ValueError("Invalid action for command validation.")

def format_options(options, level=0):
    formatted = []
    indent = "  " * level
    for opt in options:
        sub_options = opt.get("options", [])
        formatted.append(f"{indent}- {opt['name']} ({'Required' if opt.get('required', False) else 'Optional'}): {opt.get('description', 'No description')}")
        if sub_options:
            formatted.extend(format_options(sub_options, level + 1))
    return formatted

def print_status(local_commands, registered_commands, scope):
    print(f"\nStatus for {scope} commands:")
    table = PrettyTable()
    table.field_names = ["Command Name", "Registered", "Description", "Options"]
    table.hrules = 1  # Enable horizontal row lines

    for cmd in local_commands:
        registered = any(rc['name'] == cmd['name'] for rc in registered_commands)
        options = "\n".join(format_options(cmd.get("options", [])))
        table.add_row([
            cmd['name'],
            "Yes" if registered else "No",
            cmd.get("description", "No description"),
            options or "No options",
        ])

    print(table)

async def status_command(client, urls, headers, local_commands):
    for scope, url in urls.items():
        if url:
            registered_commands = await _fetch_commands(client, url, headers)
            print_status(local_commands, registered_commands, scope)

async def register_commands(client, url, headers, commands_to_register, scope):
    for cmd in commands_to_register:
        response = await client.post(url, headers=headers, content=json.dumps(cmd))
        if response.status_code in (200, 201):
            print(f"Registered: {cmd['name']} ({scope})")
        else:
            print(f"Failed to register {cmd['name']} ({scope}). Status: {response.status_code}")

async def unregister_commands(client, url, headers, commands_to_unregister, scope):
    registered_commands = await _fetch_commands(client, url, headers)
    for cmd_name in commands_to_unregister:
        cmd = next((c for c in registered_commands if c['name'] == cmd_name), None)
        if cmd:
            delete_url = f"{url}/{cmd['id']}"
            response = await client.delete(delete_url, headers=headers)
            if response.status_code == 204:
                print(f"Unregistered: {cmd_name} ({scope})")
            else:
                print(f"Failed to unregister {cmd_name} ({scope}). Status: {response.status_code}")
        else:
            print(f"Command {cmd_name} not found in {scope}.")

async def main():
    parser = argparse.ArgumentParser(description="Manage Discord slash commands.")
    parser.add_argument("--status", action="store_true", help="Check the status of commands.")
    parser.add_argument("--register", action="store_true", help="Register commands.")
    parser.add_argument("--unregister", action="store_true", help="Unregister commands.")
    parser.add_argument("--global", action="store_true", dest="is_global", help="Apply action to global commands.")
    parser.add_argument("--guild", nargs="?", const=True, dest="is_guild", help="Apply action to guild commands. Optionally specify a guild ID.")
    parser.add_argument("--commands", help="Comma-separated list of commands to process.")
    args = parser.parse_args()

    if not args.is_global and not args.is_guild:
        args.is_global = True  # Default to global if neither is specified

    settings = load_settings()
    guild_id = GUILD_ID if args.is_guild is True else args.is_guild
    if args.is_guild and not guild_id:
        guild_id = settings.get("DISCORD_GUILD_ID")

    headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}

    if args.is_guild and not guild_id:
        print("Error: GUILD_ID must be set for guild-scoped commands.")
        return

    try:
        global_url = _get_command_url("global") if args.is_global else None
        guild_url = _get_command_url("guild", guild_id) if guild_id else None
    except ValueError as e:
        print(f"Error constructing URLs: {e}")
        return

    async with httpx.AsyncClient(timeout=10) as client:
        local_commands = build_commands_payload()

        urls = {
            "Global": global_url,
            "Guild": guild_url
        }

        if args.status:
            for scope, url in urls.items():
                if url:
                    registered_commands = await _fetch_commands(client, url, headers)
                    print_status(local_commands, registered_commands, scope)

        if args.register or args.unregister:
            action = "register" if args.register else "unregister"
            for scope, url in urls.items():
                if url:
                    registered_commands = await _fetch_commands(client, url, headers)
                    commands_to_process = await _validate_and_get_commands(local_commands, registered_commands, action)
                    await _process_commands(client, url, headers, commands_to_process, action)
                    await asyncio.sleep(2)  # Add delay to alleviate rate-limiting
                    registered_commands = await _fetch_commands(client, url, headers)
                    print_status(local_commands, registered_commands, scope)

if __name__ == "__main__":
    asyncio.run(main())
