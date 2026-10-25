"""Mood: a small emotional state that drifts back to her baseline and colours how she talks."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

# label -> (valence delta, arousal delta)
FEELINGS: dict[str, tuple[float, float]] = {
    "happy": (0.15, 0.10),
    "excited": (0.12, 0.25),
    "touched": (0.20, 0.00),
    "proud": (0.12, 0.10),
    "calm": (0.02, -0.15),
    "bored": (-0.06, -0.15),
    "sleepy": (0.00, -0.20),
    "sad": (-0.20, -0.10),
    "annoyed": (-0.15, 0.10),
    "angry": (-0.25, 0.20),
    "embarrassed": (-0.03, 0.15),
    "lonely": (-0.12, -0.10),
}


@dataclass
class Mood:
    valence: float = 0.35  # -1 (down) .. 1 (elated)
    arousal: float = 0.45  # 0 (flat) .. 1 (buzzing)
    updated: float = field(default_factory=time.time)
    recent: list[str] = field(default_factory=list)


class MoodEngine:
    BASE_VALENCE = 0.35
    BASE_AROUSAL = 0.45
    HALF_LIFE = 3 * 3600

    def __init__(self, state: dict | None = None):
        self.mood = Mood(**state) if state else Mood()

    def snapshot(self) -> dict:
        return {
            "valence": self.mood.valence,
            "arousal": self.mood.arousal,
            "updated": self.mood.updated,
            "recent": self.mood.recent[-6:],
        }

    def current(self, now: float | None = None) -> Mood:
        now = now or time.time()
        dt = max(0.0, now - self.mood.updated)
        k = math.exp(-math.log(2) * dt / self.HALF_LIFE)
        self.mood.valence = self.BASE_VALENCE + (self.mood.valence - self.BASE_VALENCE) * k
        self.mood.arousal = self.BASE_AROUSAL + (self.mood.arousal - self.BASE_AROUSAL) * k
        self.mood.updated = now
        return self.mood

    def feel(self, label: str, intensity: float = 1.0, now: float | None = None) -> bool:
        label = label.strip().lower()
        if label not in FEELINGS:
            return False
        mood = self.current(now)
        dv, da = FEELINGS[label]
        mood.valence = max(-1.0, min(1.0, mood.valence + dv * intensity))
        mood.arousal = max(0.0, min(1.0, mood.arousal + da * intensity))
        mood.recent = (mood.recent + [label])[-6:]
        return True

    def label(self, energy: float, now: float | None = None) -> str:
        m = self.current(now)
        if energy < 0.25:
            return "困"
        if m.valence > 0.55:
            return "兴奋" if m.arousal > 0.65 else "开心"
        if m.valence > 0.2:
            return "心情不错" if m.arousal > 0.35 else "平静"
        if m.valence > -0.15:
            return "有点无聊" if m.arousal < 0.4 else "有点烦躁"
        if m.valence > -0.5:
            return "有点低落"
        return "很难过"

    def describe(self, energy: float, now: float | None = None) -> str:
        m = self.current(now)
        label = self.label(energy, now)
        if energy < 0.25:
            vigor = "困得睁不开眼"
        elif energy < 0.5:
            vigor = "精力一般"
        elif energy < 0.75:
            vigor = "挺有精神"
        else:
            vigor = "精力充沛"
        tail = f"，刚刚的情绪：{'、'.join(m.recent[-3:])}" if m.recent else ""
        return f"{label}，{vigor}{tail}"
