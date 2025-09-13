#!/usr/bin/env python3
"""
Dynamic CLI that discovers Adventorator slash commands and runs the same handlers.

Examples:
  PYTHONPATH=./src python scripts/cli.py roll --expr 2d6+3 --advantage
  PYTHONPATH=./src python scripts/cli.py sheet create --json '{"name":"Aria"}'

This CLI does not mock Discord. It constructs an Invocation with a PrintResponder and
calls the command's handler directly.
"""
from __future__ import annotations

import asyncio
import inspect
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin

import click

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, all_commands
from Adventorator.config import load_settings
from Adventorator.llm import LLMClient
from Adventorator.logging import setup_logging


class PrintResponder:
    async def send(self, content: str, *, ephemeral: bool = False) -> None:  # pragma: no cover
        prefix = "(ephemeral) " if ephemeral else ""
        print(prefix + str(content))


def _click_type_for(annotation: Any):
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is None:
        # Plain types
        if annotation in (str, int, float):
            return {str: str, int: int, float: float}[annotation]
        if annotation is bool:
            return bool
        if inspect.isclass(annotation) and issubclass(annotation, Enum):
            choices = [e.value if isinstance(e.value, str) else e.name for e in annotation]  # type: ignore[arg-type]
            return click.Choice(choices, case_sensitive=False)
        # Fallback: string
        return str

    # Collections and unions -> fallback to string for simplicity
    if origin in (list, tuple, dict):
        return str

    # Optional/Union -> use the first arg type if simple, else str
    if origin in (Union, UnionType) and args:
        base = next((a for a in args if a is not type(None)), str)
        return _click_type_for(base)

    return str


def _params_from_model(option_model: type) -> list[click.Parameter]:
    params: list[click.Parameter] = []
    fields = getattr(option_model, "model_fields", {})
    # Special-case: if the model has exactly one required string field with no alias,
    # expose it as a positional argument (friendlier UX for commands like `do`/`ooc`).
    if len(fields) == 1:
        only_name, only_field = next(iter(fields.items()))
        only_ann = getattr(only_field, "annotation", str) or str
        only_required = getattr(only_field, "is_required", False)
        only_alias = getattr(only_field, "alias", None)
        if only_ann is str and only_required and not only_alias:
            params.append(click.Argument([only_name]))
            return params

    for name, field in fields.items():
        # Prefer alias if provided to keep external flag names stable (e.g., --json)
        alias = getattr(field, "alias", None)
        flag_key = (alias or name).replace("_", "-")
        opt_name = f"--{flag_key}"
        ann = getattr(field, "annotation", str) or str
        required = getattr(field, "is_required", False)
        default = getattr(field, "default", None)
        help_text = getattr(field, "description", None) or ""

        if ann is bool:
            params.append(
                click.Option([opt_name], is_flag=True, default=bool(default) if default is not None else False, help=help_text)
            )
            continue

        click_type = _click_type_for(ann)
        params.append(
            click.Option(
                [opt_name],
                type=click_type,
                required=required and default is None,
                default=default,
                show_default=default is not None,
                help=help_text,
            )
        )

    return params


def _make_click_command(name: str, option_model: type, handler, sub: str | None = None) -> click.Command:
    params = _params_from_model(option_model)

    def _callback(**kwargs: Any):
        async def _run():
            # pre-flight checks
            config_path = Path("config.toml")
            env_path = Path(".env")
            if not config_path.exists() and not env_path.exists():
                msg = click.style(
                    "WARNING: Could not find 'config.toml' or '.env' in the current directory.",
                    fg="yellow",
                    bold=True,
                )
                hint = "Continuing with default settings. Some features may be disabled."
                click.echo(f"{msg}\n{hint}", err=True)
                # We no longer raise an exception, allowing the script to continue using defaults.

            # Load settings and, if enabled, initialize an LLM client
            settings = None
            llm_client = None
            try:
                settings = load_settings()
            except Exception:
                settings = None

            # Initialize logging to mirror application behavior
            try:
                setup_logging(settings)
            except Exception:
                # Fallback to defaults if logging setup fails
                setup_logging(None)

            # Optionally initialize LLM client if enabled
            if settings and getattr(settings, "features_llm", False):
                try:
                    llm_client = LLMClient(settings)
                except Exception:
                    # Leave llm_client as None if initialization fails; handler will degrade
                    llm_client = None

            inv = Invocation(
                name=name,
                subcommand=sub,
                options=kwargs,
                user_id="1",
                channel_id="1",
                guild_id="1",
                responder=PrintResponder(),
                settings=settings,
                llm_client=llm_client,
            )
            opts = option_model.model_validate(kwargs)
            await handler(inv, opts)

        asyncio.run(_run())

    return click.Command(name=sub or name, params=params, callback=_callback)


def build_app() -> click.Group:
    load_all_commands()

    app = click.Group()
    bucket: dict[str, list] = {}
    for cmd in all_commands().values():
        bucket.setdefault(cmd.name, []).append(cmd)

    for name, cmds in bucket.items():
        subs = [c for c in cmds if c.subcommand]
        if subs:
            grp = click.Group(name=name)
            for c in subs:
                grp.add_command(_make_click_command(name, c.option_model, c.handler, c.subcommand))
            app.add_command(grp)
        else:
            c = cmds[0]
            app.add_command(_make_click_command(name, c.option_model, c.handler))

    return app


def main() -> None:  # pragma: no cover
    app = build_app()
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
