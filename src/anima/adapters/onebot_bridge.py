"""Share her QQ account with other OneBot v11 frameworks, plugins and all.

NoneBot2, Koishi, AstrBot, Yunzai and most QQ bot frameworks speak OneBot v11. With the bridge on,
Anima passes every event from NapCat on to them and their API calls back to NapCat, so their
whole plugin ecosystems run unchanged next to her persona:

- ``bridge_listen = 3010``: Anima acts as a OneBot server ("正向 WebSocket"). Point NoneBot
  (``ONEBOT_WS_URLS=["ws://127.0.0.1:3010"]``) or Koishi (adapter-onebot, protocol ``ws``) here.
- ``bridge_connect = ["ws://127.0.0.1:6199/ws"]``: Anima connects out ("反向 WebSocket") to
  frameworks that run a server, such as AstrBot (default port 6199) or NoneBot in reverse mode.

Messages that start with a ``bridge_prefixes`` character ("/" "#") are left to those frameworks:
she still remembers them but doesn't answer, so a command never gets two replies. Her own owner
commands and Anima plugin commands still go first. What the frameworks send through her account
is remembered as hers.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any

import websockets
from loguru import logger

from anima.config import env

if TYPE_CHECKING:
    from anima.adapters.onebot import OneBotAdapter

SEND_ACTIONS = {"send_msg", "send_group_msg", "send_private_msg"}


def plain_text(message: Any) -> str:
    if isinstance(message, str):
        import re

        return re.sub(r"\[CQ:[^\]]+\]", "", message).strip()
    parts = []
    for seg in message or []:
        kind, data = seg.get("type"), seg.get("data") or {}
        if kind == "text":
            parts.append(data.get("text", ""))
        elif kind == "image":
            parts.append("[图片]")
        elif kind == "face":
            parts.append("[表情]")
        elif kind == "record":
            parts.append("[语音]")
    return "".join(parts).strip()


class OneBotBridge:
    def __init__(self, adapter: OneBotAdapter):
        self.adapter = adapter
        cfg = adapter.cfg
        self.listen_port = cfg.bridge_listen
        self.connect_urls = list(cfg.bridge_connect)
        self.token = env(cfg.bridge_token_env) if cfg.bridge_token_env else None
        self.peers: set[Any] = set()
        self._server = None
        self._tasks: list[asyncio.Task] = []

    @property
    def active(self) -> bool:
        return bool(self.listen_port or self.connect_urls)

    async def start(self) -> None:
        if self.listen_port:
            self._server = await websockets.serve(self._accept, "127.0.0.1", self.listen_port, max_size=20 * 2**20)
            logger.info("[bridge] OneBot frameworks can connect to ws://127.0.0.1:{}", self.listen_port)
        for url in self.connect_urls:
            self._tasks.append(asyncio.create_task(self._connect(url)))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
        for peer in list(self.peers):
            with contextlib.suppress(Exception):
                await peer.close()

    # ------------------------------------------------------------ peers

    def _authorized(self, ws) -> bool:
        if not self.token:
            return True
        headers = ws.request.headers if getattr(ws, "request", None) else {}
        sent = (headers.get("Authorization") or "").removeprefix("Bearer ").removeprefix("Token ").strip()
        query = (ws.request.path if getattr(ws, "request", None) else "").partition("access_token=")[2].split("&")[0]
        return self.token in (sent, query)

    async def _accept(self, ws) -> None:
        if not self._authorized(ws):
            await ws.close(code=1008, reason="bad access token")
            return
        await self._serve(ws, "forward client")

    async def _connect(self, url: str) -> None:
        backoff = 3.0
        while True:
            headers = {"X-Client-Role": "Universal", "X-Self-ID": self.adapter.self_id or "0", "User-Agent": "Anima/OneBot-bridge"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            try:
                async with websockets.connect(url, additional_headers=headers, max_size=20 * 2**20) as ws:
                    backoff = 3.0
                    await self._serve(ws, url)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the framework may simply not be running yet
                logger.debug("[bridge] {} unavailable: {}", url, exc)
            await asyncio.sleep(backoff)
            backoff = min(60.0, backoff * 1.6)

    async def _serve(self, ws, label: str) -> None:
        self.peers.add(ws)
        logger.info("[bridge] {} connected", label)
        if self.adapter.self_id:
            await ws.send(json.dumps({"post_type": "meta_event", "meta_event_type": "lifecycle", "sub_type": "connect",
                                      "self_id": int(self.adapter.self_id), "time": 0}))
        try:
            async for raw in ws:
                with contextlib.suppress(json.JSONDecodeError):
                    asyncio.create_task(self._handle(ws, json.loads(raw)))
        finally:
            self.peers.discard(ws)
            logger.info("[bridge] {} left", label)

    async def _handle(self, ws, request: dict[str, Any]) -> None:
        action, params, echo = request.get("action", ""), request.get("params") or {}, request.get("echo")
        response = await self.adapter.call_raw(action, params)
        if echo is not None:
            response["echo"] = echo
        with contextlib.suppress(Exception):
            await ws.send(json.dumps(response, ensure_ascii=False))
        if action in SEND_ACTIONS and response.get("status") == "ok":
            await self._remember(action, params, response)

    async def _remember(self, action: str, params: dict[str, Any], response: dict[str, Any]) -> None:
        brain = self.adapter.brain
        text = plain_text(params.get("message"))
        if brain is None or not text:
            return
        group = params.get("group_id") if action != "send_private_msg" else None
        if action == "send_msg" and params.get("message_type") == "private":
            group = None
        key = f"{self.adapter.platform}:group:{group}" if group else f"{self.adapter.platform}:private:{params.get('user_id')}"
        msg_id = (response.get("data") or {}).get("message_id")
        await brain.memory.record(key, "self", brain.cfg.identity.display_name, text, is_self=True,
                                  ts=brain.clock.timestamp(), platform_msg_id=str(msg_id) if msg_id is not None else None)
        if msg_id is not None:
            self.adapter._sent_ids.append(str(msg_id))

    async def forward(self, event: dict[str, Any]) -> None:
        if not self.peers:
            return
        raw = json.dumps(event, ensure_ascii=False)
        for peer in list(self.peers):
            with contextlib.suppress(Exception):
                await peer.send(raw)
