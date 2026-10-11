from pathlib import Path

from fluent.runtime import FluentResourceLoader, FluentLocalization

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

loader = FluentResourceLoader(str(LOCALES_DIR / "{locale}"))
l10n = FluentLocalization(
    locales=["ru"],
    resource_ids=["strings.ftl", "errors.ftl", "commands.ftl"],
    resource_loader=loader
)

def find(value_to_find, locale="ru"):
    localization_dict = {}
    for resource_id in l10n.resource_ids:
        file_path = LOCALES_DIR / locale / resource_id
        try:
            with file_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#") and not line.startswith("//"):
                        key, _ = line.split("=", 1)
                        key = key.strip()
                        localized_value = l10n.format_value(key)
                        localization_dict[key] = localized_value
        except FileNotFoundError:
            continue
    for key, val in localization_dict.items():
        if val == value_to_find:
            return key
    return None

def _(key_value: str, **kwargs):
    return l10n.format_value(key_value, kwargs)

def format_seconds(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if hours:
        parts.append(f"{hours}ч")
    if minutes:
        parts.append(f"{minutes}м")
    if secs or not parts:
        parts.append(f"{secs}с")

    return " ".join(parts)


