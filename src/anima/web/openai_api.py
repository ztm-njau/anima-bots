"""Claudette as an OpenAI-compatible "model", so other bot frameworks can use her whole brain.

AstrBot, NoneBot, Koishi, SillyTavern and anything else with an "OpenAI provider" setting can
point at ``http://<this mac>:8765/v1`` with model ``claudette``: each conversation keeps her
persona, memory, 世界书, mood and tools. Set ``ANIMA_API_KEY`` in .env to let other machines and
Docker containers in; without it only this computer may call.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from anima.core.events import Chat, Image, Incoming, Sender
from anima.core.policy import Decision
from anima.llm.registry import env_lookup

if TYPE_CHECKING:
    from anima.runtime import Runtime


def _text_and_images(content: Any) -> tuple[str, list[Image]]:
    if isinstance(content, str):
        return content, []
    texts, images = [], []
    for part in content or []:
        if part.get("type") == "text":
            texts.append(part.get("text", ""))
        elif part.get("type") == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            if url.startswith("data:") and "," in url:
                head, data = url.split(",", 1)
                images.append(Image(data=data, media_type=head[5:].split(";")[0]))
            elif url:
                images.append(Image(url=url))
    return "".join(texts), images


def openai_router(runtime: Runtime, is_local) -> APIRouter:
    router = APIRouter(prefix="/v1")
    brain = runtime.brain

    def check(request: Request) -> None:
        key = env_lookup("ANIMA_API_KEY")
        sent = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if key:
            if sent != key:
                raise HTTPException(401, "wrong ANIMA_API_KEY")
        elif not is_local(request.headers.get("host"), request.headers.get("origin")):
            raise HTTPException(403, "set ANIMA_API_KEY in .env to allow calls from other machines or containers")

    @router.get("/models")
    async def models(request: Request) -> dict[str, Any]:
        check(request)
        return {"object": "list", "data": [{"id": runtime.bot.key, "object": "model", "owned_by": "anima"}]}

    @router.post("/chat/completions")
    async def chat(request: Request, body: dict[str, Any] = Body(...)):
        check(request)
        messages = body.get("messages") or []
        last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        if last is None:
            raise HTTPException(400, "no user message")
        text, images = _text_and_images(last.get("content"))
        # One caller conversation = one chat in her memory. Frameworks usually send a user id.
        who = str(body.get("user") or last.get("name") or "")
        session = who or hashlib.sha1(json.dumps(messages[:1], ensure_ascii=False).encode()).hexdigest()[:12]
        chat = Chat("api", "private", session[:64], last.get("name") or "")
        sender = Sender(f"api-{session[:64]}", last.get("name") or "朋友")
        ev = Incoming(chat, sender, text, message_id=uuid.uuid4().hex[:10], images=images, mentions_me=True)
        await brain.memory.touch_user("api", sender.id, sender.name)
        await brain.memory.record(chat.key, ev.user_key, sender.name, ev.render(), platform_msg_id=ev.message_id)
        reply = await brain.compose(chat, [ev], Decision("reply", "有人通过其他机器人框架跟你说话"))
        lines = []
        for bubble in reply.bubbles:
            plain = "".join(s.value if s.type == "text" else brain.stickers.emoji(s.value) if s.type == "sticker" else ""
                            for s in bubble.segments) or (bubble.voice or "")
            if plain:
                lines.append(plain)
                await brain.memory.record(chat.key, "self", brain.cfg.identity.display_name, bubble.source or plain,
                                          is_self=True)
        content = "\n".join(lines)
        created, rid = int(time.time()), f"chatcmpl-{uuid.uuid4().hex[:16]}"
        if body.get("stream"):
            def events():
                chunk = {"id": rid, "object": "chat.completion.chunk", "created": created, "model": runtime.bot.key,
                         "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                done = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                yield f"data: {json.dumps(done, ensure_ascii=False)}\n\ndata: [DONE]\n\n"

            return StreamingResponse(events(), media_type="text/event-stream")
        return JSONResponse({
            "id": rid, "object": "chat.completion", "created": created, "model": runtime.bot.key,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    return router
