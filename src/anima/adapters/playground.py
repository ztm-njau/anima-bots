"""The playground: a local chat window into the bot, plus a view of her inner state.

No account, no platform, no risk. A private chat with "你" and a simulated group where you
can speak as anyone, to see how she behaves when she isn't the centre of attention.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import WebSocket

from anima.adapters.base import Adapter
from anima.core.events import Bubble, Chat, Image, Incoming, Sender
from anima.core.voice import synthesize

PRIVATE = Chat("playground", "private", "you")
GROUP = Chat("playground", "group", "lab", "可乐的测试群")


class PlaygroundAdapter(Adapter):
    platform = "playground"
    capabilities = frozenset({"typing", "poke", "voice", "quote", "read"})

    def __init__(self) -> None:
        super().__init__()
        self.clients: set[WebSocket] = set()

    async def broadcast(self, event: dict[str, Any]) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(event)
            except Exception:
                self.clients.discard(ws)

    async def receive(self, payload: dict[str, Any]) -> None:
        assert self.brain is not None
        chat = GROUP if payload.get("mode") == "group" else PRIVATE
        speaker = (payload.get("speaker") or "你").strip()[:16] or "你"
        sender = Sender(f"pg-{speaker}", speaker)
        msg_id = uuid.uuid4().hex[:12]
        if payload.get("type") == "poke":
            ev = Incoming(chat, sender, "", kind="poke", mentions_me=True, message_id=msg_id)
        else:
            text = (payload.get("text") or "").strip()
            images = []
            data_url = payload.get("image") or ""
            if data_url.startswith("data:image/") and "," in data_url:
                head, b64 = data_url.split(",", 1)
                images.append(Image(data=b64, media_type=head[5:].split(";")[0]))
            if not text and not images:
                return
            alias = self.brain.cfg.identity.display_name
            ev = Incoming(chat, sender, text, message_id=msg_id, images=images,
                          mentions_me=f"@{alias}" in text)
        await self.broadcast({
            "type": "user_message", "chat": chat.key, "id": msg_id, "speaker": speaker,
            "text": ev.text, "kind": ev.kind, "image": payload.get("image"), "ts": time.time(),
        })
        await self.brain.handle(ev)

    def segments(self, bubble: Bubble) -> list[dict[str, str]]:
        assert self.brain is not None
        out = []
        for seg in bubble.segments:
            if seg.type == "text":
                out.append({"type": "text", "value": seg.value})
            elif seg.type == "sticker":
                out.append({"type": "sticker", "value": self.brain.stickers.emoji(seg.value), "key": seg.value})
            else:
                out.append({"type": "text", "value": f"[表情包:{seg.value}]"})
        return out

    async def send(self, chat: Chat, bubble: Bubble, quote: str | None = None) -> str | None:
        assert self.brain is not None
        msg_id = uuid.uuid4().hex[:12]
        voice_url = None
        if bubble.voice:
            path = await synthesize(bubble.voice, self.brain.bot.data_dir / "voice")
            voice_url = f"/voice/{path.name}" if path else None
        await self.broadcast({
            "type": "bubble", "chat": chat.key, "id": msg_id, "segments": self.segments(bubble),
            "voice": bubble.voice, "voice_url": voice_url, "quote": quote, "ts": time.time(),
        })
        return msg_id

    async def typing(self, chat: Chat, on: bool) -> None:
        await self.broadcast({"type": "typing", "chat": chat.key, "on": on})

    async def poke(self, chat: Chat, user_id: str) -> None:
        await self.broadcast({"type": "poke", "chat": chat.key, "by": "her"})

    async def mark_read(self, chat: Chat, ev: Incoming) -> None:
        await self.broadcast({"type": "read", "chat": chat.key, "id": ev.message_id})
