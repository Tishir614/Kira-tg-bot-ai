"""Light mode for weak servers: fewer extra model calls and tighter timeouts."""
from __future__ import annotations

import os


def _mem_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 / 1024
    except Exception:
        pass
    return 99.0


def light_mode() -> bool:
    """KIRA_LIGHT_MODE=1/0 forces it; default 'auto' turns it on for servers with < 6 GB RAM."""
    value = os.getenv("KIRA_LIGHT_MODE", "auto").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return _mem_gb() < 6.0


def web_timeout() -> float:
    return 3.0 if light_mode() else 7.0


def fold_batch() -> int:
    return 16 if light_mode() else 8


def rp_summary_every() -> int:
    return 16 if light_mode() else 8
