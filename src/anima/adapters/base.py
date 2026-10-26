"""The contract every platform adapter fulfils. The brain only ever talks to this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from anima.core.events import Bubble, Chat, Incoming

if TYPE_CHECKING:
    from anima.core.brain import Brain


class Adapter(ABC):
    platform: str = "base"
    # Optional abilities: typing, poke, voice, quote, read, image, dynamic
    capabilities: frozenset[str] = frozenset()
    # Request/response platforms with hard deadlines (WeChat official accounts) skip human pacing.
    instant: bool = False

    def __init__(self) -> None:
        self.brain: Brain | None = None

    async def start(self, brain: Brain) -> None:
        self.brain = brain

    async def stop(self) -> None:
        pass

    def can_speak(self, chat: Chat) -> bool:
        return True

    @abstractmethod
    async def send(self, chat: Chat, bubble: Bubble, quote: str | None = None) -> str | None:
        """Send one bubble. Returns the platform message id when there is one."""

    async def typing(self, chat: Chat, on: bool) -> None:
        pass

    async def poke(self, chat: Chat, user_id: str) -> None:
        pass

    async def mark_read(self, chat: Chat, ev: Incoming) -> None:
        pass

    async def answer_request(self, request: dict, approve: bool) -> bool:
        """Accept or refuse a friend request / group invite. Optional."""
        return False

    async def remove_friend(self, user_id: str) -> bool:
        return False

    async def leave_group(self, group_id: str) -> bool:
        return False

    async def post(self, text: str) -> str | None:
        """Publish to the bot's own feed (e.g. a Bilibili dynamic). Optional."""
        return None

    def flatten(self, bubble: Bubble) -> str:
        """Bubble as plain text, stickers rendered with this platform's text codes."""
        assert self.brain is not None
        out = []
        for seg in bubble.segments:
            if seg.type == "text":
                out.append(seg.value)
            elif seg.type == "sticker":
                out.append(self.brain.stickers.render(seg.value, self.platform)[1])
        return "".join(out)
