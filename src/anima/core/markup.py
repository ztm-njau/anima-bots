"""Turn the model's reply into chat actions.

The model writes plain lines (one per chat bubble) with a few inline tags::

    笑死我了[sticker:laugh]
    你这也太离谱了吧
    [voice]晚安呀[/voice]
    [mood:happy]

Anything that looks like markdown is flattened, because no chat app renders it.
"""

from __future__ import annotations

import re

from anima.core.events import Bubble, Reply, Segment
from anima.core.stickers import StickerBook

_VOICE = re.compile(r"\[voice\](.+?)\[/?voice\]", re.S | re.I)  # tolerate a missing slash
_MOOD = re.compile(r"\[mood:\s*([a-zA-Z_]+)\s*\]", re.I)
_FLAG = re.compile(r"\[(poke|reply|silent)\]", re.I)
_INLINE = re.compile(r"\[(sticker|meme):\s*([^\]\s]{1,24})\s*\]", re.I)
_LEFTOVER = re.compile(r"\[(?:sticker|meme|mood|voice|/voice)[^\]]*\]", re.I)
_MD_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)、])\s+")
_MD_HEADER = re.compile(r"^\s*#{1,6}\s+")
_MD_EMPH = re.compile(r"(\*\*|__|\*|`)")
_THINK = re.compile(r"<think>.*?</think>", re.S)
_NARRATION = re.compile(r"^[（(【][^）)】]{9,}[）)】]$")  # "（突然想起了一部老电影……）"


def _speaker_prefix(names: tuple[str, ...]) -> re.Pattern:
    alternatives = "|".join(re.escape(n) for n in sorted({*names, "我"}, key=len, reverse=True) if n)
    return re.compile(rf"^\s*(?:{alternatives})\s*[:：]\s*")


def clean(raw: str, names: tuple[str, ...] = ()) -> str:
    speaker = _speaker_prefix(names)
    text = _THINK.sub("", raw or "")
    lines = []
    for line in text.replace("\r", "").split("\n"):
        line = _MD_HEADER.sub("", line)
        line = _MD_BULLET.sub("", line)
        line = _MD_EMPH.sub("", line)
        line = speaker.sub("", line)
        line = line.strip().strip('"“”')
        if line and not _NARRATION.match(line):
            lines.append(line)
    return "\n".join(lines)


def parse_reply(raw: str, stickers: StickerBook, max_bubbles: int = 5, names: tuple[str, ...] = ()) -> Reply:
    """``names`` are hers: a line starting "可乐：" loses the prefix."""
    reply = Reply()
    text = clean(raw, names)

    reply.moods = [m.lower() for m in _MOOD.findall(text)]
    text = _MOOD.sub("", text)

    flags = {f.lower() for f in _FLAG.findall(text)}
    text = _FLAG.sub("", text)
    if "poke" in flags:
        reply.poke = "*"  # the brain fills in who
    if "reply" in flags:
        reply.quote = "*"

    bubbles: list[Bubble] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        voice = _VOICE.search(line)
        if voice:
            spoken = _LEFTOVER.sub("", voice.group(1)).strip()
            if spoken:
                bubbles.append(Bubble(voice=spoken, source=f"[voice]{spoken}[/voice]"))
            line = _VOICE.sub("", line).strip()
            if not line:
                continue
        segments = _segments(line, stickers)
        if segments:
            bubbles.append(Bubble(segments=segments, source=line))

    if "silent" in flags and not bubbles:
        reply.silent = True
        reply.poke = None
        return reply

    if len(bubbles) > max_bubbles:
        head, tail = bubbles[: max_bubbles - 1], bubbles[max_bubbles - 1 :]
        merged = Bubble(source=" ".join(b.source for b in tail if not b.voice))
        for b in tail:
            if not b.voice:
                if merged.segments and b.segments and b.segments[0].type == "text":
                    merged.segments.append(Segment("text", " "))
                merged.segments.extend(b.segments)
        bubbles = head + ([merged] if merged.segments else [])

    reply.bubbles = bubbles
    reply.silent = not bubbles and not reply.poke
    return reply


def _segments(line: str, stickers: StickerBook) -> list[Segment]:
    segments: list[Segment] = []
    pos = 0
    for match in _INLINE.finditer(line):
        before = line[pos : match.start()]
        if before.strip():
            segments.append(Segment("text", _LEFTOVER.sub("", before)))
        kind, key = match.group(1).lower(), match.group(2).lower()
        if kind == "sticker" and key in stickers:
            segments.append(Segment("sticker", key))
        elif kind == "meme":
            segments.append(Segment("meme", key))
        pos = match.end()
    rest = line[pos:]
    if rest.strip():
        segments.append(Segment("text", _LEFTOVER.sub("", rest)))
    # Merge neighbouring text segments, drop empties.
    merged: list[Segment] = []
    for seg in segments:
        if seg.type == "text":
            seg.value = seg.value.replace("  ", " ")
            if not seg.value.strip():
                continue
            if merged and merged[-1].type == "text":
                merged[-1].value += seg.value
                continue
        merged.append(seg)
    if merged and merged[0].type == "text":
        merged[0].value = merged[0].value.lstrip()
    if merged and merged[-1].type == "text":
        merged[-1].value = merged[-1].value.rstrip()
    return merged
