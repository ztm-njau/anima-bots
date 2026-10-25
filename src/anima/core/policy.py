"""Whether to speak at all. Knowing when to stay quiet is most of what makes group chat feel human."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from anima.config import BehaviorConfig
from anima.core.events import Chat, Incoming
from anima.core.schedule import LifeState

Act = Literal["reply", "ignore", "defer"]


@dataclass
class ChatStats:
    seconds_since_self: float | None = None  # since she last spoke here
    self_share: float = 0.0  # her share of the last ~20 messages
    can_speak: bool = True


@dataclass
class Decision:
    act: Act
    reason: str
    addressed: bool = False
    score: float = 0.0
    tags: list[str] = field(default_factory=list)


class Policy:
    def __init__(self, cfg: BehaviorConfig, aliases: list[str], rng: random.Random | None = None):
        self.cfg = cfg
        self.aliases = [a.lower() for a in aliases if a]
        self.interests = [i.lower() for i in cfg.interests if i]
        self.rng = rng or random.Random()

    def addressed(self, ev: Incoming) -> bool:
        if ev.chat.kind == "private" or ev.mentions_me or ev.reply_to_me or ev.kind == "poke":
            return True
        text = ev.text.lower()
        return any(alias in text for alias in self.aliases)

    def decide(self, chat: Chat, batch: list[Incoming], life: LifeState, stats: ChatStats) -> Decision:
        if not batch:
            return Decision("ignore", "没有新消息")
        if not stats.can_speak or all(ev.meta.get("listen_only") for ev in batch):
            return Decision("ignore", "这里只旁听，不发言")

        addressed = any(self.addressed(ev) for ev in batch)
        poked = any(ev.kind == "poke" for ev in batch)
        if life.asleep and any(ev.meta.get("always_awake") for ev in batch):
            life = LifeState("值班中", "active", 0.6)  # e.g. an official account must always answer

        if chat.kind == "private":
            if life.asleep:
                return Decision("defer", "睡着了，醒来再回", addressed=True)
            return Decision("reply", "私聊", addressed=True, tags=["poked"] if poked else [])

        if addressed:
            why = "被戳了" if poked else "有人叫她/回复她"
            if life.asleep:
                # She sees @-mentions when she wakes; plain name-drops are lost to the night.
                if any(ev.mentions_me or ev.reply_to_me for ev in batch):
                    return Decision("defer", f"{why}，但睡着了", addressed=True)
                return Decision("ignore", "睡着了", addressed=True)
            return Decision("reply", why, addressed=True, tags=["poked"] if poked else [])

        if life.asleep:
            return Decision("ignore", "睡着了")

        if chat.kind == "comment":
            return Decision("ignore", "评论区只回复@和回复她的")

        score = self.cfg.group_chattiness * (0.4 if chat.kind == "live" else 1.0)
        tags: list[str] = []
        text = " ".join(ev.text.lower() for ev in batch)
        hits = [i for i in self.interests if i in text]
        if hits:
            score += self.cfg.interest_boost
            tags.append("interest:" + ",".join(hits[:3]))
        if any(ev.text.rstrip().endswith(("?", "？", "吗", "呢")) for ev in batch[-2:]):
            score += 0.05
            tags.append("question")
        if stats.seconds_since_self is not None:
            if stats.seconds_since_self < self.cfg.cooldown_seconds:
                score *= 0.25
                tags.append("cooldown")
            elif stats.seconds_since_self < 600:
                score += 0.08  # still part of the conversation
                tags.append("in-conversation")
        if stats.self_share > 0.3:
            score *= 0.3
            tags.append("talking-too-much")
        if life.availability == "busy":
            score *= 0.5
            tags.append("busy")
        score *= 0.5 + life.energy / 2
        score = max(0.0, min(0.9, score))

        if self.rng.random() < score:
            why = "话题戳中她的兴趣" if hits else "想接一句"
            return Decision("reply", why, score=score, tags=tags)
        return Decision("ignore", "这次不插话", score=score, tags=tags)
