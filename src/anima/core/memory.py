"""Long-term memory: people, facts, conversations, journal, reminders.

One SQLite file per bot (``data/<bot>/memory.db``). Small, inspectable, easy to back up.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    key        TEXT PRIMARY KEY,          -- platform:uid
    platform   TEXT NOT NULL,
    uid        TEXT NOT NULL,
    name       TEXT NOT NULL,
    nickname   TEXT,                      -- what she calls them, once it's settled
    affinity   REAL NOT NULL DEFAULT 0.3, -- -1 (dislike) .. 1 (close friend)
    birthday   TEXT,                      -- MM-DD
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL,
    msg_count  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_key        TEXT NOT NULL,
    platform_msg_id TEXT,
    sender_key      TEXT NOT NULL,       -- 'self' for the bot
    sender_name     TEXT NOT NULL,
    is_self         INTEGER NOT NULL DEFAULT 0,
    text            TEXT NOT NULL,
    ts              REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_key, id);
CREATE TABLE IF NOT EXISTS facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    subject    TEXT NOT NULL,            -- user key, 'self', or a chat key
    content    TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3,
    source     TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
CREATE TABLE IF NOT EXISTS chats (
    key            TEXT PRIMARY KEY,
    platform       TEXT NOT NULL,
    kind           TEXT NOT NULL,
    title          TEXT NOT NULL DEFAULT '',
    last_active    REAL,
    last_self      REAL,
    reflected_upto INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_key   TEXT NOT NULL,
    user_key   TEXT,
    user_name  TEXT,
    due        REAL NOT NULL,
    text       TEXT NOT NULL,
    done       INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
    date       TEXT NOT NULL,
    kind       TEXT NOT NULL,            -- plan | diary
    content    TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (date, kind)
);
CREATE TABLE IF NOT EXISTS treasures (  -- her collection of beautiful sentences
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key   TEXT,
    user_name  TEXT,
    text       TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_PUNCT = re.compile(r"[\s\W_]+", re.UNICODE)


def _norm(text: str) -> str:
    return _PUNCT.sub("", text.lower())


def similar(a: str, b: str, threshold: float = 0.75) -> bool:
    """Cheap near-duplicate check that works for Chinese (character-set overlap)."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    sa, sb = set(na), set(nb)
    return len(sa & sb) / len(sa | sb) >= threshold


@dataclass
class User:
    key: str
    platform: str
    uid: str
    name: str
    nickname: str | None
    affinity: float
    birthday: str | None
    first_seen: float
    last_seen: float
    msg_count: int

    @property
    def call_name(self) -> str:
        return self.nickname or self.name


@dataclass
class MessageRow:
    id: int
    chat_key: str
    platform_msg_id: str | None
    sender_key: str
    sender_name: str
    is_self: bool
    text: str
    ts: float


@dataclass
class Fact:
    id: int
    subject: str
    content: str
    importance: int
    created_at: float


class Memory:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.db: aiosqlite.Connection | None = None

    async def open(self) -> Memory:
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.executescript(SCHEMA)
        await self.db.commit()
        return self

    async def close(self) -> None:
        if self.db:
            await self.db.close()
            self.db = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self.db is not None, "Memory.open() first"
        return self.db

    # ------------------------------------------------------------ people

    async def touch_user(self, platform: str, uid: str, name: str, ts: float | None = None) -> User:
        ts = ts or time.time()
        key = f"{platform}:{uid}"
        await self.conn.execute(
            """INSERT INTO users (key, platform, uid, name, first_seen, last_seen, msg_count)
               VALUES (?, ?, ?, ?, ?, ?, 1)
               ON CONFLICT(key) DO UPDATE SET name=excluded.name, last_seen=excluded.last_seen,
                                              msg_count=users.msg_count + 1""",
            (key, platform, uid, name or uid, ts, ts),
        )
        await self.conn.commit()
        user = await self.get_user(key)
        assert user is not None
        return user

    async def get_user(self, key: str) -> User | None:
        async with self.conn.execute("SELECT * FROM users WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
        return User(**dict(row)) if row else None

    async def find_users(self, name: str, limit: int = 5) -> list[User]:
        async with self.conn.execute(
            "SELECT * FROM users WHERE name LIKE ? OR nickname LIKE ? ORDER BY last_seen DESC LIMIT ?",
            (f"%{name}%", f"%{name}%", limit),
        ) as cur:
            return [User(**dict(r)) for r in await cur.fetchall()]

    async def update_user(self, key: str, **fields: Any) -> None:
        allowed = {"nickname", "birthday", "name"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        cols = ", ".join(f"{k} = ?" for k in sets)
        await self.conn.execute(f"UPDATE users SET {cols} WHERE key = ?", (*sets.values(), key))
        await self.conn.commit()

    async def adjust_affinity(self, key: str, delta: float) -> None:
        await self.conn.execute(
            "UPDATE users SET affinity = MAX(-1.0, MIN(1.0, affinity + ?)) WHERE key = ?", (delta, key)
        )
        await self.conn.commit()

    async def birthdays_on(self, mmdd: str) -> list[User]:
        async with self.conn.execute("SELECT * FROM users WHERE birthday = ?", (mmdd,)) as cur:
            return [User(**dict(r)) for r in await cur.fetchall()]

    # ------------------------------------------------------------ conversation

    async def record(
        self,
        chat_key: str,
        sender_key: str,
        sender_name: str,
        text: str,
        *,
        is_self: bool = False,
        ts: float | None = None,
        platform_msg_id: str | None = None,
        chat_title: str = "",
    ) -> int:
        ts = ts or time.time()
        platform, kind, _ = (chat_key.split(":", 2) + ["", ""])[:3]
        cur = await self.conn.execute(
            """INSERT INTO messages (chat_key, platform_msg_id, sender_key, sender_name, is_self, text, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (chat_key, platform_msg_id, sender_key, sender_name, int(is_self), text, ts),
        )
        await self.conn.execute(
            """INSERT INTO chats (key, platform, kind, title, last_active, last_self)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   last_active = excluded.last_active,
                   title = CASE WHEN excluded.title != '' THEN excluded.title ELSE chats.title END,
                   last_self = COALESCE(excluded.last_self, chats.last_self)""",
            (chat_key, platform, kind, chat_title, ts, ts if is_self else None),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def recent(self, chat_key: str, limit: int = 40) -> list[MessageRow]:
        async with self.conn.execute(
            "SELECT * FROM messages WHERE chat_key = ? ORDER BY id DESC LIMIT ?", (chat_key, limit)
        ) as cur:
            rows = await cur.fetchall()
        return [self._msg(r) for r in reversed(rows)]

    async def messages_after(self, chat_key: str, after_id: int, limit: int = 200) -> list[MessageRow]:
        async with self.conn.execute(
            "SELECT * FROM messages WHERE chat_key = ? AND id > ? ORDER BY id ASC LIMIT ?",
            (chat_key, after_id, limit),
        ) as cur:
            return [self._msg(r) for r in await cur.fetchall()]

    async def messages_between(self, start_ts: float, end_ts: float, limit: int = 400) -> list[MessageRow]:
        async with self.conn.execute(
            "SELECT * FROM messages WHERE ts >= ? AND ts < ? ORDER BY id ASC LIMIT ?",
            (start_ts, end_ts, limit),
        ) as cur:
            return [self._msg(r) for r in await cur.fetchall()]

    async def chat(self, chat_key: str) -> dict[str, Any] | None:
        async with self.conn.execute("SELECT * FROM chats WHERE key = ?", (chat_key,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def chats(self, kind: str | None = None) -> list[dict[str, Any]]:
        query, args = "SELECT * FROM chats", ()
        if kind:
            query, args = query + " WHERE kind = ?", (kind,)
        async with self.conn.execute(query + " ORDER BY last_active DESC", args) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def set_reflected(self, chat_key: str, upto_id: int) -> None:
        await self.conn.execute("UPDATE chats SET reflected_upto = ? WHERE key = ?", (upto_id, chat_key))
        await self.conn.commit()

    @staticmethod
    def _msg(row: aiosqlite.Row) -> MessageRow:
        d = dict(row)
        d["is_self"] = bool(d["is_self"])
        return MessageRow(**d)

    # ------------------------------------------------------------ facts

    async def add_fact(self, subject: str, content: str, importance: int = 3, source: str = "") -> bool:
        """Store a fact unless she already knows it. Returns True if it was new."""
        content = content.strip()
        if not content:
            return False
        for existing in await self.facts(subject, limit=200):
            if similar(existing.content, content):
                if importance > existing.importance:
                    await self.conn.execute(
                        "UPDATE facts SET importance = ? WHERE id = ?", (importance, existing.id)
                    )
                    await self.conn.commit()
                return False
        await self.conn.execute(
            "INSERT INTO facts (subject, content, importance, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (subject, content, max(1, min(5, int(importance))), source, time.time()),
        )
        await self.conn.commit()
        return True

    async def facts(self, subject: str, limit: int = 12) -> list[Fact]:
        async with self.conn.execute(
            """SELECT id, subject, content, importance, created_at FROM facts
               WHERE subject = ? ORDER BY importance DESC, created_at DESC LIMIT ?""",
            (subject, limit),
        ) as cur:
            return [Fact(**dict(r)) for r in await cur.fetchall()]

    async def forget(self, fact_id: int) -> None:
        await self.conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        await self.conn.commit()

    async def search_facts(self, keywords: list[str], subjects: list[str] | None = None, limit: int = 8) -> list[Fact]:
        keywords = [k for k in keywords if k.strip()]
        if not keywords:
            return []
        where = " OR ".join("content LIKE ?" for _ in keywords)
        args: list[Any] = [f"%{k}%" for k in keywords]
        query = f"SELECT id, subject, content, importance, created_at FROM facts WHERE ({where})"
        if subjects:
            query += f" AND subject IN ({','.join('?' for _ in subjects)})"
            args += subjects
        query += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        async with self.conn.execute(query, (*args, limit)) as cur:
            return [Fact(**dict(r)) for r in await cur.fetchall()]

    async def search_messages(self, keywords: list[str], chat_key: str | None = None, limit: int = 8) -> list[MessageRow]:
        keywords = [k for k in keywords if k.strip()]
        if not keywords:
            return []
        where = " OR ".join("text LIKE ?" for _ in keywords)
        args: list[Any] = [f"%{k}%" for k in keywords]
        query = f"SELECT * FROM messages WHERE ({where})"
        if chat_key:
            query += " AND chat_key = ?"
            args.append(chat_key)
        query += " ORDER BY id DESC LIMIT ?"
        async with self.conn.execute(query, (*args, limit)) as cur:
            return [self._msg(r) for r in await cur.fetchall()]

    # ------------------------------------------------------------ reminders

    async def add_reminder(self, chat_key: str, due: float, text: str, user_key: str = "", user_name: str = "") -> int:
        cur = await self.conn.execute(
            "INSERT INTO reminders (chat_key, user_key, user_name, due, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_key, user_key, user_name, due, text, time.time()),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def due_reminders(self, now_ts: float) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM reminders WHERE done = 0 AND due <= ? ORDER BY due", (now_ts,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def finish_reminder(self, reminder_id: int) -> None:
        await self.conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))
        await self.conn.commit()

    # ------------------------------------------------------------ journal

    async def journal_get(self, date: str, kind: str) -> str | None:
        async with self.conn.execute(
            "SELECT content FROM journal WHERE date = ? AND kind = ?", (date, kind)
        ) as cur:
            row = await cur.fetchone()
        return row["content"] if row else None

    async def journal_put(self, date: str, kind: str, content: str) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO journal (date, kind, content, created_at) VALUES (?, ?, ?, ?)",
            (date, kind, content, time.time()),
        )
        await self.conn.commit()

    async def journal_list(self, kind: str, limit: int = 30) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT date, content FROM journal WHERE kind = ? ORDER BY date DESC LIMIT ?", (kind, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ------------------------------------------------------------ treasures

    async def add_treasure(self, text: str, user_key: str = "", user_name: str = "") -> bool:
        async with self.conn.execute("SELECT text FROM treasures ORDER BY id DESC LIMIT 200") as cur:
            if any(similar(r["text"], text, 0.85) for r in await cur.fetchall()):
                return False
        await self.conn.execute(
            "INSERT INTO treasures (user_key, user_name, text, created_at) VALUES (?, ?, ?, ?)",
            (user_key, user_name, text, time.time()),
        )
        await self.conn.commit()
        return True

    async def treasures(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT user_name, text, created_at FROM treasures ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ------------------------------------------------------------ key/value state

    async def get_state(self, key: str, default: Any = None) -> Any:
        async with self.conn.execute("SELECT value FROM state WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
        return json.loads(row["value"]) if row else default

    async def set_state(self, key: str, value: Any) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False))
        )
        await self.conn.commit()
