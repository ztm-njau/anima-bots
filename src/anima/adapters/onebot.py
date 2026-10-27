"""QQ (and any other OneBot v11 implementation) over a forward WebSocket.

Built for NapCat (``infra/napcat``), which also understands a few extensions used here:
``set_input_status`` (the "对方正在输入..." hint), ``group_poke`` / ``friend_poke``, and
``mark_*_msg_as_read``. They fail softly on implementations that lack them, so WeChat
bridges that speak OneBot v11 work with the same adapter (``platform = "wechat"``).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import random
import re
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import httpx
import websockets
from loguru import logger
from pydantic import BaseModel

from anima.adapters.base import Adapter
from anima.config import env
from anima.core.events import Bubble, Chat, Image, Incoming, Sender
from anima.core.voice import as_base64, synthesize

QQ_FACE_NAMES = {
    "13": "呲牙", "14": "微笑", "5": "流泪", "6": "害羞", "8": "睡", "9": "大哭", "66": "爱心", "76": "赞",
    "99": "鼓掌", "106": "委屈", "175": "卖萌", "178": "斜眼笑", "179": "doge", "182": "笑哭",
    "212": "托腮", "264": "捂脸", "270": "emm", "271": "吃瓜", "277": "汪汪", "307": "喵喵", "319": "比心",
}
def _id(value: str) -> int | str:
    """QQ ids are numbers; some WeChat bridges use strings like "xxx@chatroom"."""
    return int(value) if str(value).isdigit() else value


_BILI = re.compile(r"https?://(?:www\.|m\.)?(?:bilibili\.com/video/[^\s\"'?]+|b23\.tv/[0-9A-Za-z]+)")


class OneBotConfig(BaseModel):
    enabled: bool = False
    url: str = "ws://127.0.0.1:3001"
    token_env: str = "ONEBOT_TOKEN"
    groups: list[str | int] = []
    listen_groups: list[str | int] = []
    accept_friend_requests: bool = False  # legacy switch; friend_requests is the rule now
    friend_requests: str = "smart"  # accept | smart | owner | ignore
    group_invites: str = "owner"
    friend_keywords: list[str] = []
    input_status: bool = True
    download_images: bool = True


class OneBotAdapter(Adapter):
    capabilities = frozenset({"typing", "poke", "voice", "quote", "read", "image"})

    def __init__(self, cfg: dict[str, Any], platform: str = "qq"):
        super().__init__()
        self.platform = platform
        self.cfg = OneBotConfig.model_validate(cfg)
        self.speak_groups = {str(g) for g in self.cfg.groups}
        self.listen_groups = {str(g) for g in self.cfg.listen_groups}
        self.ws: Any = None
        self.self_id: str | None = None
        self.nickname = ""
        self._pending: dict[str, asyncio.Future] = {}
        self._sent_ids: deque[str] = deque(maxlen=500)
        self._ats: list[str] = []
        self._sticker = False
        self._task: asyncio.Task | None = None
        self.connected = asyncio.Event()

    # ------------------------------------------------------------ connection

    async def start(self, brain) -> None:
        await super().start(brain)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self.ws:
            await self.ws.close()

    async def _run(self) -> None:
        token = env(self.cfg.token_env)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        backoff = 2.0
        failures = 0
        while True:
            try:
                async with websockets.connect(self.cfg.url, additional_headers=headers, max_size=20 * 2**20) as ws:
                    self.ws = ws
                    backoff, failures = 2.0, 0
                    logger.info("[{}] connected to OneBot at {}", self.platform, self.cfg.url)
                    asyncio.create_task(self._hello())
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        asyncio.create_task(self._dispatch(data))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failures += 1
                if self.self_id is not None:
                    logger.warning("[{}] OneBot connection lost ({}); retrying in {:.0f}s", self.platform, exc, backoff)
                elif failures in (1, 5) or failures % 30 == 0:
                    # Before the first login this is the normal state: NapCat only opens its socket once QQ is in.
                    logger.info("[{}] waiting for NapCat at {} (QQ not logged in yet? scan with: uv run anima napcat qr)",
                                self.platform, self.cfg.url)
            finally:
                self.ws = None
                self.connected.clear()
            await asyncio.sleep(backoff)
            backoff = min(60.0, backoff * 1.8)

    async def _hello(self) -> None:
        try:
            info = await self.call("get_login_info")
            self.self_id = str(info.get("user_id"))
            self.nickname = info.get("nickname", "")
            self.connected.set()
            logger.info("[{}] logged in as {} ({})", self.platform, self.nickname, self.self_id)
        except Exception as exc:
            logger.warning("[{}] get_login_info failed: {}", self.platform, exc)

    async def call(self, action: str, **params: Any) -> dict[str, Any]:
        if not self.ws:
            raise ConnectionError("OneBot is not connected")
        echo = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[echo] = future
        try:
            await self.ws.send(json.dumps({"action": action, "params": params, "echo": echo}, ensure_ascii=False))
            resp = await asyncio.wait_for(future, timeout=20)
        finally:
            self._pending.pop(echo, None)
        if resp.get("status") == "failed" or resp.get("retcode", 0) not in (0, 1):
            raise RuntimeError(f"{action} failed: {resp.get('message') or resp.get('wording') or resp}")
        return resp.get("data") or {}

    async def _soft(self, action: str, **params: Any) -> None:
        """Extension calls: nice to have, never worth an error."""
        with contextlib.suppress(Exception):
            await self.call(action, **params)

    # ------------------------------------------------------------ inbound

    async def _dispatch(self, data: dict[str, Any]) -> None:
        echo = data.get("echo")
        if echo and echo in self._pending:
            if not self._pending[echo].done():
                self._pending[echo].set_result(data)
            return
        post_type = data.get("post_type")
        try:
            if post_type == "message":
                await self._on_message(data)
            elif post_type == "notice":
                await self._on_notice(data)
            elif post_type == "request":
                await self._on_request(data)
            elif post_type == "meta_event" and data.get("self_id") and not self.self_id:
                self.self_id = str(data["self_id"])
        except Exception:
            logger.exception("[{}] failed to handle event", self.platform)

    def _group_allowed(self, group_id: str) -> tuple[bool, bool]:
        """(visible to her at all, listen-only)."""
        if group_id in self.speak_groups:
            return True, False
        if group_id in self.listen_groups:
            return True, True
        return False, False

    async def _on_message(self, data: dict[str, Any]) -> None:
        self_id = str(data.get("self_id") or self.self_id or "")
        user_id = str(data.get("user_id", ""))
        if user_id == self_id:
            return
        sender_info = data.get("sender") or {}
        name = sender_info.get("card") or sender_info.get("nickname") or user_id
        if data.get("message_type") == "group":
            group_id = str(data.get("group_id"))
            visible, listen_only = self._group_allowed(group_id)
            if not visible:
                return
            chat = Chat(self.platform, "group", group_id, str(data.get("group_name") or ""))
        else:
            listen_only = False
            chat = Chat(self.platform, "private", user_id, name)

        self._ats, self._sticker = [], False
        text, images, mentions_me, reply_to = await self._parse_segments(data.get("message"), self_id)
        if not text and not images:
            return
        ats, sticker = self._ats, self._sticker
        reply_to_me = bool(reply_to and reply_to in self._sent_ids)
        if reply_to and not reply_to_me and self.brain is not None:  # her message from before a restart
            reply_to_me = await self.brain.memory.is_own_message(chat.key, reply_to)
        collect = sticker and self.brain is not None and random.random() < self.brain.cfg.behavior.collect_stickers
        if images and self.cfg.download_images and (chat.kind == "private" or mentions_me or collect):
            await self._download(images)
        ev = Incoming(
            chat=chat,
            sender=Sender(user_id, name, is_admin=sender_info.get("role") in ("owner", "admin")),
            text=text,
            message_id=str(data.get("message_id")) if data.get("message_id") is not None else None,
            mentions_me=mentions_me,
            reply_to_me=reply_to_me,
            images=images,
            meta={"listen_only": listen_only, "at": ats, "sticker": sticker,
                  "reply_to_other": bool(reply_to and not reply_to_me)},
        )
        assert self.brain is not None
        await self.brain.handle(ev)

    async def _parse_segments(self, message: Any, self_id: str) -> tuple[str, list[Image], bool, str | None]:
        if isinstance(message, str):  # CQ-code string format; keep it readable
            return re.sub(r"\[CQ:[^\]]+\]", "", message).strip(), [], f"[CQ:at,qq={self_id}]" in message, None
        parts: list[str] = []
        images: list[Image] = []
        mentions_me = False
        reply_to: str | None = None
        for seg in message or []:
            kind, d = seg.get("type"), seg.get("data") or {}
            if kind == "text":
                parts.append(d.get("text", ""))
            elif kind == "at":
                qq = str(d.get("qq", ""))
                if qq == self_id:
                    mentions_me = True
                    parts.append(f"@{self.brain.cfg.identity.display_name if self.brain else '我'} ")
                elif qq == "all":
                    parts.append("@全体成员 ")
                else:
                    self._ats.append(qq)
                    parts.append(f"@{d.get('name') or qq} ")
            elif kind == "reply":
                reply_to = str(d.get("id", ""))
            elif kind == "face":
                parts.append(f"[{QQ_FACE_NAMES.get(str(d.get('id')), '表情')}]")
            elif kind in ("mface", "marketface"):
                self._sticker = True
                if d.get("url"):
                    images.append(Image(url=d["url"]))
                parts.append(f"[表情包：{d['summary'].strip('[]')}]" if d.get("summary") else "[表情包]")
            elif kind == "image":
                images.append(Image(url=d.get("url") or d.get("file")))
                is_sticker = str(d.get("sub_type")) == "1" or bool(d.get("summary"))
                self._sticker = self._sticker or is_sticker
                parts.append("[表情包]" if is_sticker else "[图片]")
            elif kind == "record":
                parts.append("[语音]")
            elif kind == "video":
                parts.append("[视频]")
            elif kind == "file":
                parts.append(f"[文件 {d.get('name', '')}]")
            elif kind == "forward":
                parts.append("[聊天记录]")
            elif kind == "json":
                parts.append(self._describe_card(d.get("data", "")))
            elif kind == "poke":
                parts.append("（戳了戳你）")
        return "".join(parts).strip(), images, mentions_me, reply_to

    @staticmethod
    def _describe_card(raw: str) -> str:
        """Mini-program cards (often Bilibili shares) → something she can read and look up."""
        try:
            card = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return "[卡片]"
        blob = json.dumps(card, ensure_ascii=False)
        title = (card.get("meta", {}).get("detail_1", {}) or {}).get("desc") or card.get("prompt", "")
        link = _BILI.search(blob.replace("\\/", "/"))
        if link:
            return f"[分享了B站视频：{title} {link.group(0)}]"
        return f"[分享卡片：{title}]" if title else "[卡片]"

    async def _download(self, images: list[Image]) -> None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            for img in images[:3]:
                if not img.url or not img.url.startswith("http"):
                    continue
                try:
                    resp = await client.get(img.url)
                    if resp.status_code == 200 and len(resp.content) < 5 * 2**20:
                        img.data = base64.b64encode(resp.content).decode()
                        img.media_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
                        if not img.media_type.startswith("image/"):
                            img.media_type = "image/jpeg"
                except httpx.HTTPError:
                    pass

    async def _on_notice(self, data: dict[str, Any]) -> None:
        self_id = str(data.get("self_id") or self.self_id or "")
        notice = data.get("notice_type")
        if notice in ("group_recall", "friend_recall") and data.get("message_id") is not None:
            if str(data.get("user_id")) == self_id or self.brain is None:
                return
            if notice == "group_recall":
                chat = Chat(self.platform, "group", str(data.get("group_id")))
            else:
                chat = Chat(self.platform, "private", str(data.get("user_id")))
            await self.brain.retract(chat, str(data["message_id"]))
            return
        if notice == "notify" and data.get("sub_type") == "poke" and str(data.get("target_id")) == self_id:
            user_id = str(data.get("user_id"))
            if user_id == self_id:
                return
            group_id = data.get("group_id")
            if group_id is not None:
                visible, listen_only = self._group_allowed(str(group_id))
                if not visible or listen_only:
                    return
                chat = Chat(self.platform, "group", str(group_id))
            else:
                chat = Chat(self.platform, "private", user_id)
            name = await self._name_of(user_id, group_id)
            assert self.brain is not None
            await self.brain.handle(Incoming(chat, Sender(user_id, name), "", kind="poke", mentions_me=True))

    async def _on_request(self, data: dict[str, Any]) -> None:
        """Friend requests and group invites go to her owner-configured rules (core/admin.py)."""
        assert self.brain is not None
        kind = data.get("request_type")
        if kind == "group" and data.get("sub_type") != "invite":
            return  # someone asking to join a group she manages: not her call
        if kind not in ("friend", "group"):
            return
        user_id = str(data.get("user_id"))
        name = await self._name_of(user_id)
        await self.brain.admin.on_request(
            self.platform, kind, user_id, str(data.get("flag")), user_name=name,
            group_id=str(data["group_id"]) if data.get("group_id") else None,
            comment=str(data.get("comment") or ""), sub_type=str(data.get("sub_type") or ""),
        )

    async def answer_request(self, request: dict, approve: bool) -> bool:
        try:
            if request["kind"] == "friend":
                await self.call("set_friend_add_request", flag=request["flag"], approve=approve)
            else:
                await self.call("set_group_add_request", flag=request["flag"], sub_type=request["sub_type"] or "invite",
                                approve=approve)
        except Exception as exc:
            logger.warning("[{}] request {} failed: {}", self.platform, request["id"], exc)
            return False
        if approve and request["kind"] == "group" and request.get("group_id"):
            self.speak_groups.add(str(request["group_id"]))  # she was invited by her owner's choice
        return True

    async def remove_friend(self, user_id: str) -> bool:
        try:
            await self.call("delete_friend", user_id=_id(user_id))
            return True
        except Exception as exc:
            logger.warning("[{}] delete_friend failed: {}", self.platform, exc)
            return False

    async def leave_group(self, group_id: str) -> bool:
        try:
            await self.call("set_group_leave", group_id=_id(group_id))
            self.speak_groups.discard(str(group_id))
            return True
        except Exception as exc:
            logger.warning("[{}] set_group_leave failed: {}", self.platform, exc)
            return False

    async def _name_of(self, user_id: str, group_id: Any = None) -> str:
        try:
            if group_id is not None:
                info = await self.call("get_group_member_info", group_id=_id(str(group_id)), user_id=_id(user_id))
                return info.get("card") or info.get("nickname") or user_id
            info = await self.call("get_stranger_info", user_id=_id(user_id))
            return info.get("nickname") or user_id
        except Exception:
            return user_id

    # ------------------------------------------------------------ outbound

    def can_speak(self, chat: Chat) -> bool:
        return chat.kind == "private" or chat.id in self.speak_groups

    def _target(self, chat: Chat) -> tuple[str, dict[str, Any]]:
        if chat.kind == "group":
            return "send_group_msg", {"group_id": _id(chat.id)}
        return "send_private_msg", {"user_id": _id(chat.id)}

    async def send(self, chat: Chat, bubble: Bubble, quote: str | None = None) -> str | None:
        assert self.brain is not None
        segments: list[dict[str, Any]] = []
        if bubble.voice:
            path = await synthesize(bubble.voice, self.brain.bot.data_dir / "voice")
            if path:
                segments = [{"type": "record", "data": {"file": f"base64://{as_base64(path)}"}}]
            else:
                segments = [{"type": "text", "data": {"text": bubble.voice}}]
        else:
            if quote:
                segments.append({"type": "reply", "data": {"id": quote}})
            for seg in bubble.segments:
                if seg.type == "text":
                    segments.append({"type": "text", "data": {"text": seg.value}})
                elif seg.type == "sticker":
                    kind, value = self.brain.stickers.render(seg.value, self.platform)
                    if kind == "face":
                        segments.append({"type": "face", "data": {"id": value}})
                    elif value:
                        segments.append({"type": "text", "data": {"text": value}})
                elif seg.type == "image" and seg.path:
                    data_b64 = base64.b64encode(Path(seg.path).read_bytes()).decode()
                    segments.append({"type": "image", "data": {"file": f"base64://{data_b64}", "sub_type": 1}})
        if not segments:
            return None
        action, target = self._target(chat)
        data = await self.call(action, message=segments, **target)
        msg_id = str(data.get("message_id")) if data.get("message_id") is not None else None
        if msg_id:
            self._sent_ids.append(msg_id)
        return msg_id

    async def typing(self, chat: Chat, on: bool) -> None:
        if on and chat.kind == "private" and self.cfg.input_status:
            await self._soft("set_input_status", user_id=_id(chat.id), event_type=1)

    async def poke(self, chat: Chat, user_id: str) -> None:
        if chat.kind == "group":
            await self._soft("group_poke", group_id=_id(chat.id), user_id=_id(user_id))
        else:
            await self._soft("friend_poke", user_id=_id(user_id))

    async def mark_read(self, chat: Chat, ev: Incoming) -> None:
        if chat.kind == "group":
            await self._soft("mark_group_msg_as_read", group_id=_id(chat.id))
        else:
            await self._soft("mark_private_msg_as_read", user_id=_id(chat.id))
