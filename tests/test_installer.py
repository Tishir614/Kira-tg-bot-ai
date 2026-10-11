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
