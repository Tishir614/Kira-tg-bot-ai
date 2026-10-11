from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from aiogram import Router

from bot import log
from bot.plugins.manager import is_plugin_enabled


def get_plugin_router() -> Router:
    """Load modules from bot.plugins that expose ``router`` or ``setup(router)``.

    A broken optional plugin is logged and skipped instead of taking the bot down.
    """
    root = Router(name="plugins")
    package_path = Path(__file__).parent
    for module_info in pkgutil.iter_modules([str(package_path)]):
        if module_info.name.startswith("_") or module_info.name == "manager":
            continue
        if not is_plugin_enabled(module_info.name):
            log.info("Plugin disabled by KIRA_DISABLED_PLUGINS: %s", module_info.name)
            continue
        try:
            module = importlib.import_module(f"bot.plugins.{module_info.name}")
            plugin_router = getattr(module, "router", None)
            if isinstance(plugin_router, Router):
                root.include_router(plugin_router)
                log.info("Loaded plugin router: %s", module_info.name)
                continue
            setup = getattr(module, "setup", None)
            if callable(setup):
                setup(root)
                log.info("Loaded plugin setup: %s", module_info.name)
        except Exception:
            log.exception("Failed to load plugin %s", module_info.name)
    return root
