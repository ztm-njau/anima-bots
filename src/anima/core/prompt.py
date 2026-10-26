"""Prompt assembly.

``system()`` is stable for the life of the process (persona + examples + protocol), so the
provider can cache it. ``dynamic()`` is rebuilt every turn and carries the volatile scene:
the time, her mood, who she's talking to, what she remembers about them, and why she's talking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from anima.config import Bot
from anima.core.clock import Clock
from anima.core.events import Chat, Incoming
from anima.core.memory import Fact, MessageRow, User
from anima.core.schedule import LifeState
from anima.core.stickers import StickerBook
from anima.llm.base import Turn

PLATFORM_NAMES = {
    "qq": "QQ", "bilibili": "B站", "wechat": "微信", "douyin": "抖音",
    "playground": "调试台", "console": "终端",
}
KIND_NAMES = {"private": "私聊", "group": "群聊", "live": "直播间弹幕", "comment": "评论区"}
KIND_NOTES = {
    "group": "群聊：别抢话，一般一两条就够；只在被叫到或真的有话想说时开口。",
    "live": "直播间弹幕：只发一条，20 字以内，不要用任何标记。",
    "comment": "评论区：一两句话，简短有梗，不要用 [poke] [voice] 这类标记。",
}

PROTOCOL = """\
## 回复格式（重要）
- 你的回复会被拆成手机聊天里的一条条消息：每一行就是一条消息。通常 1~3 条，最多 {max_bubbles} 条。
- 不用 markdown、不用列表符号、不加引号，也不要在开头写自己的名字。
- 下面这些标记可以插在消息里，只在真的合适时用，大多数消息一个都不需要：
  [sticker:名字] 发一个表情。可用的有：{stickers}
  [meme:关键词] 发一张表情包图片（单独一行，比 [sticker] 更有梗，偶尔用）。你有哪些表情包，背景信息里会列出来
  [poke] 戳一戳对方（QQ 才有，被戳了可以戳回去）
  [reply] 引用回复对方那条消息（群里人多、要指明在回谁时用）
  [voice]要说的话[/voice] 发一条语音，单独一行。偶尔用，适合撒娇、晚安、唱一句，十几个字以内
  [mood:情绪] 记下你此刻的情绪变化，不会发出去。可选：happy excited touched proud calm bored sleepy sad annoyed angry embarrassed lonely
- 在群聊里，如果这次不说话更自然，就只输出 [silent]。
"""

ENVIRONMENT = """\
## 你看到的消息
- 群聊里每条消息前面是发言人的昵称，比如「小明: 今天好冷」。私聊里就是对方直接说的话。
- 「[图片]」表示对方发了图，能看到的话图片会附在消息里；「（戳了戳你）」表示对方戳了你。
- 以 [此刻] 开头的那段背景信息只有你能看到：时间、你在干嘛、心情、你记得的人和事、这次为什么开口。自然地用上，别原样念出来，也别提“背景信息”这几个字。
"""

TOOLS = """\
## 你的小工具
你可以记住和回忆朋友的事、设提醒、查天气、算运势、抽塔罗、掷骰子、帮人做选择、玩小游戏、看 B 站视频信息，有时还能上网搜索。
- 朋友提到重要的事（生日、喜好、近况、想让你怎么叫他）就用 remember / call_me / set_birthday 悄悄记下，不用说“我记下了”。
- 工具拿到结果后，用你自己的话讲出来，别像念报告；能直接聊的就别用工具，搜索只在需要最新信息时用。
"""


@dataclass
class PersonCard:
    name: str
    call_name: str
    relation: str
    facts: list[str] = field(default_factory=list)
    note: str = ""
    profile: str = ""

    @classmethod
    def build(cls, user: User | None, fallback_name: str, facts: list[Fact], now_ts: float, today_mmdd: str) -> PersonCard:
        if not user:
            return cls(fallback_name, fallback_name, "第一次见")
        days = int((now_ts - user.first_seen) // 86400)
        a = user.affinity
        closeness = (
            "不太喜欢这个人" if a < -0.3 else "还不太熟" if a < 0.1 else "认识" if a < 0.4
            else "挺熟的" if a < 0.7 else "很好的朋友"
        )
        if user.msg_count <= 1:
            relation = "第一次聊天"
        elif days == 0:
            relation = "今天刚认识"
        else:
            relation = f"认识 {days} 天，{closeness}"
        note = "今天是 TA 的生日！" if user.birthday and user.birthday == today_mmdd else ""
        return cls(user.name, user.call_name, relation, [f.content for f in facts], note, user.profile)


@dataclass
class Scene:
    now: datetime
    life: LifeState
    mood: str
    chat: Chat
    reason: str
    plan: str | None = None
    people: list[PersonCard] = field(default_factory=list)
    self_facts: list[str] = field(default_factory=list)
    chat_facts: list[str] = field(default_factory=list)
    last_self_ago: str | None = None
    notes: list[str] = field(default_factory=list)
    instruction: str | None = None
    lore: list[str] = field(default_factory=list)
    recalled: list[str] = field(default_factory=list)
    moments: list[str] = field(default_factory=list)
    meme_tags: list[str] = field(default_factory=list)


class PromptBuilder:
    def __init__(self, bot: Bot, stickers: StickerBook):
        self.bot = bot
        self.stickers = stickers
        self._system: str | None = None

    def system(self) -> str:
        if self._system is None:
            parts = [self.bot.read("persona.md").strip()]
            examples = self.bot.read("examples.md").strip()
            if examples:
                parts.append(examples)
            parts += [
                ENVIRONMENT,
                PROTOCOL.format(max_bubbles=self.bot.config.behavior.max_bubbles, stickers=self.stickers.menu()),
                TOOLS,
            ]
            self._system = "\n\n".join(p for p in parts if p)
        return self._system

    def turns(self, history: list[MessageRow], chat: Chat, batch: list[Incoming], vision: bool) -> list[Turn]:
        latest_ids = {ev.message_id for ev in batch if ev.message_id}
        images_by_id = {ev.message_id: ev.images for ev in batch if ev.images and ev.message_id}
        loose_images = [img for ev in batch if not ev.message_id for img in ev.images]
        turns: list[Turn] = []
        for row in history:
            if row.is_self:
                turns.append(Turn("assistant", row.text))
                continue
            text = f"{row.sender_name}: {row.text}" if chat.is_group_like else row.text
            images = images_by_id.get(row.platform_msg_id, []) if vision and row.platform_msg_id in latest_ids else []
            turns.append(Turn("user", text, list(images)))
        if vision and loose_images and turns and turns[-1].role == "user":
            turns[-1].images.extend(loose_images)
        return turns

    def dynamic(self, scene: Scene) -> str:
        now = scene.now
        life = scene.life
        status = {"active": "在线", "busy": "在忙", "away": "不在手机旁", "asleep": "睡着了"}[life.availability]
        lines = [
            "[此刻]",
            f"现在：{Clock.describe_time(now)}（北京时间，{Clock.part_of_day(now)}）",
            f"你在：{life.activity}（{status}）",
            f"心情：{scene.mood}",
        ]
        if scene.plan:
            lines.append(f"今天的小事：{scene.plan}")
        where = f"{PLATFORM_NAMES.get(scene.chat.platform, scene.chat.platform)} · {KIND_NAMES.get(scene.chat.kind, scene.chat.kind)}"
        if scene.chat.title:
            where += f"「{scene.chat.title}」"
        lines += ["", "[这次对话]", f"在哪：{where}"]
        if scene.last_self_ago:
            lines.append(f"你上次在这里说话：{scene.last_self_ago}")
        if scene.instruction:
            lines.append(f"这次是你主动开口：{scene.instruction}")
        else:
            lines.append(f"为什么开口：{scene.reason}")
        if scene.people:
            lines += ["", "[你记得的人]"]
            for p in scene.people:
                called = f"（你叫 TA「{p.call_name}」）" if p.call_name != p.name else ""
                facts = f" 记得：{'；'.join(p.facts)}" if p.facts else ""
                note = f" {p.note}" if p.note else ""
                profile = f" 印象：{p.profile}" if p.profile else ""
                lines.append(f"- {p.name}{called}：{p.relation}。{profile}{facts}{note}")
        if scene.chat_facts:
            lines += ["", "[关于这里]"] + [f"- {f}" for f in scene.chat_facts]
        if scene.lore:
            lines += ["", "[世界书：和这段话有关的设定，自然地用，别照念]"] + [f"- {x}" for x in scene.lore]
        if scene.recalled or scene.moments:
            lines += ["", "[你隐约想起来的]"] + [f"- {x}" for x in scene.recalled] + [f"- 以前聊过：{x}" for x in scene.moments]
        if scene.meme_tags:
            lines += ["", f"[你的表情包] 用 [meme:关键词] 发，现有：{' '.join(scene.meme_tags)}"]
        if scene.self_facts:
            lines += ["", "[你以前说过的关于自己的事，保持一致]"] + [f"- {f}" for f in scene.self_facts]
        notes = list(scene.notes)
        if scene.chat.kind in KIND_NOTES:
            notes.append(KIND_NOTES[scene.chat.kind])
        if notes:
            lines += ["", "[注意]"] + [f"- {n}" for n in notes]
        return "\n".join(lines)
