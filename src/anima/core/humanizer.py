"""Human rhythm: read time, typing time, bubble shaping.

People don't answer instantly, don't type at 2,000 characters a second, and send three
short messages instead of one paragraph. This module owns all of that.
"""

from __future__ import annotations

import math
import random
import re

from anima.config import BehaviorConfig
from anima.core.events import Bubble, Segment
from anima.core.segment import split_text

_LATIN_WORD = re.compile(r"[A-Za-z0-9]+")
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿]")


class Humanizer:
    def __init__(self, cfg: BehaviorConfig, rng: random.Random | None = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.scale = 1.0 if cfg.delays else 0.0

    # ------------------------------------------------------------ timing

    def reading_delay(self, chars: int) -> float:
        base = 0.6 + chars / 25.0
        return min(6.0, base * self.rng.uniform(0.7, 1.3)) * self.scale

    def keystrokes(self, text: str) -> float:
        """Rough effort to type ``text`` on a phone, in Chinese-character units."""
        latin = _LATIN_WORD.findall(text)
        emoji = len(_EMOJI.findall(text))
        rest = len(_LATIN_WORD.sub("", _EMOJI.sub("", text)))
        punct = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
        return rest - punct * 0.6 + sum(len(w) for w in latin) * 0.35 + emoji * 2.5

    def typing_delay(self, bubble: Bubble) -> float:
        if bubble.voice:
            return min(12.0, 1.5 + len(bubble.voice) / 4.0) * self.scale
        if bubble.is_sticker_only:
            return self.rng.uniform(0.6, 1.6) * self.scale  # finding the sticker
        seconds = self.keystrokes(bubble.text) / self.cfg.typing_cps * self.rng.uniform(0.8, 1.25)
        if any(s.type != "text" for s in bubble.segments):
            seconds += self.rng.uniform(0.4, 1.0)
        return max(0.7, min(9.0, seconds)) * self.scale

    def gap(self) -> float:
        return self.rng.uniform(0.25, 1.1) * self.scale

    def plan(self, bubbles: list[Bubble], budget: float | None = None) -> list[float]:
        """Seconds of 'typing…' before each bubble: a moment to think, then typing time.

        A long reply is squeezed to fit ``budget`` the way people type faster when they have a
        lot to say, but no bubble drops below a beat.
        """
        if not bubbles:
            return []
        total_chars = sum(len(b.text or b.voice or "") for b in bubbles)
        think = (0.3 + 0.12 * math.sqrt(total_chars)) * self.rng.uniform(0.7, 1.3) * self.scale
        delays = [self.typing_delay(b) + (self.gap() if i else think) for i, b in enumerate(bubbles)]
        budget = self.cfg.reply_budget if budget is None else budget
        total = sum(delays)
        if budget and total > budget * self.scale > 0:
            floor = 0.6 * self.scale
            factor = max(0.0, budget * self.scale - floor * len(delays)) / max(1e-6, total - floor * len(delays))
            delays = [floor + (d - floor) * min(1.0, factor) for d in delays]
        return delays

    # ------------------------------------------------------------ shaping

    def shape(self, bubbles: list[Bubble], max_bubbles: int | None = None, cfg: BehaviorConfig | None = None) -> list[Bubble]:
        """Split run-on bubbles, merge overflow, tidy punctuation the way people text."""
        cfg = cfg or self.cfg
        max_bubbles = max_bubbles or cfg.max_bubbles
        out: list[Bubble] = []
        for bubble in bubbles:
            if bubble.voice or bubble.is_sticker_only or len(bubble.text) <= cfg.bubble_split:
                out.append(bubble)
                continue
            out.extend(self._split_long(bubble, cfg))
        if len(out) > max_bubbles:
            keep, overflow = out[: max_bubbles - 1], out[max_bubbles - 1 :]
            if any(b.voice for b in overflow):
                keep, overflow = out[:max_bubbles], []
            if overflow:
                segments: list[Segment] = []
                for b in overflow:
                    if segments and b.segments and b.segments[0].type == "text" and segments[-1].type == "text":
                        segments.append(Segment("text", " "))
                    segments.extend(b.segments)
                keep.append(Bubble(segments=segments, source=" ".join(b.source for b in overflow)))
            out = keep
        for bubble in out:
            self._tidy(bubble)
        return [b for b in out if b.segments or b.voice]

    def _split_long(self, bubble: Bubble, cfg: BehaviorConfig) -> list[Bubble]:
        """Cut the text at natural breaks; stickers stay right after the words they followed."""
        result: list[Bubble] = []
        current: list[Segment] = []
        for seg in bubble.segments:
            if seg.type != "text":
                current.append(seg)
                continue
            for j, piece in enumerate(split_text(seg.value, cfg.bubble_split, cfg.bubble_hard)):
                if j and current:  # every further piece starts a new bubble
                    result.append(Bubble(segments=current))
                    current = []
                if current and current[-1].type == "text":
                    current[-1] = Segment("text", current[-1].value + piece)
                else:
                    current.append(Segment("text", piece))
        if current:
            result.append(Bubble(segments=current))
        if len(result) < 2:
            return [bubble]
        for b in result:
            b.source = "".join(s.value if s.type == "text" else f"[{s.type}:{s.value}]" for s in b.segments)
        return result

    def _tidy(self, bubble: Bubble) -> None:
        for seg in bubble.segments:
            if seg.type != "text":
                continue
            value = seg.value.strip()
            # Most people drop the final full stop in chat. Keep it sometimes, for variety.
            if value.endswith("。") and not value.endswith("。。") and self.rng.random() < 0.85:
                value = value[:-1]
            seg.value = value
        bubble.segments = [s for s in bubble.segments if s.type != "text" or s.value]
