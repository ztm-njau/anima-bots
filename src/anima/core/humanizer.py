"""Human rhythm: read time, typing time, bubble shaping.

People don't answer instantly, don't type at 2,000 characters a second, and send three
short messages instead of one paragraph. This module owns all of that.
"""

from __future__ import annotations

import random
import re

from anima.config import BehaviorConfig
from anima.core.events import Bubble, Segment

_SENTENCE_END = re.compile(r"(?<=[。！？!?~～…])")


class Humanizer:
    def __init__(self, cfg: BehaviorConfig, rng: random.Random | None = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.scale = 1.0 if cfg.delays else 0.0

    # ------------------------------------------------------------ timing

    def reading_delay(self, chars: int) -> float:
        base = 0.6 + chars / 25.0
        return min(6.0, base * self.rng.uniform(0.7, 1.3)) * self.scale

    def typing_delay(self, bubble: Bubble) -> float:
        if bubble.voice:
            return min(12.0, 1.5 + len(bubble.voice) / 4.0) * self.scale
        if bubble.is_sticker_only:
            return self.rng.uniform(0.6, 1.6) * self.scale
        chars = len(bubble.text)
        seconds = chars / self.cfg.typing_cps * self.rng.uniform(0.75, 1.35)
        return max(0.8, min(9.0, seconds)) * self.scale

    def gap(self) -> float:
        return self.rng.uniform(0.25, 1.1) * self.scale

    # ------------------------------------------------------------ shaping

    def shape(self, bubbles: list[Bubble]) -> list[Bubble]:
        """Split run-on bubbles, merge overflow, tidy punctuation the way people text."""
        out: list[Bubble] = []
        for bubble in bubbles:
            if bubble.voice or bubble.is_sticker_only or len(bubble.text) <= 60:
                out.append(bubble)
                continue
            out.extend(self._split_long(bubble))
        if len(out) > self.cfg.max_bubbles:
            keep, overflow = out[: self.cfg.max_bubbles - 1], out[self.cfg.max_bubbles - 1 :]
            merged = Bubble(segments=[s for b in overflow for s in b.segments], source=" ".join(b.source for b in overflow))
            out = keep + [merged]
        for bubble in out:
            self._tidy(bubble)
        return out

    def _split_long(self, bubble: Bubble) -> list[Bubble]:
        text = bubble.text
        pieces = [p for p in _SENTENCE_END.split(text) if p.strip()]
        if len(pieces) < 2:
            return [bubble]
        chunks, current = [], ""
        for piece in pieces:
            if current and len(current) + len(piece) > 45:
                chunks.append(current)
                current = piece
            else:
                current += piece
        if current:
            chunks.append(current)
        stickers = [s for s in bubble.segments if s.type != "text"]
        result = [Bubble(segments=[Segment("text", c.strip())], source=c.strip()) for c in chunks]
        if stickers:
            result[-1].segments.extend(stickers)
        return result

    def _tidy(self, bubble: Bubble) -> None:
        for seg in bubble.segments:
            if seg.type != "text":
                continue
            value = seg.value.strip()
            # Most people drop the final full stop in chat. Keep it sometimes, for variety.
            if value.endswith("。") and self.rng.random() < 0.85:
                value = value[:-1]
            seg.value = value
        bubble.segments = [s for s in bubble.segments if s.type != "text" or s.value]
