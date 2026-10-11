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
        "OLLAMA_BASE_URL=http://ollama:11434\nOLLAMA_MODELS=qwen3:1.7b\nOLLAMA_FAST_MODEL=fast:2b\n"
        "OLLAMA_SMART_MODEL=smart:4b\nOLLAMA_ADULT_MODEL=adult:1b\nIMAGE_PROVIDERS=comfyui\n"
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
    for model in ("qwen3:1.7b", "fast:2b", "smart:4b", "adult:1b"):   # everything the .env refers to is downloaded
        assert f"ollama pull {model}" in calls, model


def _run_omniget(tmp_path, curl_body, env_extra=None):
    """Run deploy/install_omniget.sh with a fake curl. Returns (returncode, stderr+stdout, installed_path)."""
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    curl = bin_dir / "curl"
    curl.write_text("#!/usr/bin/env bash\n" + curl_body)
    curl.chmod(0o755)
    dest = tmp_path / "dest"
    dest.mkdir(exist_ok=True)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "OMNIGET_INSTALL_DIR": str(dest),
           "INSTALL_OMNIGET": "1", "TARGETARCH": "amd64", **(env_extra or {})}
    r = subprocess.run(["sh", str(ROOT / "deploy/install_omniget.sh")], env=env, capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout + r.stderr, dest / "omniget"


def test_omniget_install_never_fails_the_build(tmp_path):
    # default: skipped without touching the network
    rc, out, bin_path = _run_omniget(tmp_path, "exit 99\n", {"INSTALL_OMNIGET": "0"})
    assert rc == 0 and "skipped" in out and not bin_path.exists()
    # release archive does not exist (404) -> warning, exit 0
    rc, out, bin_path = _run_omniget(tmp_path, "exit 22\n")
    assert rc == 0 and "WARNING" in out and not bin_path.exists()
    # garbage instead of an archive -> warning, exit 0
    rc, out, bin_path = _run_omniget(tmp_path, 'echo "<html>not found</html>" > "$8"; exit 0\n')
    assert rc == 0 and "not a valid tar.gz" in out and not bin_path.exists()
    # unsupported arch -> skip
    rc, out, _ = _run_omniget(tmp_path, "exit 0\n", {"TARGETARCH": "riscv64"})
    assert rc == 0 and "unsupported arch" in out


def test_omniget_install_success_path(tmp_path):
    import io
    import tarfile

    payload = tmp_path / "payload.tar.gz"
    with tarfile.open(payload, "w:gz") as tar:
        data = b"#!/bin/sh\necho omniget 0.0.test\n"
        info = tarfile.TarInfo("release/omniget")
        info.size, info.mode = len(data), 0o755
        tar.addfile(info, io.BytesIO(data))
    rc, out, bin_path = _run_omniget(tmp_path, f'cp "{payload}" "$8"\n')
    assert rc == 0 and "installed" in out and bin_path.exists()


def test_dockerfile_has_no_hard_omniget_dependency():
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "install_omniget.sh" in docker and "INSTALL_OMNIGET=0" in docker
    assert "releases/download" not in docker and "curl -fL" not in docker
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert "INSTALL_OMNIGET: ${INSTALL_OMNIGET:-0}" in compose


def test_install_plan_mode_is_side_effect_free_and_informative(tmp_path):
    import os

    env = {**os.environ, "NO_COLOR": "1", "HOME": str(tmp_path)}
    r = subprocess.run(["bash", str(ROOT / "install.sh"), "--plan"], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "K I R A B O T" in out and "План установки" in out and "Итого свободного места" in out
    for item in ("Docker + Compose", "Qwen3.5 2B", "Piper", "ComfyUI", "OLLAMA_ADULT_MODEL"):
        assert item in out or "Картинки" in out, item
    assert "ничего не устанавливалось" in out
    assert list(tmp_path.iterdir()) == []  # no clone, no files


def test_install_spinner_reports_success_and_failure():
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    start = script.index("spin() {")
    end = script.index("\n}\n", start) + 3
    helpers = "R=;G=;Y=;C=;N=;\nok() { echo OK: $*; }\n" + script[start:end]
    good = subprocess.run(["bash", "-c", helpers + 'spin "работа" true; echo rc=$?'], capture_output=True, text=True, timeout=10)
    assert "OK: работа" in good.stdout and "rc=0" in good.stdout
    bad = subprocess.run(["bash", "-c", helpers + 'spin "падение" bash -c "echo boom >&2; exit 3"; echo rc=$?'],
                         capture_output=True, text=True, timeout=10)
    assert "rc=1" in bad.stdout and "boom" in bad.stderr and "ошибка" in bad.stderr


def _fake_docker_env(tmp_path, home):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "docker.log"
    for name, body in (("docker", f'echo "$@" >> {log}\nexit 0\n'), ("sudo", "exit 0\n"), ("systemctl", "exit 0\n")):
        f = bin_dir / name
        f.write_text("#!/usr/bin/env bash\n" + body)
        f.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home), "NO_COLOR": "1"}, log


def _make_project(tmp_path):
    import shutil

    proj = tmp_path / "newproj"
    proj.mkdir()
    for name in ("install.sh", "setup.sh", "example.env"):
        shutil.copy(ROOT / name, proj / name)
    shutil.copytree(ROOT / "tools", proj / "tools")
    (proj / "bot").mkdir()
    (proj / "bot/__init__.py").write_text("")
    return proj


def test_installer_finds_existing_env_elsewhere_and_never_asks(tmp_path):
    import hashlib

    home = tmp_path / "home"
    old = home / "Kira-old"
    old.mkdir(parents=True)
    env_text = ("TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789\nOWNER_ID=42\n"
                "OLLAMA_BASE_URL=http://ollama:11434\nOLLAMA_MODELS=qwen3:1.7b\n")
    (old / ".env").write_text(env_text)
    digest = hashlib.sha256((old / ".env").read_bytes()).hexdigest()
    env, log = _fake_docker_env(tmp_path, home)
    proj = _make_project(tmp_path)

    r = subprocess.run(["bash", str(proj / "install.sh")], cwd=proj, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "Нашёл готовый .env" in out and str(old / ".env") in out
    assert (proj / ".env").read_text() == env_text                     # used as is
    assert hashlib.sha256((old / ".env").read_bytes()).hexdigest() == digest  # original untouched
    assert "Вставь Telegram BOT TOKEN" not in out and "Telegram user ID" not in out  # never asked
    assert "up -d --build" in log.read_text()


def test_installer_uses_env_in_project_dir_and_explicit_env_file(tmp_path):
    env, log = _fake_docker_env(tmp_path, tmp_path / "home")
    (tmp_path / "home").mkdir()
    proj = _make_project(tmp_path)
    explicit = tmp_path / "elsewhere.env"
    explicit.write_text("TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789\nOWNER_ID=7\n")
    r = subprocess.run(["bash", str(proj / "install.sh")], cwd=proj, env={**env, "ENV_FILE": str(explicit)},
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (proj / ".env").read_text() == explicit.read_text()

    # .env already in the project folder: used as is, no copy from anywhere
    before = (proj / ".env").read_bytes()
    r2 = subprocess.run(["bash", str(proj / "install.sh")], cwd=proj, env=env, stdin=subprocess.DEVNULL,
                        capture_output=True, text=True, timeout=120)
    assert r2.returncode == 0 and (proj / ".env").read_bytes() == before
    assert "Использую существующий .env без вопросов" in r2.stdout


def test_installer_stops_instead_of_asking_when_env_has_no_token(tmp_path):
    env, _ = _fake_docker_env(tmp_path, tmp_path / "home")
    (tmp_path / "home").mkdir()
    proj = _make_project(tmp_path)
    (proj / ".env").write_text("OWNER_ID=42\n")
    r = subprocess.run(["bash", str(proj / "install.sh")], cwd=proj, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "нет TOKEN" in (r.stdout + r.stderr)
    assert (proj / ".env").read_text() == "OWNER_ID=42\n"
