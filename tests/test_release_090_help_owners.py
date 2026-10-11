"""Regression checks for the public help site and stable owner identity."""
import asyncio
import importlib.util
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HelpAndOwnersTests(unittest.TestCase):
    def test_all_slash_commands_have_site_descriptions(self):
        catalog = (ROOT / "bot/help_ui.py").read_text(encoding="utf-8")
        covered = set(re.findall(r'\("/([a-z][a-z0-9_]*)', catalog))
        registered = set()
        for source in (ROOT / "bot/handlers").rglob("*.py"):
            for match in re.finditer(r"Command\(([^)]*)\)", source.read_text(encoding="utf-8")):
                registered.update(re.findall(r"""["']([a-z][a-z0-9_]*)["']""", match.group(1)))
        self.assertGreaterEqual(len(registered), 95)
        self.assertEqual(registered - covered, set())
        site = (ROOT / "bot/web_panel.py").read_text(encoding="utf-8")
        self.assertIn('PUBLIC_SECTIONS + ADMIN_SECTIONS', site)
        self.assertIn('@app.get("/help"', site)
        self.assertIn("escape(description)", site)

    def test_owner_binding_requires_primary_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            package = types.ModuleType("bot")
            package.__path__ = []
            config = types.ModuleType("bot.config")
            config.settings = types.SimpleNamespace(owner_id=11, data_dir=Path(directory))
            old = {key: sys.modules.get(key) for key in ("bot", "bot.config")}
            try:
                sys.modules["bot"] = package
                sys.modules["bot.config"] = config
                spec = importlib.util.spec_from_file_location("kira_owners_test", ROOT / "bot/owners.py")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.assertFalse(module.is_owner(22))
                asyncio.run(module.bind_owner(2, 22))
                self.assertFalse(module.is_owner(22))
                asyncio.run(module.bind_owner(2, 22, primary=True))
                self.assertTrue(module.is_owner(22))
                self.assertEqual(module._bindings()["2"], 22)
                self.assertEqual(module._bindings().get("3"), None)
                self.assertTrue(module.is_owner(11))
            finally:
                for key, value in old.items():
                    if value is None:
                        sys.modules.pop(key, None)
                    else:
                        sys.modules[key] = value


if __name__ == "__main__":
    unittest.main()
