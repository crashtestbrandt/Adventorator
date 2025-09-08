#!/usr/bin/env python3

import httpx, os, orjson, sys

from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from the project root .env file
project_root = Path(__file__).parent.parent  # TODO: this sucks, replace this with something better
env_path = project_root / ".env"

if not env_path.exists():
    print(f"Error: .env file not found at {env_path}")
    sys.exit(1)
load_dotenv(dotenv_path=env_path)

# Fetch required environment variables with error handling
try:
    APP_ID = os.environ["DISCORD_APP_ID"]
    BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
except KeyError as e:
    print(f"Error: Missing required environment variable: {e}")
    print(f"Path of .env file: {env_path}")
    print(f"contents of .env file: {env_path.read_text()}")
    sys.exit(1)

# Fetch optional environment variables with a default fallback
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", None)

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import all_commands
from pydantic.fields import FieldInfo
from typing import Any


def _map_pydantic_to_discord(field_name: str, f: FieldInfo) -> dict[str, Any]:
  # Discord types: 3=STRING, 4=INTEGER, 5=BOOLEAN, 10=NUMBER
  ann = f.annotation
  if ann in (int,):
    t = 4
  elif ann in (float,):
    t = 10
  elif ann in (bool,):
    t = 5
  else:
    t = 3
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
            "type": 1,  # SUB_COMMAND
            "name": c.subcommand,
            "description": c.description,
            "options": sc_opts,
          }
        )
      payload.append(
        {
          "name": name,
          "description": meta_by_name[name]["description"],
          "type": 1,
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
          "type": 1,
          "options": options,
        }
      )
  return payload

async def main():
  # url = f"https://discord.com/api/v10/applications/{APP_ID}/guilds/{GUILD_ID}/commands"
  url = f"https://discord.com/api/v10/applications/{APP_ID}/commands"
  headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
  async with httpx.AsyncClient(timeout=10) as client:
    for cmd in build_commands_payload():
      r = await client.post(url, headers=headers, content=orjson.dumps(cmd))
      if r.status_code in (200, 201):
        print("Registered:", r.json().get("name", "<unknown>"), "status code:", r.status_code)
      else:
        print(f"Failed to register command '{cmd.get('name', '<unknown>')}'. Status: {r.status_code}")
        print("Response:", r.text)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
