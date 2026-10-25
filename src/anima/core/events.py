"""Platform-neutral events. Every adapter translates its platform into these shapes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

ChatKind = Literal["private", "group", "live", "comment"]
EventKind = Literal["message", "poke", "comment", "danmaku", "join", "gift"]


@dataclass(frozen=True)
class Chat:
    platform: str
    kind: ChatKind
    id: str
    title: str = ""

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.kind}:{self.id}"

    @property
    def is_group_like(self) -> bool:
        return self.kind in ("group", "live", "comment")


@dataclass(frozen=True)
class Sender:
    id: str
    name: str
    is_admin: bool = False

    def user_key(self, platform: str) -> str:
        return f"{platform}:{self.id}"


@dataclass
class Image:
    """An image someone sent. ``data`` is base64 when the adapter could download it."""

    url: str | None = None
    data: str | None = None
    media_type: str = "image/jpeg"


@dataclass
class Incoming:
    chat: Chat
    sender: Sender
    text: str
    kind: EventKind = "message"
    message_id: str | None = None
    mentions_me: bool = False
    reply_to_me: bool = False
    images: list[Image] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def user_key(self) -> str:
        return self.sender.user_key(self.chat.platform)

    def render(self) -> str:
        """How this event reads in the conversation transcript."""
        body = self.text.strip()
        if self.images and "[图片]" not in body:
            body = (body + " [图片]").strip()
        if self.kind == "poke":
            body = "（戳了戳你）"
        elif self.kind == "gift":
            body = f"（送了礼物）{body}"
        elif self.kind == "join":
            body = "（加入了）"
        return body


# ---------------------------------------------------------------- outgoing


@dataclass
class Segment:
    """One piece of a chat bubble."""

    type: Literal["text", "sticker", "meme"]
    value: str


@dataclass
class Bubble:
    """One message as it lands in the chat. Most bubbles are a single text segment."""

    segments: list[Segment] = field(default_factory=list)
    voice: str | None = None  # spoken text, if this bubble is a voice note
    source: str = ""  # the line as the model wrote it; this is what goes into her history

    @property
    def text(self) -> str:
        return "".join(s.value for s in self.segments if s.type == "text")

    @property
    def is_sticker_only(self) -> bool:
        return bool(self.segments) and all(s.type != "text" for s in self.segments)

    def plain(self, sticker_render=None) -> str:
        parts = []
        for seg in self.segments:
            if seg.type == "text":
                parts.append(seg.value)
            elif sticker_render:
                parts.append(sticker_render(seg))
        if self.voice:
            parts.append(f"(语音) {self.voice}")
        return "".join(parts)


@dataclass
class Reply:
    """Everything the bot decided to do in response to a batch of events."""

    bubbles: list[Bubble] = field(default_factory=list)
    quote: str | None = None  # message id to quote-reply, when the platform supports it
    poke: str | None = None  # user id to poke back
    moods: list[str] = field(default_factory=list)
    silent: bool = False

    @property
    def empty(self) -> bool:
        return not self.bubbles and not self.poke
