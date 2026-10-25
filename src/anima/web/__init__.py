"""The local web server: playground UI, platform webhooks (WeChat), and a health check."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from anima.adapters.playground import GROUP, PRIVATE
from anima.core.clock import Clock
from anima.core.markup import parse_reply

if TYPE_CHECKING:
    from anima.runtime import Runtime

STATIC = Path(__file__).parent / "static"


async def snapshot(runtime: Runtime) -> dict[str, Any]:
    brain = runtime.brain
    memory = brain.memory
    now = brain.clock.now()
    life = brain.life()
    mood = brain.mood.current()
    you = await memory.get_user("playground:pg-你")
    you_facts = await memory.facts("playground:pg-你", 12)
    return {
        "time": now.strftime("%H:%M"),
        "date": brain.clock.describe(now),
        "part": Clock.part_of_day(now),
        "night": now.hour >= 19 or now.hour < 6,
        "offset_hours": round(brain.clock.offset / 3600, 2),
        "life": {"activity": life.activity, "availability": life.availability, "energy": life.energy,
                 "insomnia": life.insomnia},
        "mood": {"label": brain.mood.label(life.energy), "valence": round(mood.valence, 3),
                 "arousal": round(mood.arousal, 3), "text": brain.mood.describe(life.energy), "recent": mood.recent},
        "plan": await memory.journal_get(brain.clock.today(), "plan"),
        "diaries": await memory.journal_list("diary", 6),
        "you": {"name": you.name, "call": you.call_name, "affinity": round(you.affinity, 2),
                "messages": you.msg_count, "facts": [f.content for f in you_facts]} if you else None,
        "self_facts": [f.content for f in await memory.facts("self", 10)],
        "treasures": await memory.treasures(8),
        "llm": {"provider": brain.llm.name, "model": brain.llm.model, "demo": brain.llm.name == "fake"},
        "cost": round(brain.cost, 4),
        "usage": brain.usage.__dict__,
        "fast": brain.humanizer.scale == 0,
        "name": brain.cfg.identity.display_name,
        "skills": [s.name for s in brain.skills],
        "platforms": sorted(brain.adapters),
    }


async def history(runtime: Runtime, chat_key: str, limit: int = 80) -> list[dict[str, Any]]:
    brain = runtime.brain
    rows = await brain.memory.recent(chat_key, limit)
    out = []
    for row in rows:
        item: dict[str, Any] = {"id": row.platform_msg_id, "self": row.is_self, "speaker": row.sender_name, "ts": row.ts}
        if row.is_self:
            parsed = parse_reply(row.text, brain.stickers, 5)
            bubble = parsed.bubbles[0] if parsed.bubbles else None
            pg = runtime.adapters.get("playground")
            item["segments"] = pg.segments(bubble) if bubble and pg else [{"type": "text", "value": row.text}]
            item["voice"] = bubble.voice if bubble else None
        else:
            item["text"] = row.text
        out.append(item)
    return out


def wake_offset(clock: Clock, target_hour: int = 20) -> float:
    """Hours to add to the clock so it reads `target_hour`:00 Beijing time today-ish."""
    real = clock.now().timestamp() - clock.offset
    current = clock.to_local(real)
    target = current.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    return (target.timestamp() - real) / 3600


def create_app(runtime: Runtime) -> FastAPI:
    app = FastAPI(title="Anima", docs_url=None, redoc_url=None)
    brain = runtime.brain
    playground = runtime.adapters.get("playground")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True, "bot": runtime.bot.key, "platforms": sorted(brain.adapters)})

    wechat = runtime.adapters.get("wechat")
    if wechat is not None and hasattr(wechat, "router"):
        app.include_router(wechat.router())

    if playground is None:
        return app

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))

    @app.get("/voice/{name}")
    async def voice(name: str):
        path = brain.bot.data_dir / "voice" / Path(name).name
        return FileResponse(path, media_type="audio/mpeg") if path.exists() else JSONResponse({}, status_code=404)

    @app.get("/api/state")
    async def state() -> JSONResponse:
        return JSONResponse(await snapshot(runtime))

    async def tick_life() -> None:
        with contextlib.suppress(Exception):
            await runtime.life.tick()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        playground.clients.add(ws)
        queue = brain.trace.subscribe()

        async def push_traces() -> None:
            while True:
                event = await queue.get()
                await ws.send_json({"type": "trace", **event})
                if event["kind"] in ("reply", "plan", "diary", "reflect", "wake", "decision"):
                    await ws.send_json({"type": "state", "state": await snapshot(runtime)})

        async def push_state() -> None:
            while True:
                await asyncio.sleep(20)
                await ws.send_json({"type": "state", "state": await snapshot(runtime)})

        tasks = [asyncio.create_task(push_traces()), asyncio.create_task(push_state())]
        try:
            await ws.send_json({
                "type": "hello",
                "state": await snapshot(runtime),
                "history": {PRIVATE.key: await history(runtime, PRIVATE.key),
                            GROUP.key: await history(runtime, GROUP.key)},
                "chats": {"private": PRIVATE.key, "group": GROUP.key},
                "traces": list(brain.trace.history)[-60:],
            })
            while True:
                msg = await ws.receive_json()
                kind = msg.get("type")
                if kind in ("say", "poke"):
                    await playground.receive(msg)
                elif kind == "clock":
                    brain.clock.set_offset_hours(float(msg.get("hours", 0)))
                    await tick_life()
                elif kind == "wake":
                    brain.clock.set_offset_hours(wake_offset(brain.clock, int(msg.get("hour", 20))))
                    await tick_life()
                elif kind == "fast":
                    brain.humanizer.scale = 0.0 if msg.get("on") else 1.0
                elif kind == "diary":
                    asyncio.create_task(runtime.life.write_diary(brain.clock.today()))
                elif kind == "plan":
                    asyncio.create_task(runtime.life.plan_day(brain.clock.today()))
                await ws.send_json({"type": "state", "state": await snapshot(runtime)})
        except WebSocketDisconnect:
            pass
        finally:
            playground.clients.discard(ws)
            brain.trace.unsubscribe(queue)
            for task in tasks:
                task.cancel()

    return app
