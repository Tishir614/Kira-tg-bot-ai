from __future__ import annotations

import asyncio
import hmac
import os
import json
import hashlib
import secrets
import time
import random
from urllib.parse import parse_qsl
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
import uvicorn

from bot import version
from bot.help_ui import PUBLIC_SECTIONS, ADMIN_SECTIONS
from bot.command_aliases import russian_usage
from bot.mini_app import KIRA_MINI_APP_HTML
from bot.dnd_app import DND_MINI_APP_HTML
from bot.ai_client import AIUnavailable, ai
from bot.config import settings
from bot.runtime import metrics
from bot.sql import (
    AuditLogManager,
    BlacklistManager,
    ChatManager,
    ChatSettingsManager,
    StatsManager,
    UserManager,
    EconomyManager,
    InventoryManager,
    NicknameManager,
    ProfileCustomizationManager,
    session_factory,
)
from bot.sql.orm_tables import Chat, Mem, RPTrigger, User, DndCharacter, DndCampaign, DndCampaignMember, DndRoll, MemoryPrivacy, LongTermMemory
from sqlalchemy import select


app = FastAPI(title="KiraBot Admin", version=version, docs_url=None, redoc_url=None, openapi_url=None)

def _telegram_user(init_data: str | None) -> int:
    """Validate Telegram WebApp initData and return authenticated user id."""
    if not init_data:
        raise HTTPException(401, "Telegram initData required")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", "")
    bot_token = settings.token
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    check = hmac.new(secret, "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs)).encode(), hashlib.sha256).hexdigest()
    if not received or not hmac.compare_digest(check, received):
        raise HTTPException(401, "Invalid Telegram initData")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        uid = int(json.loads(pairs["user"]).get("id"))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Malformed Telegram initData")
    if not uid or abs(time.time() - auth_date) > 86400:
        raise HTTPException(401, "Expired Telegram initData")
    return uid


@app.get("/commands", response_class=HTMLResponse)
@app.get("/help", response_class=HTMLResponse)
async def commands_site() -> str:
    """Iris-style searchable command catalog. /help is kept for old links."""
    from html import escape

    sections = PUBLIC_SECTIONS + ADMIN_SECTIONS
    command_count = sum(len(commands) for _, commands in sections)
    nav = []
    cards = []
    for index, (title, commands) in enumerate(sections):
        category = f"cat-{index}"
        nav.append(f'<button class="chip" data-target="{category}">{escape(title)}</button>')
        items = []
        for usage, description in commands:
            ru_usage = russian_usage(usage)
            search = escape(f"{title} {ru_usage} {description}", quote=True).casefold()
            items.append(
                '<article class="command" data-search="' + search + '">'
                '<div class="command-top"><code>' + escape(ru_usage) + '</code>'
                '<button class="copy" type="button" data-copy="' + escape(ru_usage, quote=True) + '">Копировать</button></div>'
                '<p>' + escape(description) + '</p></article>'
            )
        cards.append(
            f'<section class="group" id="{category}"><h2>{escape(title)}</h2>'
            '<div class="grid">' + ''.join(items) + '</div></section>'
        )

    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#171325"><title>Kira · Команды</title>
    <style>
    :root{{--bg:#15111f;--panel:#211a30;--panel2:#2a203b;--line:#544266;--ink:#fbf7ff;--muted:#bfb1cd;--accent:#c894ff;--gold:#ffd08a;color-scheme:dark;font-family:Inter,system-ui,-apple-system,sans-serif}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:radial-gradient(900px 520px at 8% -10%,#6d3f8355,transparent 62%),radial-gradient(760px 500px at 100% 15%,#35427844,transparent 63%),var(--bg);color:var(--ink);line-height:1.45}}main{{max-width:1120px;margin:auto;padding:24px 16px 90px}}header{{padding:22px 2px 18px}}.eyebrow{{color:var(--gold);font-size:12px;font-weight:850;letter-spacing:.12em;text-transform:uppercase}}h1{{font-size:clamp(2.2rem,7vw,4.3rem);line-height:.98;margin:8px 0 12px}}.lead{{max-width:720px;color:var(--muted);font-size:1.04rem}}.count{{display:inline-flex;padding:7px 11px;border:1px solid #ffffff18;border-radius:999px;background:#ffffff0a;color:#e5d8ef;font-size:13px}}.search-wrap{{position:sticky;top:0;z-index:5;padding:10px 0 12px;background:linear-gradient(var(--bg) 72%,transparent)}}input{{width:100%;padding:16px 18px;border-radius:17px;border:1px solid var(--line);background:#251d35ee;color:white;font-size:1rem;outline:none;box-shadow:0 10px 30px #0003}}input:focus{{border-color:var(--accent);box-shadow:0 0 0 3px #c894ff22}}.chips{{display:flex;gap:8px;overflow:auto;padding:2px 0 13px;scrollbar-width:none}}.chip,.copy{{border:0;color:var(--ink);cursor:pointer}}.chip{{white-space:nowrap;border:1px solid #ffffff16;border-radius:999px;background:#261d36;padding:10px 13px;font-weight:720}}.chip:hover{{background:#352748}}h2{{font-size:1.25rem;margin:30px 0 12px;color:#e8d4fa;scroll-margin-top:120px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:11px}}.command{{border:1px solid #ffffff12;border-radius:18px;background:linear-gradient(145deg,#282036dd,#20192de8);padding:16px;min-height:112px;box-shadow:0 12px 30px #0002}}.command:hover{{border-color:#c894ff44;transform:translateY(-1px)}}.command-top{{display:flex;gap:9px;align-items:flex-start;justify-content:space-between}}.command code{{font-size:.98rem;color:var(--gold);overflow-wrap:anywhere;word-break:break-word}}.command p{{margin:9px 0 0;color:#d2c6dc}}.copy{{flex:none;border-radius:10px;padding:7px 9px;background:#ffffff0d;color:#d8c9e5;font-size:12px}}.copy.copied{{color:#a9edbc;background:#73c88c1a}}#empty{{display:none;border:1px dashed var(--line);border-radius:18px;padding:28px;text-align:center;color:var(--muted);margin-top:20px}}footer{{margin-top:40px;padding:18px;border-radius:17px;background:#ffffff07;color:var(--muted)}}.group[hidden]{{display:none}}@media(max-width:520px){{main{{padding-left:12px;padding-right:12px}}.grid{{grid-template-columns:1fr}}.command{{min-height:auto}}}}
    </style></head><body><main><header><div class="eyebrow">🦊 Kira · справочник</div><h1>Команды Киры</h1><p class="lead">Отдельная страница команд в стиле каталога: категории, быстрый поиск и копирование в один тап. Основные названия теперь на русском.</p><span class="count">{command_count} команд · старые английские алиасы сохранены</span></header><div class="search-wrap"><input id="q" type="search" placeholder="Найти: память, картинка, мут, профиль…" autocomplete="off"></div><nav class="chips">{''.join(nav)}</nav><p id="empty">Ничего не найдено. Попробуй другое слово.</p>{''.join(cards)}<footer>💡 Telegram не разрешает публиковать кириллические команды в системном slash-меню, поэтому меню использует короткие латинские формы. Но вручную можно писать русские команды, например <b>/память</b>, <b>/картинка</b>, <b>/дайджест</b> и <b>/профиль</b>.</footer></main><script>
    const q=document.querySelector('#q'),cards=[...document.querySelectorAll('.command')],groups=[...document.querySelectorAll('.group')];
    function filter(){{const term=q.value.trim().toLocaleLowerCase('ru');let count=0;for(const card of cards){{card.hidden=!!term&&!card.dataset.search.includes(term);if(!card.hidden)count++}}for(const group of groups){{group.hidden=![...group.querySelectorAll('.command')].some(c=>!c.hidden)}}document.querySelector('#empty').style.display=count?'none':'block'}}
    q.addEventListener('input',filter);
    document.querySelectorAll('.chip').forEach(b=>b.addEventListener('click',()=>{{q.value='';filter();document.getElementById(b.dataset.target)?.scrollIntoView({{behavior:'smooth'}})}}));
    document.querySelectorAll('.copy').forEach(b=>b.addEventListener('click',async()=>{{try{{await navigator.clipboard.writeText(b.dataset.copy);b.textContent='Скопировано';b.classList.add('copied');setTimeout(()=>{{b.textContent='Копировать';b.classList.remove('copied')}},1200)}}catch(e){{b.textContent='Выдели команду'}}}}));
    </script></body></html>"""


@app.get("/dnd", response_class=HTMLResponse)
async def dnd_app() -> str:
    """Independent D&D UI: failures stay isolated from the main Kira Mini App."""
    return DND_MINI_APP_HTML


async def _dnd_user(request: Request) -> int:
    return _telegram_user(request.headers.get("X-Telegram-Init-Data"))

@app.get("/api/dnd/character")
async def dnd_character_get(request: Request):
    uid = await _dnd_user(request)
    async with session_factory() as session:
        row = (await session.scalars(select(DndCharacter).where(DndCharacter.user_id == uid).order_by(DndCharacter.id.desc()))).first()
    if row is None:
        return {"name": "", "level": 1, "hp": 10, "ac": 10, "stats": {x: 10 for x in ("STR", "DEX", "CON", "INT", "WIS", "CHA")}}
    try:
        data = json.loads(row.data or "{}")
    except (TypeError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("level", 1)
    data.setdefault("hp", 10)
    data.setdefault("ac", 10)
    data.setdefault("stats", {x: 10 for x in ("STR", "DEX", "CON", "INT", "WIS", "CHA")})
    return data | {"id": row.id, "name": row.name}

@app.put("/api/dnd/character")
async def dnd_character_put(request: Request):
    uid = await _dnd_user(request)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid character payload")
    allowed = {"name","race","subrace","class","subclass","gender","age","height","appearance","color_primary","color_secondary","markings","stats","skills","proficiencies","saving_throws","hp","ac","initiative","speed","level","xp","inventory","gold","spells","spell_slots","features","background","alignment","notes","portrait"}
    now = int(time.time())
    async with session_factory() as session:
        row = (await session.scalars(select(DndCharacter).where(DndCharacter.user_id == uid).order_by(DndCharacter.id.desc()))).first()
        existing: dict[str, Any] = {}
        if row:
            try:
                decoded = json.loads(row.data or "{}")
                if isinstance(decoded, dict):
                    existing = decoded
            except (TypeError, json.JSONDecodeError):
                existing = {}
        data = existing | {k: v for k, v in payload.items() if k in allowed}
        data["name"] = " ".join(str(data.get("name") or "Герой").split())[:120] or "Герой"
        data["level"] = max(1, min(20, int(data.get("level", 1) or 1)))
        data["hp"] = max(-999, min(9999, int(data.get("hp", 10) or 0)))
        data["ac"] = max(0, min(99, int(data.get("ac", 10) or 0)))
        data.setdefault("xp", 0)
        data.setdefault("stats", {x: 10 for x in ("STR", "DEX", "CON", "INT", "WIS", "CHA")})
        if row:
            row.name = data["name"]
            row.data = json.dumps(data, ensure_ascii=False)
            row.updated_at = now
        else:
            session.add(DndCharacter(user_id=uid, name=data["name"], data=json.dumps(data, ensure_ascii=False), updated_at=now))
        await session.commit()
    return {"ok": True, "character": data}

@app.post("/api/dnd/roll")
async def dnd_roll(request: Request):
    uid = await _dnd_user(request)
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError
        sides = max(2, min(100, int(payload.get("sides", 20))))
        modifier = max(-20, min(20, int(payload.get("modifier", 0))))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Некорректные параметры кубика") from exc
    mode = str(payload.get("mode", "normal"))
    if mode not in {"normal", "advantage", "disadvantage"}:
        mode = "normal"
    rolls = [random.randint(1, sides) for _ in range(2 if mode != "normal" else 1)]
    value = max(rolls) if mode == "advantage" else min(rolls) if mode == "disadvantage" else rolls[0]
    total = value + modifier
    async with session_factory() as session:
        session.add(DndRoll(user_id=uid, expression=f"d{sides}{modifier:+d}", result=total, detail=f"{rolls}", created_at=int(time.time())))
        await session.commit()
    return {"expression": f"d{sides}{modifier:+d}", "rolls": rolls, "result": total, "mode": mode}

@app.post("/api/dnd/campaigns")
async def dnd_campaign_create(request: Request):
    uid = await _dnd_user(request); body = await request.json(); now = int(time.time())
    async with session_factory() as session:
        code = secrets.token_urlsafe(5).upper()[:8]
        while (await session.scalars(select(DndCampaign).where(DndCampaign.code == code))).first(): code = secrets.token_urlsafe(5).upper()[:8]
        camp = DndCampaign(code=code, name=str(body.get("name", "Новая кампания"))[:160], dm_user_id=uid, data=json.dumps({"log":[],"quests":[],"notes":"","encounters":[]}, ensure_ascii=False), created_at=now)
        session.add(camp); await session.flush(); session.add(DndCampaignMember(campaign_id=camp.id,user_id=uid,role="dm",joined_at=now)); await session.commit()
    return {"id":camp.id,"code":code,"name":camp.name}

@app.post("/api/dnd/campaigns/join")
async def dnd_campaign_join(request: Request):
    uid = await _dnd_user(request); body = await request.json(); code = str(body.get("code", "")).upper().strip()
    async with session_factory() as session:
        camp=(await session.scalars(select(DndCampaign).where(DndCampaign.code==code))).first()
        if not camp: raise HTTPException(404,"Campaign not found")
        existing=(await session.scalars(select(DndCampaignMember).where(DndCampaignMember.campaign_id==camp.id,DndCampaignMember.user_id==uid))).first()
        if not existing: session.add(DndCampaignMember(campaign_id=camp.id,user_id=uid,role="player",joined_at=int(time.time()))); await session.commit()
    return {"ok":True,"campaign_id":camp.id,"name":camp.name}

@app.get("/api/dnd/campaigns")
async def dnd_campaigns(request: Request):
    uid=await _dnd_user(request)
    async with session_factory() as session:
        rows=(await session.scalars(select(DndCampaign).join(DndCampaignMember,DndCampaignMember.campaign_id==DndCampaign.id).where(DndCampaignMember.user_id==uid).order_by(DndCampaign.id.desc()))).all()
    return [{"id":x.id,"code":x.code,"name":x.name,"dm_user_id":x.dm_user_id} for x in rows]

@app.get("/api/dnd/campaigns/{campaign_id}")
async def dnd_campaign_detail(campaign_id: int, request: Request):
    uid = await _dnd_user(request)
    async with session_factory() as session:
        camp = await session.get(DndCampaign, campaign_id)
        member = (await session.scalars(select(DndCampaignMember).where(DndCampaignMember.campaign_id == campaign_id, DndCampaignMember.user_id == uid))).first()
        if not camp or not member: raise HTTPException(404, "Campaign not found")
        members = (await session.scalars(select(DndCampaignMember).where(DndCampaignMember.campaign_id == campaign_id))).all()
    try:
        state = json.loads(camp.data or "{}")
    except (TypeError, json.JSONDecodeError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    return {"id": camp.id, "name": camp.name, "code": camp.code, "role": member.role, "dm_user_id": camp.dm_user_id, "state": state, "members":[{"user_id":m.user_id,"role":m.role,"character_id":m.character_id} for m in members]}

@app.patch("/api/dnd/campaigns/{campaign_id}")
async def dnd_campaign_update(campaign_id: int, request: Request):
    uid = await _dnd_user(request); body = await request.json()
    async with session_factory() as session:
        camp = await session.get(DndCampaign, campaign_id)
        if not camp or camp.dm_user_id != uid: raise HTTPException(403, "DM access required")
        try:
            state = json.loads(camp.data or "{}")
        except (TypeError, json.JSONDecodeError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        # DM tools: journal, quests, encounter initiative, HP/conditions and loot.
        for key in ("log", "quests", "notes", "encounters", "initiative", "loot"):
            if key in body: state[key] = body[key]
        camp.data = json.dumps(state, ensure_ascii=False); await session.commit()
    return {"ok": True, "state": state}

@app.get("/api/dnd/rolls")
async def dnd_rolls(request: Request, limit: int = 30):
    uid = await _dnd_user(request); limit = max(1, min(limit, 100))
    async with session_factory() as session:
        rows = (await session.scalars(select(DndRoll).where(DndRoll.user_id == uid).order_by(DndRoll.id.desc()).limit(limit))).all()
    return [{"expression":r.expression,"result":r.result,"detail":r.detail,"created_at":r.created_at} for r in rows]


def _panel_token() -> str:
    return settings.panel_token


async def require_auth(authorization: str | None = Header(default=None), x_panel_token: str | None = Header(default=None)) -> None:
    token = _panel_token()
    if not token:
        raise HTTPException(status_code=503, detail="PANEL_TOKEN is not configured")
    supplied = x_panel_token or ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # The D&D Mini App is opened inside Telegram WebView/Web clients. It needs
    # Telegram's official Mini App SDK, and web.telegram.org may embed the page.
    # Keep the stricter frame policy for the admin panel and API paths.
    if request.url.path in {"/dnd", "/kira"}:
        # MutableHeaders has no .pop(); calling it caused every /dnd request
        # to end as HTTP 500 after the route itself had rendered successfully.
        # Nothing sets X-Frame-Options before this branch, so no deletion is needed.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline' https://telegram.org; "
            "img-src 'self' data:; connect-src 'self'; "
            "frame-ancestors https://web.telegram.org https://*.telegram.org"
        )
    else:
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """
<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>KiraBot Admin</title><style>
body{font-family:system-ui;background:#11131a;color:#eef;margin:0;padding:24px} .wrap{max-width:1000px;margin:auto}
.card{background:#1b1e29;border:1px solid #303549;border-radius:16px;padding:18px;margin:12px 0} input{background:#0d0f14;color:#fff;border:1px solid #444;padding:10px;border-radius:10px;width:100%;box-sizing:border-box}
button{background:#725cff;color:#fff;border:0;padding:10px 14px;border-radius:10px;margin-top:8px;cursor:pointer} pre{white-space:pre-wrap;word-break:break-word}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}.num{font-size:28px;font-weight:700}
</style></head><body><div class='wrap'><h1>🤖 KiraBot Admin</h1>
<div class='card'><b>Panel token</b><input id='token' type='password' placeholder='PANEL_TOKEN'><button onclick='loadAll()'>Обновить</button></div>
<div id='stats' class='grid'></div><div class='card'><h3>Последние действия</h3><pre id='logs'>—</pre></div>
<div class='card'><h3>Blacklist</h3><pre id='blacklist'>—</pre></div></div>
<script>
const h=()=>({'X-Panel-Token':document.getElementById('token').value});
async function j(url){let r=await fetch(url,{headers:h()}); if(!r.ok)throw new Error(await r.text()); return r.json()}
async function loadAll(){try{let s=await j('/api/stats');document.getElementById('stats').innerHTML=Object.entries(s).map(([k,v])=>`<div class='card'><div>${k}</div><div class='num'>${v}</div></div>`).join('');document.getElementById('logs').textContent=JSON.stringify(await j('/api/logs'),null,2);document.getElementById('blacklist').textContent=JSON.stringify(await j('/api/blacklist'),null,2)}catch(e){alert(e)}}
</script></body></html>
"""


@app.get("/health")
async def health() -> dict[str, str | int]:
    return {"status": "ok", "uptime": metrics.uptime}


@app.get("/api/stats", dependencies=[Depends(require_auth)])
async def stats() -> dict[str, int]:
    return await StatsManager.counts()


@app.get("/api/runtime", dependencies=[Depends(require_auth)])
async def runtime_stats() -> dict[str, int]:
    return {
        "uptime": metrics.uptime,
        "errors": metrics.errors,
        "ai_requests": metrics.ai_requests,
        "downloads": metrics.downloads,
        "searches": metrics.searches,
        "reminders_sent": metrics.reminders_sent,
        "backups_created": metrics.backups_created,
    }


@app.get("/api/users", dependencies=[Depends(require_auth)])
async def users(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    async with session_factory() as session:
        rows = list((await session.scalars(select(User).order_by(User.user_id.desc()).limit(limit))).all())
    return [{
        "user_id": x.user_id,
        "sudo": bool(x.sudo),
        "level": x.level,
        "xp": x.xp,
        "coins": x.coins,
        "daily_streak": x.daily_streak,
    } for x in rows]


@app.get("/api/chats", dependencies=[Depends(require_auth)])
async def chats(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    async with session_factory() as session:
        rows = list((await session.scalars(select(Chat).order_by(Chat.chat_id.desc()).limit(limit))).all())
    return [{"chat_id": x.chat_id, "admin_chat_id": x.admin_chat_id} for x in rows]


@app.get("/api/mems", dependencies=[Depends(require_auth)])
async def mems(limit: int = 200) -> list[dict[str, Any]]:
    async with session_factory() as session:
        rows = list((await session.scalars(select(Mem).order_by(Mem.id.desc()).limit(max(1, min(limit, 1000))))).all())
    return [{"id": x.id, "chat_id": x.chat_id, "sticker_id": x.sticker_id} for x in rows]


@app.get("/api/rp", dependencies=[Depends(require_auth)])
async def rp(limit: int = 200) -> list[dict[str, Any]]:
    async with session_factory() as session:
        rows = list((await session.scalars(select(RPTrigger).order_by(RPTrigger.id.desc()).limit(max(1, min(limit, 1000))))).all())
    return [{"id": x.id, "chat_id": x.chat_id, "trigger": x.trigger, "answer": x.answer, "type": x.type} for x in rows]


@app.get("/api/blacklist", dependencies=[Depends(require_auth)])
async def blacklist() -> list[dict[str, Any]]:
    rows = await BlacklistManager.list()
    return [{"id": x.id, "user_id": x.user_id, "chat_id": x.chat_id, "reason": x.reason, "created_at": x.created_at} for x in rows]


@app.post("/api/blacklist/{user_id}", dependencies=[Depends(require_auth)])
async def blacklist_add(user_id: int, chat_id: int = 0, reason: str = "panel") -> dict[str, bool]:
    import time
    await BlacklistManager.add(user_id, chat_id, reason, int(time.time()))
    return {"ok": True}


@app.delete("/api/blacklist/{user_id}", dependencies=[Depends(require_auth)])
async def blacklist_remove(user_id: int, chat_id: int = 0) -> dict[str, bool]:
    return {"ok": await BlacklistManager.remove(user_id, chat_id)}


@app.get("/api/chat/{chat_id}/settings", dependencies=[Depends(require_auth)])
async def chat_settings(chat_id: int) -> dict[str, Any]:
    row = await ChatSettingsManager.get(chat_id)
    return {
        "chat_id": row.chat_id,
        "anti_spam": row.anti_spam,
        "flood_limit": row.flood_limit,
        "flood_window": row.flood_window,
        "links_allowed": row.links_allowed,
        "ai_enabled": row.ai_enabled,
    }


@app.patch("/api/chat/{chat_id}/settings", dependencies=[Depends(require_auth)])
async def update_chat_settings(chat_id: int, anti_spam: bool | None = None, links_allowed: bool | None = None, ai_enabled: bool | None = None, flood_limit: int | None = None, flood_window: int | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if anti_spam is not None: values["anti_spam"] = anti_spam
    if links_allowed is not None: values["links_allowed"] = links_allowed
    if ai_enabled is not None: values["ai_enabled"] = ai_enabled
    if flood_limit is not None: values["flood_limit"] = max(3, min(flood_limit, 30))
    if flood_window is not None: values["flood_window"] = max(2, min(flood_window, 60))
    row = await ChatSettingsManager.update(chat_id, **values)
    return {k: getattr(row, k) for k in ("chat_id", "anti_spam", "flood_limit", "flood_window", "links_allowed", "ai_enabled")}


@app.get("/api/logs", dependencies=[Depends(require_auth)])
async def logs(limit: int = 100) -> list[dict[str, Any]]:
    rows = await AuditLogManager.recent(max(1, min(limit, 500)))
    return [{"id": x.id, "chat_id": x.chat_id, "actor_id": x.actor_id, "target_id": x.target_id, "action": x.action, "details": x.details, "created_at": x.created_at} for x in rows]


class WebPanelRuntime:
    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.server: uvicorn.Server | None = None

    async def start(self) -> None:
        # The same FastAPI process serves both the optional admin panel and the
        # Telegram D&D Mini App. D&D must stay available even when the admin
        # panel toggle is off. Admin API routes remain protected by PANEL_TOKEN.
        dnd_enabled = bool(os.getenv("KIRA_WEBAPP_URL", "").strip() or os.getenv("DND_WEBAPP_URL", "").strip() or os.getenv("HELP_URL", "").strip())
        if not settings.web_panel_enabled and not dnd_enabled:
            return
        if settings.web_panel_enabled and len(_panel_token()) < 24:
            raise RuntimeError("WEB_PANEL_ENABLED=1, но PANEL_TOKEN короче 24 символов")
        host = settings.web_panel_host
        port = settings.web_panel_port
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            loop="asyncio",
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        self.task = asyncio.create_task(self.server.serve(), name="kira-web-panel")

    async def stop(self) -> None:
        if self.server:
            self.server.should_exit = True
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.task.cancel()
            self.task = None


web_panel_runtime = WebPanelRuntime()

@app.get("/kira", response_class=HTMLResponse)
async def kira_mini_app() -> str:
    """Single-page Kira Mini App: profile, economy, D&D, commands and memory."""
    return KIRA_MINI_APP_HTML


KIRA_COSMETIC_SHOP = {
    "nick_color": ("🎨 Палитра ника", 750, "Любой HEX-цвет профиля; уровень 5 открывает это бесплатно."),
    "theme_midnight": ("🌌 Тема Midnight", 900, "Сине-ночная тема Mini App."),
    "theme_rose": ("🌹 Тема Rose", 900, "Розово-бордовая тема Mini App."),
    "theme_emerald": ("💚 Тема Emerald", 900, "Изумрудная тема Mini App."),
    "theme_amber": ("🟠 Тема Amber", 900, "Тёплая янтарная тема Mini App."),
    "title_vip": ("👑 Свой титул", 1250, "Произвольный титул до 48 символов; уровень 10 открывает бесплатно."),
    "badge_star": ("⭐ Значок звезды", 500, "Звезда рядом с ником в профиле."),
    "badge_fire": ("🔥 Огненный значок", 650, "Огненный значок профиля."),
}


@app.post("/api/kira/chat")
async def kira_chat_api(request: Request):
    uid = _telegram_user(request.headers.get("X-Telegram-Init-Data"))
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Invalid JSON") from exc
    message = str(body.get("message", "")).replace("\x00", "").strip()[:4000]
    if not message:
        raise HTTPException(400, "Пустое сообщение")
    try:
        answer = await asyncio.wait_for(ai.respond(message, user_id=uid, chat_id=-uid, remember=True), timeout=90)
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, "AI timeout") from exc
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "AI временно недоступен") from exc
    return {"answer": str(answer)[:12000]}


@app.get("/api/kira/me")
async def kira_me(request: Request):
    uid = _telegram_user(request.headers.get("X-Telegram-Init-Data"))
    async with session_factory() as session:
        user = await session.get(User, uid)
        privacy = await session.get(MemoryPrivacy, uid)
        memories = list((await session.scalars(
            select(LongTermMemory)
            .where(LongTermMemory.user_id == uid)
            .order_by(LongTermMemory.importance.desc(), LongTermMemory.updated_at.desc())
            .limit(12)
        )).all())
    if user is None:
        user = await UserManager.get(uid)
    nickname = await NicknameManager.get(uid, 0)
    inventory = await InventoryManager.list(uid)
    return {
        "level": int(getattr(user, "level", 1) or 1),
        "xp": int(getattr(user, "xp", 0) or 0),
        "coins": int(getattr(user, "coins", 0) or 0),
        "memory_count": len(memories),
        "profile": {
            "nickname": nickname or "",
            "gender": getattr(user, "gender", "unspecified") or "unspecified",
            "color": getattr(user, "profile_color", "#E8BDFF") or "#E8BDFF",
            "title": getattr(user, "profile_title", "") or "",
            "badge": getattr(user, "profile_badge", "🦊") or "🦊",
            "theme": getattr(user, "profile_theme", "violet") or "violet",
        },
        "inventory": [
            {"key": row.item_key, "quantity": int(row.quantity or 0)}
            for row in inventory
        ],
        "privacy": {
            "personal_memory": True if privacy is None else bool(privacy.personal_memory),
            "allow_group_history": True if privacy is None else bool(privacy.allow_group_history),
        },
        "memory": [{"key": row.key, "value": row.value[:500], "kind": row.kind} for row in memories],
    }


@app.put("/api/kira/profile")
async def kira_profile_update(request: Request):
    uid = _telegram_user(request.headers.get("X-Telegram-Init-Data"))
    body = await request.json()
    user = await UserManager.get(uid)
    level = max(1, int(user.level or 1))

    if "nickname" in body:
        nickname = NicknameManager.clean(str(body.get("nickname", "")))
        if nickname:
            try:
                await NicknameManager.set(uid, 0, nickname)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        else:
            await NicknameManager.delete(uid, 0)

    if "gender" in body:
        try:
            await ProfileCustomizationManager.set_gender(uid, str(body.get("gender", "")))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    if "color" in body:
        requested_color = str(body.get("color", "")).strip().upper()
        if requested_color and not requested_color.startswith("#"):
            requested_color = "#" + requested_color
        current_color = (getattr(user, "profile_color", "#E8BDFF") or "#E8BDFF").upper()
        if requested_color != current_color and level < 5 and not await InventoryManager.has(uid, "nick_color"):
            raise HTTPException(403, "Цвет ника открывается на 5 уровне или после покупки палитры.")
        try:
            await ProfileCustomizationManager.set_color(uid, requested_color)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    if "title" in body:
        title = str(body.get("title", "")).strip()
        current_title = (getattr(user, "profile_title", "") or "").strip()
        if title != current_title and title and level < 10 and not await InventoryManager.has(uid, "title_vip"):
            raise HTTPException(403, "Свой титул открывается на 10 уровне или после покупки.")
        await ProfileCustomizationManager.set_title(uid, title)

    if "badge" in body:
        badge = str(body.get("badge", "🦊")).strip()
        current_badge = (getattr(user, "profile_badge", "🦊") or "🦊").strip()
        required = {"🦊": None, "⭐": "badge_star", "🔥": "badge_fire"}.get(badge)
        if badge not in {"🦊", "⭐", "🔥"}:
            raise HTTPException(400, "Неизвестный значок")
        if badge != current_badge and required and not await InventoryManager.has(uid, required):
            raise HTTPException(403, "Сначала купи этот значок в магазине.")
        await ProfileCustomizationManager.set_badge(uid, badge)

    if "theme" in body:
        theme = str(body.get("theme", "violet")).strip().lower()
        current_theme = (getattr(user, "profile_theme", "violet") or "violet").strip().lower()
        if theme != current_theme and theme != "violet" and level < 15 and not await InventoryManager.has(uid, f"theme_{theme}"):
            raise HTTPException(403, "Эта тема открывается на 15 уровне или после покупки.")
        try:
            await ProfileCustomizationManager.set_theme(uid, theme)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return {"ok": True, "message": "Профиль сохранён ✦"}


@app.get("/api/kira/shop")
async def kira_shop(request: Request):
    uid = _telegram_user(request.headers.get("X-Telegram-Init-Data"))
    user = await UserManager.get(uid)
    rows = await InventoryManager.list(uid)
    owned = {row.item_key for row in rows if int(row.quantity or 0) > 0}
    level = max(1, int(user.level or 1))
    items = []
    for key, (name, price, description) in KIRA_COSMETIC_SHOP.items():
        free_by_level = (
            (key == "nick_color" and level >= 5)
            or (key == "title_vip" and level >= 10)
            or (key.startswith("theme_") and level >= 15)
        )
        items.append({
            "key": key,
            "name": name,
            "price": price,
            "description": description,
            "owned": key in owned or free_by_level,
            "free_by_level": free_by_level,
        })
    return {"coins": int(user.coins or 0), "level": level, "items": items}


@app.post("/api/kira/shop/{item_key}")
async def kira_shop_buy(item_key: str, request: Request):
    uid = _telegram_user(request.headers.get("X-Telegram-Init-Data"))
    item = KIRA_COSMETIC_SHOP.get(item_key)
    if item is None:
        raise HTTPException(404, "Товар не найден")
    user = await UserManager.get(uid)
    level = max(1, int(user.level or 1))
    free_by_level = (
        (item_key == "nick_color" and level >= 5)
        or (item_key == "title_vip" and level >= 10)
        or (item_key.startswith("theme_") and level >= 15)
    )
    if free_by_level or await InventoryManager.has(uid, item_key):
        return {"ok": True, "message": "У тебя это уже открыто."}
    name, price, _ = item
    ok = await EconomyManager.purchase_item(uid, item_key, price, int(time.time()))
    if not ok:
        raise HTTPException(402, "Не хватает монет")
    return {"ok": True, "message": f"Куплено: {name}"}


@app.get("/api/kira/commands")
async def kira_commands(request: Request):
    # Validate Telegram initData so this endpoint follows the same Mini App trust model.
    _telegram_user(request.headers.get("X-Telegram-Init-Data"))
    rows: list[dict[str, str]] = []
    for section, commands in PUBLIC_SECTIONS + ADMIN_SECTIONS:
        for usage, description in commands:
            rows.append({
                "section": section,
                "usage": russian_usage(usage),
                "description": description,
            })
    return {"commands": rows}


@app.put("/api/kira/privacy")
async def kira_privacy(request: Request):
    uid = _telegram_user(request.headers.get("X-Telegram-Init-Data"))
    body = await request.json()
    async with session_factory() as session:
        row = await session.get(MemoryPrivacy, uid)
        if row is None:
            row = MemoryPrivacy(user_id=uid)
            session.add(row)
        row.personal_memory = bool(body.get("personal_memory", row.personal_memory))
        row.allow_group_history = bool(body.get("allow_group_history", row.allow_group_history))
        row.updated_at = int(time.time())
        await session.commit()
    return {"ok": True}
