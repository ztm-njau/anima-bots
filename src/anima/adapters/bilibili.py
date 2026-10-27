"""Bilibili: private messages, replies and @-mentions, live-room danmaku, and dynamics.

Uses bilibili-api-python with a cookie credential from ``anima login bilibili`` (QR scan),
stored in ``data/<bot>/secrets/bilibili.json``. Polls gently with jitter; Bilibili has no
push channel for DMs or notifications on the web.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel

from anima.adapters.base import Adapter
from anima.core.events import Bubble, Chat, Incoming, Sender

CREDENTIAL_FIELDS = ("sessdata", "bili_jct", "buvid3", "buvid4", "dedeuserid", "ac_time_value")


class BilibiliConfig(BaseModel):
    enabled: bool = False
    private_messages: bool = True
    replies_and_mentions: bool = True
    live_rooms: list[int] = []
    post_diary: bool = False
    poll_seconds: float = 25.0


def credential_path(secrets_dir: Path) -> Path:
    return secrets_dir / "bilibili.json"


MISSING = ("The Bilibili adapter needs bilibili-api-python (GPL-3.0-or-later), kept out of Anima's own "
           "dependencies: `uv sync` installs it, or `pip install bilibili-api-python qrcode`.")


def available() -> bool:
    try:
        import bilibili_api  # noqa: F401
    except ImportError:
        return False
    return True


def load_credential(secrets_dir: Path):
    from bilibili_api import Credential

    path = credential_path(secrets_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return Credential(**{k: data.get(k) for k in CREDENTIAL_FIELDS})


def save_credential(secrets_dir: Path, credential) -> Path:
    path = credential_path(secrets_dir)
    data = {k: getattr(credential, k, None) for k in CREDENTIAL_FIELDS}
    path.write_text(json.dumps(data, indent=2))
    path.chmod(0o600)
    return path


async def qr_login(secrets_dir: Path) -> Path:
    """Interactive QR login in the terminal. Scan with the Bilibili app."""
    if not available():
        raise RuntimeError(MISSING)
    from bilibili_api import login_v2

    qr = login_v2.QrCodeLogin()
    await qr.generate_qrcode()
    print(qr.get_qrcode_terminal())
    print("用 B 站 App 扫描上面的二维码（建议用给可乐准备的小号）……")
    last = None
    while not qr.has_done():
        state = await qr.check_state()
        if state != last:
            print({"SCAN": "等待扫码", "CONF": "已扫码，请在手机上确认", "TIMEOUT": "二维码过期了，请重试",
                   "DONE": "登录成功"}.get(state.name, state.name))
            last = state
        if state.name == "TIMEOUT":
            raise TimeoutError("QR code expired")
        await asyncio.sleep(2)
    return save_credential(secrets_dir, qr.get_credential())


class BilibiliAdapter(Adapter):
    platform = "bilibili"
    capabilities = frozenset({"dynamic"})

    def __init__(self, cfg: dict[str, Any], secrets_dir: Path):
        super().__init__()
        self.cfg = BilibiliConfig.model_validate(cfg)
        self.secrets_dir = secrets_dir
        self.credential = None
        self.self_uid: int | None = None
        self._tasks: list[asyncio.Task] = []
        self._names: dict[int, str] = {}
        self._comment_targets: dict[str, dict[str, Any]] = {}
        self._rooms: dict[int, Any] = {}
        self._last_danmaku: dict[int, float] = {}

    async def start(self, brain) -> None:
        await super().start(brain)
        if not available():
            logger.error("[bilibili] {}", MISSING)
            return
        self.credential = load_credential(self.secrets_dir)
        if not self.credential:
            logger.error("[bilibili] not logged in. Run: uv run anima login bilibili")
            return
        brain.bilibili_credential = self.credential
        self.self_uid = int(self.credential.dedeuserid or 0)
        self._tasks.append(asyncio.create_task(self._keep_fresh()))
        if self.cfg.private_messages or self.cfg.replies_and_mentions:
            self._tasks.append(asyncio.create_task(self._poll_loop()))
        for room in self.cfg.live_rooms:
            self._tasks.append(asyncio.create_task(self._live(room)))
        logger.info("[bilibili] running as uid {}", self.self_uid)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for room in self._rooms.values():
            try:
                await room.disconnect()
            except Exception:
                pass

    async def _keep_fresh(self) -> None:
        while True:
            try:
                if await self.credential.check_refresh():
                    await self.credential.refresh()
                    save_credential(self.secrets_dir, self.credential)
                    logger.info("[bilibili] cookie refreshed")
            except Exception as exc:
                logger.warning("[bilibili] cookie refresh check failed: {}", exc)
            await asyncio.sleep(6 * 3600)

    async def _name(self, uid: int) -> str:
        if uid not in self._names:
            from bilibili_api import user

            try:
                info = await user.User(uid, credential=self.credential).get_user_info()
                self._names[uid] = info.get("name") or str(uid)
            except Exception:
                self._names[uid] = str(uid)
        return self._names[uid]

    # ------------------------------------------------------------ polling

    async def _poll_loop(self) -> None:
        while True:
            try:
                if self.cfg.private_messages:
                    await self._poll_dms()
                if self.cfg.replies_and_mentions:
                    await self._poll_notifications()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[bilibili] poll failed: {}", exc)
            await asyncio.sleep(self.cfg.poll_seconds * random.uniform(0.7, 1.4))

    async def _poll_dms(self) -> None:
        from bilibili_api import session

        assert self.brain is not None
        data = await session.get_sessions(self.credential, session_type=1)
        for item in data.get("session_list") or []:
            if not item.get("unread_count"):
                continue
            talker = int(item["talker_id"])
            state_key = f"bilibili:dm_seq:{talker}"
            last_seq = await self.brain.memory.get_state(state_key, 0)
            msgs = await session.fetch_session_msgs(talker, self.credential, session_type=1, begin_seqno=last_seq)
            fresh = sorted((m for m in msgs.get("messages") or [] if m.get("msg_seqno", 0) > last_seq),
                           key=lambda m: m["msg_seqno"])
            for msg in fresh:
                last_seq = max(last_seq, msg["msg_seqno"])
                if int(msg.get("sender_uid", 0)) == self.self_uid or msg.get("msg_type") != 1:
                    continue
                try:
                    text = json.loads(msg.get("content") or "{}").get("content", "")
                except json.JSONDecodeError:
                    text = ""
                if not text:
                    continue
                name = await self._name(talker)
                await self.brain.handle(Incoming(
                    chat=Chat("bilibili", "private", str(talker), name),
                    sender=Sender(str(talker), name),
                    text=text,
                    message_id=str(msg.get("msg_key") or msg["msg_seqno"]),
                    timestamp=float(msg.get("timestamp") or time.time()),
                ))
            await self.brain.memory.set_state(state_key, last_seq)

    async def _poll_notifications(self) -> None:
        from bilibili_api import session

        assert self.brain is not None
        for kind, fetch in (("reply", session.get_replies), ("at", session.get_at)):
            state_key = f"bilibili:last_{kind}"
            last_id = await self.brain.memory.get_state(state_key)
            data = await fetch(self.credential)
            items = sorted(data.get("items") or [], key=lambda i: i.get("id", 0))
            if last_id is None:  # first run: don't answer the backlog of old notifications
                await self.brain.memory.set_state(state_key, items[-1]["id"] if items else 0)
                continue
            for entry in items:
                if entry.get("id", 0) <= last_id:
                    continue
                last_id = entry["id"]
                await self._on_comment(entry)
            await self.brain.memory.set_state(state_key, last_id)

    async def _on_comment(self, entry: dict[str, Any]) -> None:
        assert self.brain is not None
        user_info, item = entry.get("user") or {}, entry.get("item") or {}
        uid = int(user_info.get("mid") or 0)
        if not uid or uid == self.self_uid or not item.get("source_content"):
            return
        oid, business = int(item.get("subject_id") or 0), int(item.get("business_id") or 1)
        rpid = int(item.get("source_id") or 0)
        root = int(item.get("root_id") or 0) or rpid
        chat = Chat("bilibili", "comment", f"{business}:{oid}:{root}", item.get("title") or "")
        self._comment_targets[chat.key] = {"oid": oid, "type": business, "root": root, "parent": rpid}
        await self.brain.handle(Incoming(
            chat=chat,
            sender=Sender(str(uid), user_info.get("nickname") or str(uid)),
            text=item["source_content"],
            kind="comment",
            message_id=str(rpid),
            reply_to_me=True,
            meta={"uri": item.get("uri")},
        ))

    # ------------------------------------------------------------ live rooms

    async def _live(self, room_id: int) -> None:
        from bilibili_api import live

        assert self.brain is not None
        room = live.LiveDanmaku(room_id, credential=self.credential)
        self._rooms[room_id] = room
        alias = self.brain.cfg.identity.display_name

        @room.on("DANMU_MSG")
        async def on_danmaku(event: dict) -> None:
            info = (event.get("data") or {}).get("info") or []
            if len(info) < 3:
                return
            text, uid, uname = info[1], int(info[2][0]), info[2][1]
            if uid == self.self_uid:
                return
            await self.brain.handle(Incoming(
                chat=Chat("bilibili", "live", str(room_id), f"直播间 {room_id}"),
                sender=Sender(str(uid), uname),
                text=text,
                kind="danmaku",
                mentions_me=alias in text,
            ))

        while True:
            try:
                await room.connect()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[bilibili] live room {} disconnected: {}", room_id, exc)
            await asyncio.sleep(30)

    # ------------------------------------------------------------ outbound

    def can_speak(self, chat: Chat) -> bool:
        return self.credential is not None

    async def send(self, chat: Chat, bubble: Bubble, quote: str | None = None) -> str | None:
        text = self.flatten(bubble).strip() or (bubble.voice or "")
        if not text:
            return None
        if chat.kind == "private":
            from bilibili_api import session

            resp = await session.send_msg(self.credential, int(chat.id), session.EventType.TEXT, text)
            return str(resp.get("msg_key") or "") or None
        if chat.kind == "comment":
            from bilibili_api import comment

            target = self._comment_targets.get(chat.key)
            if not target:
                return None
            resp = await comment.send_comment(
                text, target["oid"], comment.CommentResourceType(target["type"]),
                root=target["root"], parent=target["parent"], credential=self.credential,
            )
            return str(resp.get("rpid") or "") or None
        if chat.kind == "live":
            from bilibili_api import live
            from bilibili_api.utils.danmaku import Danmaku

            room_id = int(chat.id)
            wait = 5.0 - (time.time() - self._last_danmaku.get(room_id, 0))
            if wait > 0:
                await asyncio.sleep(wait)
            plain = "".join(s.value for s in bubble.segments if s.type == "text")[:20]
            if plain:
                await live.LiveRoom(room_id, credential=self.credential).send_danmaku(Danmaku(plain))
                self._last_danmaku[room_id] = time.time()
            return None
        return None

    async def post(self, text: str) -> str | None:
        from bilibili_api import dynamic

        resp = await dynamic.send_dynamic(dynamic.BuildDynamic.empty().add_plain_text(text), self.credential)
        logger.info("[bilibili] posted a dynamic")
        return str((resp or {}).get("dyn_id_str") or "") or None
