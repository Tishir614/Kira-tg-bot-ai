import asyncio
import io

import pytest

from bot import horde_client as hc

MODELS = [{"name": "Fluffyrock Unbound", "count": 2}, {"name": "Pony Diffusion XL", "count": 1},
          {"name": "Deliberate", "count": 3}]


class Resp:
    def __init__(self, data=None, status=200, raw=b"", ctype="image/webp"):
        self._d, self.status, self._raw, self.headers = data, status, raw, {"Content-Type": ctype}

    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def json(self, content_type=None): return self._d
    async def text(self): return str(self._d)
    async def read(self): return self._raw


class FakeHorde:
    """Scriptable Horde: `submit_replies` is consumed one per POST /generate/async."""

    def __init__(self, submit_replies, check_replies=None, models=None, image=b"IMG"):
        self.submit_replies = list(submit_replies)
        self.check_replies = list(check_replies or [])
        self.models = MODELS if models is None else models
        self.image = image
        self.submitted, self.deleted = [], 0

    def request(self, method, url, **kw):
        if url.endswith("/status/models"):
            return Resp(self.models)
        if method == "POST" and url.endswith("/generate/async"):
            self.submitted.append(kw["json"])
            reply = self.submit_replies.pop(0)
            return Resp(reply[1], status=reply[0])
        if "/generate/check/" in url:
            return Resp(self.check_replies.pop(0) if self.check_replies else {"done": True})
        if method == "DELETE":
            self.deleted += 1
            return Resp({})
        return Resp({"generations": [{"img": "https://r2/x.webp", "censored": False}]})

    def get(self, url, **kw):
        return Resp(raw=self.image)


@pytest.fixture
def horde(monkeypatch):
    async def no_sleep(*a, **k): return None
    monkeypatch.setattr(hc.asyncio, "sleep", no_sleep)
    client = hc.AIHorde()
    client.key = hc.ANON_KEY

    def install(fake):
        async def get(): return fake
        monkeypatch.setattr(hc.http_client, "get", get)
        return client
    return install


def run(client, **kw):
    return asyncio.run(client.generate("anthro fox, beach", negative="bad anatomy, child", **kw))


def test_anonymous_request_is_clamped_and_sd15_preferred(horde):
    fake = FakeHorde([(202, {"id": "J"})])
    client = horde(fake)
    data, ctype = run(client, size=(512, 768))
    p = fake.submitted[0]
    assert data == b"IMG"
    assert p["params"]["width"] * p["params"]["height"] <= 512 * 512 and p["params"]["steps"] <= 25
    assert p["models"] == ["Fluffyrock Unbound"]               # SD1.5 furry model, not the XL one
    assert p["params"]["clip_skip"] == 2
    assert "child" not in p["prompt"] and p["nsfw"] is True and p["censor_nsfw"] is False


def test_kudos_upfront_triggers_minimal_retry(horde):
    fake = FakeHorde([(403, {"message": "Due to heavy demand, anonymous requests are limited", "rc": "KudosUpfront"}),
                      (202, {"id": "J"})])
    client = horde(fake)
    assert run(client)[0] == b"IMG"
    assert len(fake.submitted) == 2
    second = fake.submitted[1]["params"]
    assert (second["width"], second["height"], second["steps"]) == (512, 512, 20)


def test_no_worker_error_falls_back_to_general_models(horde):
    fake = FakeHorde([(400, {"message": "No active worker found for this request.", "rc": "NoValidWorkers"}),
                      (202, {"id": "J"})])
    client = horde(fake)
    assert run(client)[0] == b"IMG"
    assert fake.submitted[0]["models"] == ["Fluffyrock Unbound"] and fake.submitted[1]["models"] == ["Deliberate"]


def test_is_possible_false_retries_with_general_models_and_cancels_job(horde):
    fake = FakeHorde([(202, {"id": "A"}), (202, {"id": "B"})], check_replies=[{"is_possible": False}, {"done": True}])
    client = horde(fake)
    assert run(client)[0] == b"IMG"
    assert fake.deleted == 1 and fake.submitted[1]["models"] == ["Deliberate"]


def test_rate_limit_is_waited_out(horde):
    fake = FakeHorde([(429, {"message": "Too many parallel requests", "rc": "TooManyPrompts"}), (202, {"id": "J"})])
    client = horde(fake)
    assert run(client)[0] == b"IMG" and len(fake.submitted) == 2


def test_censored_result_is_retried_once(horde):
    class CensoredOnce(FakeHorde):
        calls = 0
        def request(self, method, url, **kw):
            if "/generate/status/" in url and method == "GET":
                CensoredOnce.calls += 1
                return Resp({"generations": [{"img": "https://r2/x.webp", "censored": CensoredOnce.calls == 1}]})
            return super().request(method, url, **kw)
    fake = CensoredOnce([(202, {"id": "A"}), (202, {"id": "B"})])
    client = horde(fake)
    assert run(client)[0] == b"IMG" and len(fake.submitted) == 2


def test_hard_errors_are_reported_not_retried_forever(horde):
    fake = FakeHorde([(401, {"message": "Wrong API key", "rc": "InvalidAPIKey"})])
    client = horde(fake)
    with pytest.raises(hc.HordeError, match="InvalidAPIKey"):
        run(client)
    assert len(fake.submitted) == 1
    fake2 = FakeHorde([], models=[])
    with pytest.raises(hc.HordeError, match="нет активных"):
        run(horde(fake2))


def test_webp_is_converted_to_jpeg(horde):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (8, 8), (255, 0, 0, 128)).save(buf, "WEBP")
    fake = FakeHorde([(202, {"id": "J"})], image=buf.getvalue())
    data, ctype = run(horde(fake))
    assert ctype == "image/jpeg" and data[:3] == b"\xff\xd8\xff"


def test_clamp_and_key_modes():
    assert hc.clamp_for_anonymous(512, 768, 28)[2] == 25
    w, h, _ = hc.clamp_for_anonymous(768, 512, 28)
    assert w * h <= 512 * 512 and w % 64 == 0 and h % 64 == 0 and w > h
    assert hc.clamp_for_anonymous(512, 512, 20) == (512, 512, 20)


def test_probe_uses_dry_run_and_reports_rejection(horde):
    fake = FakeHorde([(200, {"kudos": 7})])
    client = horde(fake)
    ok, msg = asyncio.run(client.probe())
    assert ok and "тестовый запрос принят" in msg and "7 kudos" in msg
    assert fake.submitted[0]["dry_run"] is True and fake.submitted[0]["params"]["width"] * fake.submitted[0]["params"]["height"] <= 512 * 512

    fake2 = FakeHorde([(403, {"message": "anonymous limit", "rc": "KudosUpfront"})])
    ok, msg = asyncio.run(horde(fake2).probe())
    assert not ok and "KudosUpfront" in msg
