"""世界书 (lorebook): background she only "remembers" when the conversation touches it.

Each entry has trigger keys; when a key shows up in the last few messages, the entry's content
goes into her private scene for that turn. Constant entries are always there. Books are JSON
files in ``bots/<name>/lorebook/``, and SillyTavern world books / character books import as-is.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LoreEntry:
    keys: list[str]
    content: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    secondary: list[str] = field(default_factory=list)  # with selective: one of these must match too
    selective: bool = False
    constant: bool = False
    enabled: bool = True
    priority: int = 100  # higher goes in first when the budget is tight
    comment: str = ""

    def matches(self, text: str) -> bool:
        if not self.enabled:
            return False
        if self.constant:
            return True
        if not any(_hit(k, text) for k in self.keys):
            return False
        return not (self.selective and self.secondary) or any(_hit(k, text) for k in self.secondary)


def _hit(key: str, text: str) -> bool:
    key = key.strip()
    if not key:
        return False
    regex = re.fullmatch(r"/(.+)/([imsx]*)", key)
    if regex:
        flags = sum(getattr(re, f.upper()) for f in regex.group(2))
        try:
            return re.search(regex.group(1), text, flags) is not None
        except re.error:
            return False
    return key.lower() in text.lower()


def _clean_name(name: str) -> str:
    return re.sub(r"[^\w一-鿿-]+", "_", name).strip("_") or "book"


class Lorebook:
    def __init__(self, folder: Path):
        self.folder = folder
        self.books: dict[str, list[LoreEntry]] = {}
        self.reload()

    def reload(self) -> None:
        self.books = {}
        if not self.folder.exists():
            return
        for path in sorted(self.folder.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            entries = data.get("entries", []) if isinstance(data, dict) else data
            if isinstance(entries, dict):  # a SillyTavern file dropped in directly
                entries = from_sillytavern(data)
                self.books[path.stem] = entries
                continue
            self.books[path.stem] = [LoreEntry(**{k: v for k, v in e.items() if k in LoreEntry.__dataclass_fields__})
                                     for e in entries]

    def save(self, name: str, entries: list[LoreEntry]) -> str:
        name = _clean_name(name)
        self.folder.mkdir(parents=True, exist_ok=True)
        payload = {"name": name, "entries": [asdict(e) for e in entries]}
        (self.folder / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.books[name] = entries
        return name

    def delete(self, name: str) -> None:
        (self.folder / f"{_clean_name(name)}.json").unlink(missing_ok=True)
        self.books.pop(name, None)

    def entries(self) -> list[LoreEntry]:
        return [e for book in self.books.values() for e in book]

    def triggered(self, text: str, budget: int = 1800, replacements: dict[str, str] | None = None) -> list[str]:
        """Contents to bring up for this text, highest priority first, within a character budget."""
        hits = sorted((e for e in self.entries() if e.matches(text)), key=lambda e: (-int(e.constant), -e.priority))
        out, used = [], 0
        for entry in hits:
            content = entry.content.strip()
            for token, value in (replacements or {}).items():
                content = content.replace(token, value)
            if used + len(content) > budget:
                continue
            out.append(content)
            used += len(content)
        return out


def from_sillytavern(data: dict[str, Any]) -> list[LoreEntry]:
    """SillyTavern world info (``{"entries": {"0": {...}}}``) or a character card's ``character_book``."""
    raw = data.get("entries", [])
    items = raw.values() if isinstance(raw, dict) else raw
    entries = []
    for e in items:
        keys = e.get("key") or e.get("keys") or []
        content = e.get("content") or ""
        if not content:
            continue
        entries.append(LoreEntry(
            keys=[k for k in keys if isinstance(k, str)],
            content=content,
            secondary=[k for k in (e.get("keysecondary") or e.get("secondary_keys") or []) if isinstance(k, str)],
            selective=bool(e.get("selective")),
            constant=bool(e.get("constant")),
            enabled=not (e.get("disable") or e.get("enabled") is False),
            priority=int(e.get("order") or e.get("insertion_order") or e.get("priority") or 100),
            comment=e.get("comment") or e.get("name") or "",
        ))
    return entries
