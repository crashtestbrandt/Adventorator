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

commands = [
    {
      "name": "roll",
      "description": "Roll dice, e.g., 2d6+3",
      "options": [
        {"name": "expr", "description": "Dice expression", "type": 3, "required": False},
        {"name": "advantage", "description": "Advantage", "type": 5, "required": False},
        {"name": "disadvantage", "description": "Disadvantage", "type": 5, "required": False},
      ]
    },
    {
      "name": "check",
      "description": "Ability check vs DC",
      "options": [
        {"name": "ability", "description":"STR/DEX/CON/INT/WIS/CHA", "type":3, "required":False},
        {"name": "score", "description":"Ability score (10 default)", "type":4, "required":False},
        {"name": "proficient", "description":"Proficient?", "type":5, "required":False},
        {"name": "expertise", "description":"Expertise?", "type":5, "required":False},
        {"name": "prof_bonus", "description":"Proficiency bonus", "type":4, "required":False},
        {"name": "dc", "description":"Difficulty Class", "type":4, "required":False},
        {"name": "advantage", "description":"Advantage", "type":5, "required":False},
        {"name": "disadvantage", "description":"Disadvantage", "type":5, "required":False},
      ]
    },
    {
      "name": "do",
      "description": "Interpret a player action with the shadow-mode narrator.",
      "options": [
        {
          "type": 3,  # STRING
          "name": "message",
          "description": "Describe what you attempt.",
          "required": True,
        }
      ]
    },
    {
      "name": "sheet",
      "description": "Character sheet operations",
      "options": [
        {
          "name": "create",
          "description": "Create or update a sheet from JSON",
          "type": 1,  # SUB_COMMAND
          "options": [
            {"name":"json","description":"JSON sheet payload","type":3,"required":True}
          ]
        },
        {
          "name": "show",
          "description": "Show a sheet by name",
          "type": 1,
          "options": [
            {"name":"name","description":"Character name","type":3,"required":True}
          ]
        }
      ]
    },
    {
        "name": "ooc",
        "description": "Speak with the narrator or say something out of character.",
        "options": [
            {
                "type": 3,  # STRING
                "name": "message",
                "description": "What you want to say or do.",
                "required": True,
            }
        ]
    }
]

async def main():
#    url = f"https://discord.com/api/v10/applications/{APP_ID}/guilds/{GUILD_ID}/commands"
    url = f"https://discord.com/api/v10/applications/{APP_ID}/commands"
    headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=10) as client:
        for cmd in commands:
            r = await client.post(url, headers=headers, content=orjson.dumps(cmd))
            if r.status_code == 201 or r.status_code == 200:
                print("Registered:", r.json().get("name", "<unknown>"), "status code: ", r.status_code)
            else:
                print(f"Failed to register command '{cmd.get('name', '<unknown>')}'. Status: {r.status_code}")
                print("Response:", r.text)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
