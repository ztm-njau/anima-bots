"""Whether to speak at all. Knowing when to stay quiet is most of what makes group chat feel human.

In a group she always answers an @, a reply to her, a poke, or someone calling her by name. She
keeps talking with whoever she just answered, as long as they aren't clearly talking to someone
else. Otherwise she chimes in now and then: more when the topic is hers, less when the group is
racing along, when she has talked a lot, or when she has already butted in a few times this hour.
And when three people repeat the same line, sometimes she repeats it too.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Literal

from anima.config import BehaviorConfig
from anima.core.events import Chat, Incoming
from anima.core.schedule import LifeState

Act = Literal["reply", "ignore", "defer", "echo"]


@dataclass
class ChatStats:
    seconds_since_self: float | None = None  # since she last spoke here
    self_share: float = 0.0  # her share of the last ~20 messages
    can_speak: bool = True
    partners: dict[str, float] = field(default_factory=dict)  # user key -> seconds since she answered them
    others_since_self: int = 0  # messages from other people since she last spoke
    asked_ago: float | None = None  # seconds since she ended a message with a question
    interjections_hour: int = 0  # unprompted chime-ins in the last hour
    pace: float = 0.0  # messages per minute in the last few minutes
    echo: str | None = None  # a line several people just repeated


@dataclass
class Decision:
    act: Act
    reason: str
    addressed: bool = False
    score: float = 0.0
    tags: list[str] = field(default_factory=list)
    target: Incoming | None = None  # the message she is mainly answering
    unprompted: bool = False  # a chime-in nobody asked for


def call_strength(text: str, aliases: list[str], false_friends: list[str] = ()) -> float:
    """1.0 when someone calls her by name, 0.5 when they talk about her, 0 otherwise."""
    lowered = text.lower()
    for word in false_friends:
        lowered = lowered.replace(word.lower(), " ")
    best = 0.0
    for alias in aliases:
        if not alias:
            continue
        for m in re.finditer(re.escape(alias), lowered):
            before, after = lowered[: m.start()].rstrip(), lowered[m.end():].lstrip()
            if (not before or before[-1] in "@，,。！!？?~～ 、:：" or before.endswith(("问问", "叫", "喊", "让", "请", "求")) or
                    not after or after[0] in "，,。！!？?~～、:：" or after.startswith(("你", "在", "快", "来", "帮", "呢", "吗", "呀", "啊", "酱"))):
                return 1.0
            best = 0.5
    return best


def directed_elsewhere(ev: Incoming) -> bool:
    """@-ing or replying to someone else, and not her."""
    if ev.mentions_me or ev.reply_to_me:
        return False
    return bool(ev.meta.get("at")) or bool(ev.meta.get("reply_to_other"))


class Policy:
    def __init__(self, cfg: BehaviorConfig, aliases: list[str], rng: random.Random | None = None):
        self.cfg = cfg
        self.aliases = [a.lower() for a in aliases if a]
        self.interests = [i.lower() for i in cfg.interests if i]
        self.rng = rng or random.Random()

    def call(self, ev: Incoming, cfg: BehaviorConfig | None = None) -> float:
        return call_strength(ev.text, self.aliases, (cfg or self.cfg).name_false_friends)

    def addressed(self, ev: Incoming, cfg: BehaviorConfig | None = None) -> bool:
        if ev.chat.kind == "private" or ev.mentions_me or ev.reply_to_me or ev.kind == "poke":
            return True
        return self.call(ev, cfg) >= 1.0

    def target(self, batch: list[Incoming], stats: ChatStats | None = None, cfg: BehaviorConfig | None = None) -> Incoming | None:
        """The message she is mainly answering: whoever spoke to her, else her partner, else the last question."""
        if not batch:
            return None
        partners = stats.partners if stats else {}
        for test in (lambda e: e.mentions_me or e.reply_to_me or e.kind == "poke",
                     lambda e: self.call(e, cfg) >= 1.0,
                     lambda e: e.user_key in partners and not directed_elsewhere(e),
                     lambda e: e.text.rstrip().endswith(("?", "？", "吗", "呢"))):
            hits = [e for e in batch if test(e)]
            if hits:
                return hits[-1]
        return batch[-1]

    def decide(self, chat: Chat, batch: list[Incoming], life: LifeState, stats: ChatStats,
               cfg: BehaviorConfig | None = None) -> Decision:
        cfg = cfg or self.cfg
        if not batch:
            return Decision("ignore", "没有新消息")
        if not stats.can_speak or all(ev.meta.get("listen_only") for ev in batch):
            return Decision("ignore", "这里只旁听，不发言")

        addressed = any(self.addressed(ev, cfg) for ev in batch)
        poked = any(ev.kind == "poke" for ev in batch)
        target = self.target(batch, stats, cfg)
        if life.asleep and any(ev.meta.get("always_awake") for ev in batch):
            life = LifeState("值班中", "active", 0.6)  # e.g. an official account must always answer

        if chat.kind == "private":
            if life.asleep:
                return Decision("defer", "睡着了，醒来再回", addressed=True, target=target)
            return Decision("reply", "私聊", addressed=True, tags=["poked"] if poked else [], target=target)

        if addressed:
            why = "被戳了" if poked else "有人叫她/回复她"
            if life.asleep:
                # She sees @-mentions when she wakes; plain name-drops are lost to the night.
                if any(ev.mentions_me or ev.reply_to_me for ev in batch):
                    return Decision("defer", f"{why}，但睡着了", addressed=True, target=target)
                return Decision("ignore", "睡着了", addressed=True)
            return Decision("reply", why, addressed=True, tags=["poked"] if poked else [], target=target)

        if life.asleep:
            return Decision("ignore", "睡着了")

        if chat.kind == "comment":
            return Decision("ignore", "评论区只回复@和回复她的")

        # Still talking with her: the person she just answered, or anyone answering her question.
        fresh = [ev for ev in batch if not directed_elsewhere(ev)]
        follow = [ev for ev in fresh if stats.partners.get(ev.user_key, 1e9) < cfg.follow_up_seconds]
        if follow and stats.others_since_self <= 6:
            chance = 0.85 if stats.others_since_self <= 2 else 0.55
            if self.rng.random() < chance:
                return Decision("reply", "接着刚才的话题", score=chance, tags=["follow-up"], target=follow[-1])
            return Decision("ignore", "话题被别人接走了", score=chance, tags=["follow-up"])
        if stats.asked_ago is not None and stats.asked_ago < 90 and fresh and stats.others_since_self <= 3:
            if self.rng.random() < 0.7:
                return Decision("reply", "有人回答了她的问题", score=0.7, tags=["answer"], target=fresh[0])

        if stats.echo and self.rng.random() < cfg.repeat_chance and stats.interjections_hour < max(1, cfg.interjections_per_hour):
            return Decision("echo", "大家在复读，跟一个", score=cfg.repeat_chance, tags=["echo"], unprompted=True)

        if stats.interjections_hour >= cfg.interjections_per_hour:
            return Decision("ignore", "这个小时已经插过好几次话了", tags=["hourly-cap"])

        score = cfg.group_chattiness * (0.4 if chat.kind == "live" else 1.0)
        tags: list[str] = []
        interests = [i.lower() for i in cfg.interests if i] if cfg is not self.cfg else self.interests
        text = " ".join(ev.text.lower() for ev in fresh)
        hits = [i for i in interests if i in text]
        if hits:
            score += cfg.interest_boost
            tags.append("interest:" + ",".join(hits[:3]))
        if any(self.call(ev, cfg) for ev in batch):
            score += 0.35  # they are talking about her
            tags.append("mentioned")
        if any(ev.text.rstrip().endswith(("?", "？", "吗", "呢")) for ev in fresh[-2:]):
            score += 0.05
            tags.append("question")
        if len(fresh) < len(batch) / 2:
            score *= 0.2  # mostly people talking to each other
            tags.append("directed-elsewhere")
        if stats.seconds_since_self is not None:
            if stats.seconds_since_self < cfg.cooldown_seconds:
                score *= 0.25
                tags.append("cooldown")
            elif stats.seconds_since_self < 600:
                score += 0.08  # still part of the conversation
                tags.append("in-conversation")
        if stats.self_share > 0.3:
            score *= 0.3
            tags.append("talking-too-much")
        if stats.pace > 12:
            score *= 0.5  # the group is racing; a reply would land three topics late
            tags.append("fast-chat")
        if life.availability == "busy":
            score *= 0.5
            tags.append("busy")
        score *= 0.5 + life.energy / 2
        score = max(0.0, min(0.9, score))

        if self.rng.random() < score:
            why = "话题戳中她的兴趣" if hits else "有人在说她" if "mentioned" in tags else "想接一句"
            return Decision("reply", why, score=score, tags=tags, target=target, unprompted=True)
        return Decision("ignore", "这次不插话", score=score, tags=tags)
