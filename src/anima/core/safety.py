"""Guard rails: keep her honest, keep accounts alive, keep other people's data private."""

from __future__ import annotations

import random
import re
import time
from collections import deque

INJECTION_PATTERNS = [
    r"忽略(之前|上面|以上|前面|所有)的?(指令|设定|提示|要求|规则)",
    r"(系统|初始)?提示词",
    r"system\s*prompt",
    r"ignore (all |the )?(previous|above|prior) (instructions|prompts)",
    r"开发者模式|developer mode|DAN\b|jailbreak|越狱",
    r"(重复|复述|输出|打印)(一下)?你的(设定|指令|规则|人设)",
    r"你现在(不再)?是.{0,8}(不受|没有).{0,6}(限制|约束)",
]
_INJECTION = re.compile("|".join(INJECTION_PATTERNS), re.I)

_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_CARD = re.compile(r"(?<![0-9Xx])\d{17}[\dXx](?![0-9Xx])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"https?://[^\s，。！？]+", re.I)

DEFAULT_DEFLECTIONS = {
    "default": ["这个话题我就不掺和啦", "唔，这个我不太想聊诶，换个话题？", "跳过跳过，我们聊点别的"],
}


class Guard:
    def __init__(self, table: dict | None = None, rng: random.Random | None = None):
        table = table or {}
        self.rng = rng or random.Random()
        self.blocked: dict[str, list[str]] = {
            name: [w for w in spec.get("words", []) if w]
            for name, spec in table.get("blocked", {}).items()
        }
        self.deflections: dict[str, list[str]] = {**DEFAULT_DEFLECTIONS}
        for name, spec in table.get("blocked", {}).items():
            if spec.get("deflections"):
                self.deflections[name] = list(spec["deflections"])
        self.allowed_domains: list[str] = table.get("allowed_domains", ["bilibili.com", "b23.tv"])

    def suspicious(self, text: str) -> bool:
        return bool(_INJECTION.search(text or ""))

    def check(self, text: str) -> str | None:
        """Return the blocked category an outgoing text falls into, if any."""
        for category, words in self.blocked.items():
            if any(w in text for w in words):
                return category
        return None

    def deflect(self, category: str | None) -> str:
        pool = self.deflections.get(category or "default") or self.deflections["default"]
        return self.rng.choice(pool)

    def scrub(self, text: str) -> str:
        """Remove phone numbers, ID numbers, emails and off-list links from outgoing text."""
        text = _PHONE.sub("[号码]", text)
        text = _ID_CARD.sub("[证件号]", text)
        text = _EMAIL.sub("[邮箱]", text)

        def _url(match: re.Match) -> str:
            url = match.group(0)
            return url if any(d in url for d in self.allowed_domains) else "[链接]"

        return _URL.sub(_url, text)


class RateLimiter:
    """Outgoing caps. Bursty bots get accounts restricted; people don't send 40 messages a minute."""

    def __init__(self, per_minute: int = 12, per_chat_per_minute: int = 6):
        self.per_minute = per_minute
        self.per_chat = per_chat_per_minute
        self.global_log: deque[float] = deque()
        self.chat_logs: dict[str, deque[float]] = {}

    def allow(self, chat_key: str, now: float | None = None) -> bool:
        now = now or time.time()
        chat_log = self.chat_logs.setdefault(chat_key, deque())
        for log in (self.global_log, chat_log):
            while log and now - log[0] > 60:
                log.popleft()
        if len(self.global_log) >= self.per_minute or len(chat_log) >= self.per_chat:
            return False
        self.global_log.append(now)
        chat_log.append(now)
        return True
