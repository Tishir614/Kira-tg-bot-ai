import os
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    shutil.copy(ROOT / "https.sh", proj / "https.sh")
    shutil.copy(ROOT / "compose.yml", proj / "compose.yml")
    shutil.copytree(ROOT / "deploy", proj / "deploy")
    env = proj / ".env"
    env.write_text("TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789\nOWNER_ID=42\nKIRA_WEBAPP_URL=\n")
    os.chmod(env, 0o640)
    return proj, env


def _run(proj, *args):
    return subprocess.run(["bash", "https.sh", *args], cwd=proj, capture_output=True, text=True, timeout=30)


def test_dry_run_generates_https_files_without_touching_env(tmp_path):
    proj, env = _project(tmp_path)
    before = (env.read_bytes(), env.stat().st_mtime_ns, env.stat().st_mode)
    r = _run(proj, "kira.example.com", "me@example.com", "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (env.read_bytes(), env.stat().st_mtime_ns, env.stat().st_mode) == before
    assert sorted(p.name for p in proj.glob(".env*")) == [".env"]

    override = yaml.safe_load((proj / "compose.override.yml").read_text())
    kira_env = override["services"]["kira"]["environment"]
    assert kira_env["KIRA_WEBAPP_URL"] == "https://kira.example.com/kira"
    assert kira_env["DND_WEBAPP_URL"] == "https://kira.example.com/dnd"
    assert set(override["services"]) == {"kira", "nginx"}            # nothing else is touched
    assert set(override["volumes"]) == {"kira-letsencrypt", "kira-certbot-webroot"}  # new volumes only

    # the override replaces the nginx config mount of the base file (same container path)
    base = yaml.safe_load((ROOT / "compose.yml").read_text())
    base_targets = {v.split(":")[1] for v in base["services"]["nginx"]["volumes"]}
    assert "/etc/nginx/conf.d/default.conf" in base_targets
    assert any(v.endswith(":/etc/nginx/conf.d/default.conf:ro") for v in override["services"]["nginx"]["volumes"])
    for v in override["services"]["nginx"]["volumes"]:
        assert not v.startswith(("kira-persistent-data", "kira-data", "kira-redis"))

    conf = (proj / "deploy/nginx.generated.conf").read_text()
    assert "__DOMAIN__" not in conf and "kira.example.com" in conf
    assert "/etc/letsencrypt/live/kira.example.com/fullchain.pem" in conf
    assert "acme-challenge" in conf and "return 301 https://" in conf
    assert "TLSv1.2 TLSv1.3" in conf and "Strict-Transport-Security" in conf
    # admin panel stays private: only allow-listed public routes are proxied, the rest is 404
    assert "kira|dnd|commands|help|health" in conf
    assert conf.rstrip().endswith("return 404;\n    }\n}")
    assert "location = / {\n        return 302 /kira;" in conf


def test_remove_and_safety_rules(tmp_path):
    proj, env = _project(tmp_path)
    assert _run(proj, "kira.example.com", "me@example.com", "--dry-run").returncode == 0
    r = _run(proj, "--remove", "--dry-run")
    assert r.returncode == 0 and not (proj / "compose.override.yml").exists()
    assert not (proj / "deploy/nginx.generated.conf").exists()

    bad = _run(proj, "not a domain", "me@example.com", "--dry-run")
    assert bad.returncode != 0 and not (proj / "compose.override.yml").exists()
    assert _run(proj, "kira.example.com", "bad-email", "--dry-run").returncode != 0

    (proj / "compose.override.yml").write_text("services: {}\n")  # somebody else's file
    refused = _run(proj, "kira.example.com", "me@example.com", "--dry-run")
    assert refused.returncode != 0 and (proj / "compose.override.yml").read_text() == "services: {}\n"


def test_script_never_writes_env_or_data_volumes():
    raw = (ROOT / "https.sh").read_text(encoding="utf-8")
    text = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))  # code only, not comments
    for forbidden in ("down -v", "volume rm", "volume prune", "> .env", ">> .env", "sed -i", "rm -rf", "cat .env", "source .env"):
        assert forbidden not in text, forbidden
    for data_volume in ("kira-persistent-data", "kira-redis", "kira-ollama"):
        assert data_volume not in text
    gitignore = (ROOT / ".gitignore").read_text()
    assert "compose.override.yml" in gitignore and "deploy/nginx.generated.conf" in gitignore
