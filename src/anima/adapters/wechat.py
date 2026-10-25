"""WeChat via an official account (公众号) webhook: the compliant way to put her on WeChat.

WeChat expects a passive reply within 5 seconds and retries the same message up to three
times. She uses those retries as thinking time: the first attempts are held until WeChat
gives up on them, and the reply rides on the latest attempt (~14 s budget). Verified
accounts with an AppSecret also get a fallback through the customer-service message API.

For personal WeChat accounts, point a OneBot v11 bridge at the OneBot adapter instead
(``mode = "onebot_bridge"``); see docs/platforms/wechat.md.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request, Response
from loguru import logger
from pydantic import BaseModel

from anima.adapters.base import Adapter
from anima.config import env
from anima.core.events import Bubble, Chat, Incoming, Sender


class WeChatMPConfig(BaseModel):
    enabled: bool = False
    mode: str = "official_account"
    path: str = "/wechat/mp"
    token_env: str = "WECHAT_MP_TOKEN"
    app_id_env: str = "WECHAT_MP_APP_ID"
    app_secret_env: str = "WECHAT_MP_APP_SECRET"
    aes_key_env: str = "WECHAT_MP_AES_KEY"


class WeChatMPAdapter(Adapter):
    platform = "wechat"
    instant = True

    def __init__(self, cfg: dict[str, Any]):
        super().__init__()
        self.cfg = WeChatMPConfig.model_validate(cfg)
        self.token = env(self.cfg.token_env) or ""
        self.app_id = env(self.cfg.app_id_env) or ""
        self.app_secret = env(self.cfg.app_secret_env)
        aes_key = env(self.cfg.aes_key_env)
        self.crypto = None
        if aes_key and self.app_id:
            from wechatpy.crypto import WeChatCrypto

            self.crypto = WeChatCrypto(self.token, aes_key, self.app_id)
        self._attempts: dict[str, int] = {}
        self._replies: dict[str, asyncio.Future] = {}  # msg id -> final text
        self._outbox: dict[str, list[str]] = {}  # chat key -> bubbles being delivered
        self._chat_msg: dict[str, str] = {}  # chat key -> msg id currently being answered

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(self.cfg.path, self.verify, methods=["GET"])
        router.add_api_route(self.cfg.path, self.receive, methods=["POST"])
        return router

    async def verify(self, signature: str = "", timestamp: str = "", nonce: str = "", echostr: str = "") -> Response:
        from wechatpy.exceptions import InvalidSignatureException
        from wechatpy.utils import check_signature

        try:
            check_signature(self.token, signature, timestamp, nonce)
        except InvalidSignatureException:
            return Response(status_code=403)
        return Response(echostr, media_type="text/plain")

    async def receive(self, request: Request) -> Response:
        from wechatpy import create_reply, parse_message
        from wechatpy.exceptions import InvalidSignatureException
        from wechatpy.utils import check_signature

        q = request.query_params
        body = await request.body()
        try:
            check_signature(self.token, q.get("signature", ""), q.get("timestamp", ""), q.get("nonce", ""))
            if q.get("encrypt_type") == "aes" and self.crypto:
                body = self.crypto.decrypt_message(body, q.get("msg_signature", ""), q.get("timestamp", ""), q.get("nonce", ""))
        except (InvalidSignatureException, Exception) as exc:
            logger.warning("[wechat] rejected a request: {}", exc)
            return Response(status_code=403)

        msg = parse_message(body)
        msg_id = str(getattr(msg, "id", None) or f"{msg.source}:{getattr(msg, 'create_time', '')}")
        attempt = self._attempts.get(msg_id, 0) + 1
        self._attempts[msg_id] = attempt

        if attempt == 1:
            ev = self._to_event(msg, msg_id)
            if ev is None:
                return Response("success", media_type="text/plain")
            self._replies[msg_id] = asyncio.get_running_loop().create_future()
            self._chat_msg[ev.chat.key] = msg_id
            assert self.brain is not None
            asyncio.create_task(self.brain.handle(ev))

        future = self._replies.get(msg_id)
        if future is None:
            return Response("success", media_type="text/plain")
        try:
            text = await asyncio.wait_for(asyncio.shield(future), timeout=4.3)
        except TimeoutError:
            if attempt < 3:
                await asyncio.sleep(1.2)  # let this attempt lapse so WeChat retries
                return Response("", media_type="text/plain")
            asyncio.create_task(self._push_later(msg.source, future))
            return Response("success", media_type="text/plain")

        self._forget(msg_id)
        if not text:
            return Response("success", media_type="text/plain")
        xml = create_reply(text, msg).render()
        if q.get("encrypt_type") == "aes" and self.crypto:
            xml = self.crypto.encrypt_message(xml, q.get("nonce", ""), q.get("timestamp", ""))
        return Response(xml, media_type="application/xml")

    def _to_event(self, msg: Any, msg_id: str) -> Incoming | None:
        chat = Chat("wechat", "private", msg.source)
        sender = Sender(msg.source, "微信网友")
        meta = {"always_awake": True}  # people expect an official account to answer at 3 a.m.
        if msg.type == "text":
            return Incoming(chat, sender, msg.content, message_id=msg_id, meta=meta)
        if msg.type == "image":
            return Incoming(chat, sender, "[图片]", message_id=msg_id, meta=meta)
        if msg.type == "voice":
            text = getattr(msg, "recognition", None)
            return Incoming(chat, sender, text or "[语音]", message_id=msg_id, meta=meta)
        if msg.type == "event" and getattr(msg, "event", "") == "subscribe":
            return Incoming(chat, sender, "（刚刚关注了你）", kind="join", message_id=msg_id, meta=meta)
        return None

    def _forget(self, msg_id: str) -> None:
        self._replies.pop(msg_id, None)
        self._attempts.pop(msg_id, None)

    async def _push_later(self, openid: str, future: asyncio.Future) -> None:
        """Too slow for a passive reply: use the customer-service API if this account has one."""
        try:
            text = await asyncio.wait_for(future, timeout=60)
        except TimeoutError:
            return
        if not text or not (self.app_id and self.app_secret):
            logger.info("[wechat] reply was too slow for a passive reply and no AppSecret is set; dropped")
            return
        from wechatpy import WeChatClient

        try:
            await asyncio.to_thread(WeChatClient(self.app_id, self.app_secret).message.send_text, openid, text)
        except Exception as exc:
            logger.warning("[wechat] customer-service send failed: {}", exc)

    # ------------------------------------------------------------ brain → wechat

    async def send(self, chat: Chat, bubble: Bubble, quote: str | None = None) -> str | None:
        text = self.flatten(bubble) or (bubble.voice or "")
        self._outbox.setdefault(chat.key, []).append(text)
        return None

    async def typing(self, chat: Chat, on: bool) -> None:
        # The brain calls typing(off) when a reply is fully delivered: that's our cue to answer.
        if on:
            return
        msg_id = self._chat_msg.pop(chat.key, None)
        text = "\n".join(t for t in self._outbox.pop(chat.key, []) if t)
        future = self._replies.get(msg_id) if msg_id else None
        if future and not future.done():
            future.set_result(text)
