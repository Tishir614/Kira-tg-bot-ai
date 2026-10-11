import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shell_scripts_have_valid_syntax():
    for name in ("setup.sh", "install.sh", "deploy.sh", "upgrade.sh"):
        subprocess.run(["bash", "-n", str(ROOT / name)], check=True)


def test_auto_mode_never_prompts_and_returns_defaults():
    setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
    start = setup.index("yesno() {")
    end = setup.index("\n}\n", start) + 3
    script = setup[start:end] + '''
export KIRA_AUTO=1
yesno "q" Y </dev/null && echo yes1 || echo no1
yesno "q" N </dev/null && echo yes2 || echo no2
'''
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10).stdout.split()
    assert out == ["yes1", "no2"]


def test_installer_keeps_keys_and_is_auto():
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
    assert "KIRA_AUTO=1" in install and ".env.backup-" in install and "rm -rf" not in install
    assert "down -v" not in install + setup
    assert 'KIRA_LOCAL_IMAGE:-0' in setup and "example.env" in setup


def test_keep_env_mode_does_not_modify_env(tmp_path):
    """Run setup.sh in KIRA_KEEP_ENV mode against a fake docker and prove .env is untouched."""
    import hashlib
    import os
    import shutil
    import stat

    proj = tmp_path / "proj"
    proj.mkdir()
    shutil.copy(ROOT / "setup.sh", proj / "setup.sh")
    shutil.copytree(ROOT / "tools", proj / "tools")
    shutil.copy(ROOT / "example.env", proj / "example.env")
    env_text = (
        "TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789\nOWNER_ID=42\n"
        "OLLAMA_BASE_URL=http://ollama:11434\nOLLAMA_MODELS=qwen3:1.7b\nIMAGE_PROVIDERS=comfyui\n"
    )
    (proj / ".env").write_text(env_text)
    os.chmod(proj / ".env", 0o640)  # deliberately not 600: must stay exactly as it is
    before = ((proj / ".env").read_bytes(), os.stat(proj / ".env").st_mtime_ns, stat.S_IMODE(os.stat(proj / ".env").st_mode))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    fake = bin_dir / "docker"
    fake.write_text(f'#!/usr/bin/env bash\necho "$@" >> {log}\nexit 0\n')
    fake.chmod(0o755)
    for tool in ("sudo", "systemctl"):
        t = bin_dir / tool
        t.write_text('#!/usr/bin/env bash\nexit 0\n')
        t.chmod(0o755)

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "KIRA_AUTO": "1", "KIRA_KEEP_ENV": "1"}
    result = subprocess.run(["bash", str(proj / "setup.sh")], cwd=proj, env=env, capture_output=True, text=True, timeout=60)
    after = ((proj / ".env").read_bytes(), os.stat(proj / ".env").st_mtime_ns, stat.S_IMODE(os.stat(proj / ".env").st_mode))
    assert after == before, result.stdout + result.stderr
    assert not list(proj.glob(".env.*")), "no backups/temp files should be created by setup.sh in keep mode"
    calls = log.read_text()
    assert "up -d --build" in calls and "--profile ollama" in calls and "--profile image" not in calls
    assert "pull ollama" in calls or "ollama pull" in calls
