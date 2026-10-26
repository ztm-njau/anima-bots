"""Her 表情包 collection: real sticker images she sends by mood or meme, and grows by herself.

Two sources: packs you drop into ``bots/<name>/memes/<tag>/`` (the folder name is the tag) and
stickers she "steals" from chats, saved in ``data/<name>/stickers/`` and tagged by a vision model
the way a person remembers a sticker ("狗头 无语 摸鱼").
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from anima.core.recall import bm25, terms

if TYPE_CHECKING:
    from anima.config import Bot
    from anima.core.memory import Memory

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


@dataclass
class Sticker:
    id: str
    path: Path
    tags: list[str]
    description: str = ""
    source: str = ""
    uses: int = 0

    @property
    def media_type(self) -> str:
        ext = self.path.suffix.lower().lstrip(".")
        return "image/jpeg" if ext == "jpg" else f"image/{ext}"


class StickerLibrary:
    def __init__(self, bot: Bot, memory: Memory):
        self.bot = bot
        self.memory = memory
        self.folder = bot.data_dir / "stickers"

    def _bundled(self) -> list[Sticker]:
        root = self.bot.dir / "memes"
        out = []
        for folder in sorted(p for p in root.glob("*") if p.is_dir()):
            for path in sorted(folder.iterdir()):
                if path.suffix.lower() in IMAGE_EXT:
                    stem_tags = [t for t in re.split(r"[\s_,，、-]+", path.stem) if t and not t.isdigit()]
                    out.append(Sticker(f"b:{folder.name}/{path.name}", path, [folder.name, *stem_tags], source="pack"))
        return out

    async def all(self) -> list[Sticker]:
        collected = [
            Sticker(str(row["id"]), self.folder / row["file"], row["tags"].split(), row["description"], row["source"],
                    row["uses"])
            for row in await self.memory.stickers()
            if (self.folder / row["file"]).exists()
        ]
        return self._bundled() + collected

    async def menu(self, limit: int = 24) -> list[str]:
        """The tags she'd think of first, most common first."""
        counts: dict[str, int] = {}
        for sticker in await self.all():
            for tag in sticker.tags[:3]:
                counts[tag] = counts.get(tag, 0) + 1
        return [t for t, _ in sorted(counts.items(), key=lambda x: -x[1])][:limit]

    async def pick(self, query: str) -> Sticker | None:
        stickers = await self.all()
        if not stickers:
            return None
        exact = [s for s in stickers if query in s.tags]
        if not exact:
            scores = bm25(terms(query) or [query], [terms(" ".join(s.tags) + " " + s.description) for s in stickers])
            ranked = [s for score, s in sorted(zip(scores, stickers, strict=True), key=lambda x: -x[0]) if score > 0]
            exact = ranked[:3]
        if not exact:
            return None
        # Favour ones she hasn't overused, like a person rotating their favourites.
        weights = [1 / (1 + s.uses) for s in exact]
        chosen = random.choices(exact, weights=weights)[0]
        if not chosen.id.startswith("b:"):
            await self.memory.update_sticker(int(chosen.id), uses=chosen.uses + 1)
        return chosen

    async def add(self, data: bytes, ext: str, tags: list[str], description: str = "", source: str = "") -> int | None:
        sha = hashlib.sha1(data).hexdigest()
        self.folder.mkdir(parents=True, exist_ok=True)
        ext = ext if ext.startswith(".") else f".{ext}"
        name = f"{sha[:16]}{ext.lower() if ext.lower() in IMAGE_EXT else '.png'}"
        path = self.folder / name
        if not path.exists():
            path.write_bytes(data)
        return await self.memory.add_sticker(name, sha, " ".join(t for t in tags if t), description, source)

    async def remove(self, sticker_id: int) -> None:
        row = await self.memory.delete_sticker(sticker_id)
        if row:
            (self.folder / row["file"]).unlink(missing_ok=True)

    async def count(self) -> int:
        return len(await self.all())

    def path_for(self, sticker_id: str) -> Path | None:
        if sticker_id.startswith("b:"):
            path = self.bot.dir / "memes" / sticker_id[2:]
            return path if path.exists() and path.resolve().is_relative_to((self.bot.dir / "memes").resolve()) else None
        return None


def parse_caption(text: str) -> tuple[str, list[str]]:
    """``"一只狗头斜眼看人｜狗头 嘲讽 无语"`` -> (description, tags)."""
    desc, _, tags = text.strip().partition("｜")
    if not tags:
        desc, _, tags = text.strip().partition("|")
    tag_list = [t.strip("#，, 。") for t in re.split(r"[\s,，、]+", tags) if t.strip("#，, 。")]
    return desc.strip()[:60], tag_list[:5]
