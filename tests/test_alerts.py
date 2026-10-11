from bot.alerts import AIHealthMonitor, COOLDOWN


def test_alert_and_recovery():
    m = AIHealthMonitor()
    for _ in range(9):
        m.record(False)
    assert m.evaluate(100.0) is None  # window not full yet
    m.record(False)
    assert m.evaluate(100.0) == "alert"
    assert m.evaluate(101.0) is None  # no repeat while in alert
    for _ in range(5):
        m.record(True)
    assert m.evaluate(110.0) == "recovered"
    for _ in range(10):
        m.record(False)
    assert m.evaluate(200.0) is None  # cooldown
    assert m.evaluate(100.0 + COOLDOWN + 1) == "alert"


def test_no_alert_on_sporadic_failures():
    m = AIHealthMonitor()
    for i in range(30):
        m.record(i % 3 != 0)
    assert m.evaluate(1.0) is None


def test_merge_env_preserves_existing_keys():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from merge_env import merge
    old = "TOKEN=abc\nGROQ_API_KEY=secret\nIMAGE_PROVIDERS=comfyui\n"
    new = merge(old, (Path(__file__).resolve().parents[1] / "example.env").read_text())
    assert new.startswith(old) and new.count("IMAGE_PROVIDERS") == 1 and "HORDE_API_KEY=0000000000" in new
