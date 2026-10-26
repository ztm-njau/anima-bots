"""The owner's controls and her relationships: commands, blocking, friend requests and invites.

Owners are listed in ``bot.toml`` (``owners = ["qq:123456"]``); the local playground and terminal
always count as the owner. Commands start with ``/`` and are answered directly, never by the model.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from anima.core.events import Bubble, Chat, Incoming, Segment

if TYPE_CHECKING:
    from anima.core.brain import Brain

LOCAL_PLATFORMS = {"playground", "console"}
POLICIES = {"accept": "全部同意", "smart": "认识的人和带暗号的同意，其他问主人", "owner": "都问主人", "ignore": "不理"}

HELP = """主人命令：
/状态  看她现在的状态和花费
/拉黑 QQ号或@人   /放行 QQ号
/静音  这个群里只听不说   /解除静音
/请求  看待处理的好友请求和邀请
/同意 编号   /拒绝 编号
/删好友 QQ号   /退群 群号
/画像 QQ号或@人   /忘掉 QQ号（删掉关于 TA 的记忆）"""


class Admin:
    def __init__(self, brain: Brain):
        self.brain = brain

    @property
    def owners(self) -> set[str]:
        return set(self.brain.cfg.owners)

    def is_owner(self, ev: Incoming) -> bool:
        return ev.chat.platform in LOCAL_PLATFORMS or ev.user_key in self.owners

    # ------------------------------------------------------------ who she talks to

    async def gate(self, ev: Incoming) -> str | None:
        """Why this message must be dropped or only listened to: 'drop', 'listen', or None."""
        user = await self.brain.memory.get_user(ev.user_key)
        if user and user.blocked:
            return "drop"
        meta = await self.brain.memory.chat(ev.chat.key)
        if meta and meta.get("muted"):
            return "listen"
        if user and user.silenced_until > self.brain.clock.timestamp():
            return "listen"
        return None

    # ------------------------------------------------------------ commands

    def _target(self, ev: Incoming, arg: str) -> str | None:
        """"qq:123" / "123" / an @mention -> a user key. From the local console, bare numbers mean the
        first real platform she's on (usually QQ)."""
        explicit = re.search(r"([a-z]+):(\d{4,})", arg)
        if explicit:
            return f"{explicit.group(1)}:{explicit.group(2)}"
        platform = ev.chat.platform
        if platform in LOCAL_PLATFORMS:
            platform = next((p for p in self.brain.adapters if p not in LOCAL_PLATFORMS), "qq")
        uid = re.search(r"\d{4,}", arg)
        if uid:
            return f"{platform}:{uid.group()}"
        ats = ev.meta.get("at") or []
        return f"{platform}:{ats[0]}" if ats else None

    async def command(self, ev: Incoming) -> str | None:
        text = ev.text.strip()
        if not text.startswith("/") or not self.is_owner(ev):
            return None
        cmd, _, arg = text[1:].partition(" ")
        cmd, arg = cmd.strip(), arg.strip()
        brain, memory = self.brain, self.brain.memory
        if cmd in ("帮助", "help", "命令"):
            return HELP
        if cmd in ("状态", "status"):
            life = brain.life()
            pending = len(await memory.requests())
            return (f"{brain.cfg.identity.display_name}：{life.activity} · {brain.mood.describe(life.energy)}\n"
                    f"模型：{brain.llm.label} {brain.llm.model} · 本次花费 {brain.cost_text()}\n"
                    f"待处理请求：{pending} · 表情包 {await brain.memes.count()} 张 · 插件工具 "
                    f"{sum(1 for s in brain.skills if '__' in s.name)} 个")
        if cmd in ("拉黑", "block", "放行", "unblock"):
            key = self._target(ev, arg)
            if not key:
                return "要写 QQ 号，或者 @ 那个人"
            block = cmd in ("拉黑", "block")
            if not await memory.get_user(key):
                platform, uid = key.split(":", 1)
                await memory.touch_user(platform, uid, uid)
            await memory.update_user(key, blocked=int(block), silenced_until=0)
            return f"{'已拉黑' if block else '已放行'} {key.split(':', 1)[1]}"
        if cmd in ("静音", "mute", "解除静音", "unmute"):
            mute = cmd in ("静音", "mute")
            await memory.set_chat_muted(ev.chat.key, mute)
            return "好，这里我只看不说了" if mute else "我回来啦"
        if cmd in ("请求", "requests"):
            items = await memory.requests()
            if not items:
                return "没有待处理的请求"
            return "\n".join(_describe(r) for r in items[:10]) + "\n回复 /同意 编号 或 /拒绝 编号"
        if cmd in ("同意", "approve", "拒绝", "reject"):
            if not arg.isdigit():
                return "要写请求编号，比如 /同意 3"
            return await self.decide(int(arg), cmd in ("同意", "approve"))
        if cmd in ("删好友", "unfriend"):
            key = self._target(ev, arg)
            adapter = brain.adapters.get(ev.chat.platform)
            if not key or not adapter:
                return "要写 QQ 号"
            ok = await adapter.remove_friend(key.split(":", 1)[1])
            return "已删除好友" if ok else "这个平台删不了好友"
        if cmd in ("退群", "leave"):
            adapter = brain.adapters.get(ev.chat.platform)
            group = arg or (ev.chat.id if ev.chat.kind == "group" else "")
            ok = bool(adapter and group) and await adapter.leave_group(group)
            return "已退群" if ok else "退不了，要写群号"
        if cmd in ("画像", "profile"):
            key = self._target(ev, arg)
            user = await memory.get_user(key) if key else None
            if not user:
                return "没见过这个人"
            facts = await memory.facts(user.key, 10)
            return (f"{user.name}（她叫 TA「{user.call_name}」）好感 {user.affinity:.2f}，聊过 {user.msg_count} 句\n"
                    f"画像：{user.profile or '还没形成'}\n记得：" + ("；".join(f.content for f in facts) or "暂无"))
        if cmd in ("忘掉", "forget"):
            key = self._target(ev, arg)
            if not key:
                return "要写 QQ 号"
            await memory.delete_user_memories(key)
            return "关于 TA 的记忆删掉了"
        return None

    # ------------------------------------------------------------ friend requests and invites

    def policy(self, platform: str, kind: str) -> str:
        extras = self.brain.cfg.platform(platform).extras()
        if kind == "friend":
            if extras.get("accept_friend_requests") is True and "friend_requests" not in extras:
                return "accept"
            return str(extras.get("friend_requests", "smart"))
        return str(extras.get("group_invites", "owner"))

    async def on_request(self, platform: str, kind: str, user_id: str, flag: str, *, user_name: str = "",
                         group_id: str | None = None, comment: str = "", sub_type: str = "") -> str:
        memory = self.brain.memory
        rid = await memory.add_request(platform, kind, user_id, flag, user_name=user_name, group_id=group_id,
                                       comment=comment, sub_type=sub_type)
        policy = self.policy(platform, kind)
        user = await memory.get_user(f"{platform}:{user_id}")
        keywords = self.brain.cfg.platform(platform).extras().get("friend_keywords", [])
        decision = "pending"
        if user and user.blocked:
            decision = "reject"
        elif policy == "accept":
            decision = "approve"
        elif policy == "smart" and kind == "friend":
            known = bool(user and user.msg_count >= 3 and user.affinity >= 0)
            if known or any(k and k in comment for k in keywords) or f"{platform}:{user_id}" in self.owners:
                decision = "approve"
        elif policy == "ignore":
            decision = "ignore"
        self.brain.trace.emit("request", platform=platform, kind=kind, user=user_name or user_id, decision=decision)
        if decision in ("approve", "reject"):
            # People don't accept requests the second they arrive.
            delay = random.uniform(20, 180) * self.brain.humanizer.scale
            self.brain.spawn(self._later(delay, self.decide(rid, decision == "approve", note="自动")))
        elif decision == "pending":
            await self.notify_owners(platform, f"有新的{'好友请求' if kind == 'friend' else '群邀请'}：\n"
                                               f"{_describe(await memory.request(rid) or {})}\n回复 /同意 {rid} 或 /拒绝 {rid}")
        return decision

    async def _later(self, delay: float, coro) -> None:
        await asyncio.sleep(delay)
        await coro

    async def decide(self, request_id: int, approve: bool, note: str = "主人") -> str:
        memory = self.brain.memory
        req = await memory.request(request_id)
        if not req:
            return f"没有编号 {request_id} 的请求"
        if req["status"] != "pending":
            return f"这个请求已经处理过了（{req['status']}）"
        adapter = self.brain.adapters.get(req["platform"])
        if adapter is None:
            return "对应的平台没在运行"
        ok = await adapter.answer_request(req, approve)
        if not ok:
            return "平台没接受这个操作（可能请求过期了）"
        await memory.decide_request(request_id, "approved" if approve else "rejected", note)
        if approve and req["kind"] == "friend":
            name = req["user_name"] or req["user_id"]
            await memory.touch_user(req["platform"], req["user_id"], name)
            chat = Chat(req["platform"], "private", req["user_id"], name)
            hint = f"（TA 申请时写的：{req['comment']}）" if req["comment"] else ""
            self.brain.spawn(self._later(random.uniform(30, 120) * self.brain.humanizer.scale,
                                         self.brain.speak(chat, f"刚加上好友，跟 TA 打个招呼{hint}，自然一点，一两句。")))
        return f"已{'同意' if approve else '拒绝'}：{_describe(req)}"

    async def notify_owners(self, platform: str, text: str) -> None:
        adapter = self.brain.adapters.get(platform)
        for owner in self.owners:
            owner_platform, _, uid = owner.partition(":")
            if adapter and owner_platform == platform:
                try:
                    await adapter.send(Chat(platform, "private", uid), Bubble([Segment("text", text)], source=text))
                except Exception as exc:
                    logger.warning("Couldn't notify owner {}: {}", owner, exc)
        self.brain.trace.emit("notice", text=text)

    async def reply(self, ev: Incoming, text: str) -> None:
        adapter = self.brain.adapters.get(ev.chat.platform)
        if adapter:
            await adapter.send(ev.chat, Bubble([Segment("text", text)], source=text))


def _describe(r: dict[str, Any]) -> str:
    if not r:
        return ""
    who = f"{r.get('user_name') or r.get('user_id')}（{r.get('user_id')}）"
    what = "加好友" if r.get("kind") == "friend" else f"邀请进群 {r.get('group_id')}"
    when = time.strftime("%m-%d %H:%M", time.localtime(r.get("created_at") or 0))
    note = f" · 留言：{r['comment']}" if r.get("comment") else ""
    return f"#{r.get('id')} {who} {what}{note} · {when}"
