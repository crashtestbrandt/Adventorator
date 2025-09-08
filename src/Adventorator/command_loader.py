# src/Adventorator/command_loader.py
import importlib
import pkgutil

import Adventorator.commands as commands_pkg  # package


def load_all_commands() -> None:
    for m in pkgutil.iter_modules(commands_pkg.__path__, commands_pkg.__name__ + "."):
        importlib.import_module(m.name)
