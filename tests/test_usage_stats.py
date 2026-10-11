import json
from bot.usage_stats import UsageStats


def test_usage_stats_roundtrip(tmp_path):
    s = UsageStats(tmp_path / "u.json")
    s.seen(111, 222); s.seen(111, 222); s.seen(333, 222)
    for _ in range(3):
        s.count("messages")
    s.count("commands"); s.count("cmd:image"); s.count("ai_ok", 2); s.count("img:horde"); s.count("mode:tech")
    for sec in (1, 2, 3, 4, 10):
        s.latency(sec)
    r = s.report(1)
    assert r["users"] == 2 and r["chats"] == 1 and r["counters"]["messages"] == 3
    assert r["lat_n"] == 5 and r["lat_max"] == 10 and abs(r["lat_avg"] - 4) < 1e-9
    text = s.render(1)
    assert "Активных пользователей: <b>2</b>" in text and "/image 1" in text and "horde 1" in text
    s.flush(force=True)
    raw = (tmp_path / "u.json").read_text()
    assert "111" not in raw and "222" not in raw  # ids are hashed
    again = UsageStats(tmp_path / "u.json")
    assert again.report(1)["users"] == 2


def test_stats_cleanup_and_corrupt_file(tmp_path):
    p = tmp_path / "u.json"
    p.write_text("{not json")
    s = UsageStats(p)
    assert s.report(7)["users"] == 0
    s.days["2000-01-01"] = {"counters": {}, "users": [], "chats": [], "lat": [], "lat_sum": 0, "lat_n": 0, "lat_max": 0}
    s.flush(force=True)
    assert "2000-01-01" not in json.loads(p.read_text())
