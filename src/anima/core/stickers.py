"""Stickers: one emotional vocabulary, rendered natively on every platform.

The model writes ``[sticker:facepalm]``; QQ gets face #264, Bilibili gets ``[捂脸]``,
WeChat gets ``[捂脸]``, and anywhere else gets 🤦.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Sticker:
    key: str
    desc: str
    unicode: str
    native: dict[str, str | int] = field(default_factory=dict)


class StickerBook:
    PLATFORMS = ("qq", "bilibili", "wechat", "douyin")

    def __init__(self, table: dict):
        self.stickers: dict[str, Sticker] = {}
        for key, spec in table.items():
            if not isinstance(spec, dict):
                continue
            native = {p: spec[p] for p in self.PLATFORMS if p in spec}
            self.stickers[key] = Sticker(key, spec.get("desc", key), spec.get("unicode", ""), native)

    def __contains__(self, key: str) -> bool:
        return key in self.stickers

    def keys(self) -> list[str]:
        return list(self.stickers)

    def menu(self) -> str:
        """For the system prompt: ``laugh(笑哭) doge(狗头保命) ...``."""
        return " ".join(f"{s.key}({s.desc})" for s in self.stickers.values())

    def render(self, key: str, platform: str) -> tuple[str, str]:
        """Return ``("face", id)`` for a native QQ face, else ``("text", code-or-emoji)``."""
        sticker = self.stickers.get(key)
        if not sticker:
            return ("text", "")
        native = sticker.native.get(platform)
        if platform == "qq" and isinstance(native, int):
            return ("face", str(native))
        if isinstance(native, str) and native:
            return ("text", native)
        return ("text", sticker.unicode)

    def emoji(self, key: str) -> str:
        sticker = self.stickers.get(key)
        return sticker.unicode if sticker else ""
