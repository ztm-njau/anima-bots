"""Her daily rhythm: when she sleeps, studies, eats (vicariously) and hangs out.

Blocks come from ``bots/<name>/life.toml``. Availability drives how quickly she notices
messages, which is most of what makes a bot feel like a person rather than a vending machine.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Literal

from anima.core.clock import Clock

Availability = Literal["active", "busy", "away", "asleep"]

DEFAULT_WEEKDAY = [
    {"start": "00:40", "end": "08:30", "activity": "睡觉", "availability": "asleep", "energy": 0.1},
    {"start": "08:30", "end": "09:30", "activity": "刚醒，赖床刷手机", "availability": "active", "energy": 0.4},
    {"start": "09:30", "end": "12:00", "activity": "上网课", "availability": "busy", "energy": 0.7},
    {"start": "12:00", "end": "13:30", "activity": "午饭时间", "availability": "active", "energy": 0.6},
    {"start": "13:30", "end": "17:30", "activity": "做自己的事", "availability": "busy", "energy": 0.6},
    {"start": "17:30", "end": "19:00", "activity": "傍晚放空", "availability": "active", "energy": 0.65},
    {"start": "19:00", "end": "23:30", "activity": "自由时间", "availability": "active", "energy": 0.85},
    {"start": "23:30", "end": "00:40", "activity": "准备睡了", "availability": "active", "energy": 0.4},
]


@dataclass
class Block:
    start: time
    end: time
    activity: str
    availability: Availability
    energy: float

    def contains(self, t: time) -> bool:
        if self.start <= self.end:
            return self.start <= t < self.end
        return t >= self.start or t < self.end  # crosses midnight


@dataclass
class LifeState:
    activity: str
    availability: Availability
    energy: float
    insomnia: bool = False

    @property
    def asleep(self) -> bool:
        return self.availability == "asleep"


def _parse(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _blocks(raw: list[dict]) -> list[Block]:
    return [
        Block(
            start=_parse(b["start"]),
            end=_parse(b["end"]),
            activity=b["activity"],
            availability=b.get("availability", "active"),
            energy=float(b.get("energy", 0.6)),
        )
        for b in raw
    ]


class Schedule:
    def __init__(self, life: dict, clock: Clock, insomnia_chance: float = 0.04):
        self.clock = clock
        self.weekday = _blocks(life.get("weekday") or DEFAULT_WEEKDAY)
        self.weekend = _blocks(life.get("weekend") or life.get("weekday") or DEFAULT_WEEKDAY)
        self.insomnia_chance = insomnia_chance

    def _night_of(self, when: datetime) -> str:
        """Nights belong to the evening they started on, so 02:00 Tuesday is Monday's night."""
        return (when - timedelta(hours=12)).strftime("%Y-%m-%d")

    def insomnia(self, when: datetime) -> bool:
        seed = int(hashlib.sha256(self._night_of(when).encode()).hexdigest()[:8], 16)
        return random.Random(seed).random() < self.insomnia_chance and when.hour < 3

    def blocks_for(self, when: datetime) -> list[Block]:
        # Small hours belong to the previous evening: Friday and Saturday nights are weekend
        # nights, Sunday night is a school night. Daytime follows the calendar.
        day = (when - timedelta(hours=5)).weekday()
        weekend = day in (4, 5) if when.hour < 5 else day in (5, 6)
        return self.weekend if weekend else self.weekday

    def state(self, when: datetime | None = None) -> LifeState:
        when = when or self.clock.now()
        t = when.time()
        for block in self.blocks_for(when):
            if block.contains(t):
                if block.availability == "asleep" and self.insomnia(when):
                    return LifeState("失眠了，睁着眼睛数服务器的指示灯", "active", 0.3, insomnia=True)
                return LifeState(block.activity, block.availability, block.energy)
        return LifeState("发呆", "active", 0.6)

    def next_wake(self, when: datetime | None = None) -> datetime:
        """When the current sleep block ends (or `when` itself if she's awake)."""
        when = when or self.clock.now()
        probe = when
        for _ in range(24 * 12):
            if not self.state(probe).asleep:
                return probe
            probe += timedelta(minutes=5)
        return when

    def wake_time_today(self, when: datetime | None = None) -> datetime:
        when = when or self.clock.now()
        midnight = when.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.next_wake(midnight + timedelta(hours=1))

    def notice_delay(self, state: LifeState, rng: random.Random, *, close_friend: bool = False) -> float:
        """Seconds before she picks up her phone and notices a new message."""
        if state.availability == "active":
            delay = rng.uniform(1, 8) if rng.random() > 0.12 else rng.uniform(20, 90)
        elif state.availability == "busy":
            delay = rng.uniform(25, 240)
        elif state.availability == "away":
            delay = rng.uniform(180, 900)
        else:
            delay = 0.0
        return delay * (0.6 if close_friend else 1.0)
