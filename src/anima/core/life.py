"""Her life between conversations.

Every morning she plans a small day; at night she writes a diary. She keeps the promises she
made (reminders), remembers birthdays, says good morning in the groups she likes, and
occasionally breaks a long silence the way a regular group member would.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger

from anima.core.events import Chat
from anima.llm.base import LLMError

if TYPE_CHECKING:
    from anima.core.brain import Brain

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "theme": {"type": "string"},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"time": {"type": "string"}, "what": {"type": "string"}},
                "required": ["time", "what"],
                "additionalProperties": False,
            },
        },
        "song": {"type": "string"},
        "small_goal": {"type": "string"},
        "bug_moment": {"type": "string"},
    },
    "required": ["theme", "events", "song", "small_goal", "bug_moment"],
    "additionalProperties": False,
}

FALLBACK_PLANS = [
    {"theme": "想把猎户座的每颗星都认一遍", "events": [{"time": "10:00", "what": "听天体物理公开课"},
     {"time": "15:00", "what": "整理一期冷知识"}, {"time": "21:00", "what": "看别人拍的星空照片"}],
     "song": "一首下雨天的 lo-fi", "small_goal": "攒 3 枚星星币", "bug_moment": "Bug 又睡在缓存里了"},
    {"theme": "研究人类为什么爱吃火锅", "events": [{"time": "12:00", "what": "到处看别人午饭吃什么"},
     {"time": "16:00", "what": "读一本讲味觉的书"}, {"time": "20:30", "what": "看一部老电影"}],
     "song": "城市流行老歌", "small_goal": "学会一个新梗", "bug_moment": "Bug 追着一个光标跑了一下午"},
]

PLAN_SYSTEM = """\
你在为一个虚拟角色安排她今天的生活。她是住在网络里的 AI 女孩，所有事情都发生在网上或她的小屋里（比如蹭公开课、看电影、整理冷知识、云吃饭、陪电子猫 Bug 玩），不要编造线下经历。
根据她的人设和昨天的日记，给今天一个小主题、3~4 件小事（带时间，符合她的作息）、一首今日歌曲（可以只描述风格）、一个小目标、一个电子猫 Bug 的小插曲。要具体、有生活感、有点可爱，延续之前的故事线。

她的人设摘要：
{persona}"""

DIARY_SYSTEM = """\
你是「{name}」，一个住在网络里的 AI 女孩。现在是晚上，写今天的日记。
要求：用你平时说话的语气，150~250 字，像真的日记，有具体的小事和感受。
可以写今天和大家聊天的感受，但不要写出任何人的名字、账号或私聊内容（日记可能会公开）。
不要用 markdown，不要标题，直接写正文。"""


def chat_from_key(key: str, title: str = "") -> Chat:
    platform, kind, chat_id = key.split(":", 2)
    return Chat(platform, kind, chat_id, title)  # type: ignore[arg-type]


def plan_text(plan: dict) -> str:
    events = "；".join(f"{e['time']} {e['what']}" for e in plan.get("events", []))
    return (f"主题：{plan.get('theme', '')}。{events}。今日歌曲：{plan.get('song', '')}。"
            f"小目标：{plan.get('small_goal', '')}。Bug：{plan.get('bug_moment', '')}")


class Life:
    TICK = 30.0

    def __init__(self, brain: Brain):
        self.brain = brain
        self.cfg = brain.cfg.life
        self._was_asleep: bool | None = None

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Life tick failed")
            await asyncio.sleep(self.TICK)

    async def _once(self, task: str, date: str) -> bool:
        """True the first time it's called for (task, date); False afterwards."""
        key = f"life:{date}:{task}"
        if await self.brain.memory.get_state(key):
            return False
        await self.brain.memory.set_state(key, True)
        return True

    def _day_rng(self, *parts: str) -> random.Random:
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
        return random.Random(int(digest[:12], 16))

    async def tick(self) -> None:
        brain = self.brain
        now = brain.clock.now()
        today = brain.clock.today()
        life = brain.life()

        if getattr(brain.llm, "demo", False):
            return  # no real model yet: don't fill her diary or chats with canned lines

        await self.reminders()  # promises are kept even at night: she set an alarm

        if self._was_asleep and not life.asleep:
            brain.trace.emit("wake", at=now.isoformat())
            await brain.wake_up()
        self._was_asleep = life.asleep
        if life.asleep:
            return

        if self.cfg.daily_plan and await brain.memory.journal_get(today, "plan") is None:
            await self.plan_day(today)
        if self.cfg.diary and now.strftime("%H:%M") >= self.cfg.diary_time and await self._once("diary", today):
            await self.write_diary(today)
        await self.greetings(now, today)
        await self.birthdays(now, today)
        if self.cfg.idle_chatter and life.availability == "active":
            await self.idle_chatter(now, today)

    # ------------------------------------------------------------ plan & diary

    async def plan_day(self, today: str) -> str:
        brain = self.brain
        yesterday = (brain.clock.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        diary = await brain.memory.journal_get(yesterday, "diary") or "（没有）"
        persona = brain.bot.read("persona.md")[:1500]
        prompt = f"今天是 {brain.clock.describe()}。\n昨天的日记：{diary}"
        plan: dict | None = None
        try:
            result = await brain.llm.complete(PLAN_SYSTEM.format(persona=persona), prompt, schema=PLAN_SCHEMA)
            brain.account(result)
            plan = json.loads(result.text)
            if not plan.get("events"):
                plan = None
        except (LLMError, json.JSONDecodeError) as exc:
            logger.warning("Daily plan generation failed: {}", exc)
        plan = plan or self._day_rng("plan", today).choice(FALLBACK_PLANS)
        text = plan_text(plan)
        await brain.memory.journal_put(today, "plan", text)
        brain.trace.emit("plan", date=today, plan=text)
        return text

    async def write_diary(self, today: str) -> str | None:
        brain = self.brain
        start = brain.clock.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        messages = await brain.memory.messages_between(start, brain.clock.timestamp() + 1, limit=300)
        sample = messages[-120:]
        transcript = "\n".join(f"{'我' if m.is_self else '某人'}: {m.text[:60]}" for m in sample) or "（今天没怎么聊天）"
        plan = await brain.memory.journal_get(today, "plan") or ""
        prompt = (f"日期：{brain.clock.describe()}\n今天的计划：{plan}\n心情：{brain.mood.describe(0.5)}\n"
                  f"今天聊过 {len({m.sender_key for m in messages if not m.is_self})} 个人，节选：\n{transcript}")
        try:
            result = await brain.llm.complete(DIARY_SYSTEM.format(name=brain.cfg.identity.display_name), prompt)
            brain.account(result)
        except LLMError as exc:
            logger.warning("Diary failed: {}", exc)
            return None
        diary = result.text.strip()
        if not diary:
            return None
        await brain.memory.journal_put(today, "diary", diary)
        brain.trace.emit("diary", date=today, text=diary)
        for name, adapter in brain.adapters.items():
            if "dynamic" in adapter.capabilities and brain.cfg.platform(name).extras().get("post_diary"):
                try:
                    await adapter.post(diary)
                except Exception:
                    logger.exception("Posting diary to {} failed", name)
        return diary

    # ------------------------------------------------------------ keeping promises

    async def reminders(self) -> None:
        brain = self.brain
        for item in await brain.memory.due_reminders(brain.clock.timestamp()):
            await brain.memory.finish_reminder(item["id"])
            meta = await brain.memory.chat(item["chat_key"])
            chat = chat_from_key(item["chat_key"], meta["title"] if meta else "")
            await brain.speak(chat, f"提醒{item['user_name'] or '对方'}：{item['text']}。这是 TA 之前请你设的提醒，现在到点了，"
                                    "叫一下 TA，语气自然，像朋友提醒一样。")

    async def greetings(self, now: datetime, today: str) -> None:
        wake = self.brain.schedule.wake_time_today(now)
        for chat_key in self.cfg.greet_groups:
            rng = self._day_rng("greet", chat_key, today)
            if rng.random() > 0.6:
                continue
            at = wake + timedelta(minutes=rng.randint(10, 100))
            if now >= at and now < at + timedelta(hours=2) and await self._once(f"greet:{chat_key}", today):
                meta = await self.brain.memory.chat(chat_key)
                await self.brain.speak(chat_from_key(chat_key, meta["title"] if meta else ""),
                                       "早上在群里跟大家打个招呼，可以顺口提一句你今天的小计划，一两句就好。")

    async def birthdays(self, now: datetime, today: str) -> None:
        if now.hour < 9:
            return
        for user in await self.brain.memory.birthdays_on(now.strftime("%m-%d")):
            if user.affinity < 0.2 or not await self._once(f"birthday:{user.key}", today):
                continue
            chat = Chat(user.platform, "private", user.uid)
            await self.brain.speak(chat, f"今天是{user.call_name}的生日，真诚地祝 TA 生日快乐，可以提到你记得的关于 TA 的事。")

    async def idle_chatter(self, now: datetime, today: str) -> None:
        brain = self.brain
        now_ts = brain.clock.timestamp()
        for meta in await brain.memory.chats("group"):
            chat = chat_from_key(meta["key"], meta["title"])
            adapter = brain.adapters.get(chat.platform)
            if not adapter or not adapter.can_speak(chat):
                continue
            quiet = now_ts - (meta["last_active"] or now_ts)
            her_silence = now_ts - (meta["last_self"] or 0)
            if quiet < self.cfg.idle_chatter_hours * 3600 or her_silence < 6 * 3600:
                continue
            if brain.rng.random() < 1 / 120 and await self._once(f"chatter:{chat.key}", today):
                await brain.speak(chat, "群里安静好久了。像普通群友冒泡一样随口分享一点东西：今天的小事、一个冷知识、"
                                        "或者一个有意思的问题，一两句就好，别像在发公告。")
