from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PluginInfo:
    name: str
    enabled: bool


def disabled_plugins() -> set[str]:
    return {x.strip().casefold() for x in os.getenv("KIRA_DISABLED_PLUGINS", "").split(",") if x.strip()}


def is_plugin_enabled(name: str) -> bool:
    return name.casefold() not in disabled_plugins()
