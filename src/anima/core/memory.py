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
CREATE TABLE IF NOT EXISTS requests (   -- friend requests and group invites
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    platform   TEXT NOT NULL,
    kind       TEXT NOT NULL,            -- friend | group
    user_id    TEXT NOT NULL,
    user_name  TEXT NOT NULL DEFAULT '',
    group_id   TEXT,
    comment    TEXT NOT NULL DEFAULT '',
    flag       TEXT NOT NULL,
    sub_type   TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    note       TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    decided_at REAL
);
CREATE TABLE IF NOT EXISTS stickers (   -- her sticker (表情包) collection
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    file       TEXT NOT NULL,
    sha        TEXT NOT NULL UNIQUE,
    tags       TEXT NOT NULL DEFAULT '',  -- space separated
    description TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',
    uses       INTEGER NOT NULL DEFAULT 0,
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
"""

# Columns added after the first release; open() adds them to older databases.
MIGRATIONS = [
    ("users", "profile", "TEXT NOT NULL DEFAULT ''"),
    ("users", "blocked", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "silenced_until", "REAL NOT NULL DEFAULT 0"),
    ("users", "notes", "TEXT NOT NULL DEFAULT ''"),
    ("chats", "muted", "INTEGER NOT NULL DEFAULT 0"),
]

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
    profile: str = ""  # 用户画像: who they are and how to treat them
    blocked: int = 0
    silenced_until: float = 0.0  # she stopped talking to them until then
    notes: str = ""  # the owner's private notes

    @property
    def call_name(self) -> str:
        return self.nickname or self.name

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__} | {"call_name": self.call_name}


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
        for table, column, ddl in MIGRATIONS:
            async with self.db.execute(f"PRAGMA table_info({table})") as cur:
                if column not in {row[1] for row in await cur.fetchall()}:
                    await self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
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
        allowed = {"nickname", "birthday", "name", "profile", "blocked", "silenced_until", "notes", "affinity"}
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

    # ------------------------------------------------------------ people (admin)

    async def users(self, query: str = "", limit: int = 200) -> list[User]:
        async with self.conn.execute(
            "SELECT * FROM users WHERE name LIKE ? OR nickname LIKE ? OR uid LIKE ? ORDER BY last_seen DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", f"%{query}%", limit),
        ) as cur:
            return [User(**dict(r)) for r in await cur.fetchall()]

    async def delete_user_memories(self, key: str) -> None:
        await self.conn.execute("DELETE FROM facts WHERE subject = ?", (key,))
        await self.conn.execute("UPDATE users SET profile = '', nickname = NULL, birthday = NULL WHERE key = ?", (key,))
        await self.conn.commit()

    async def retract(self, chat_key: str, platform_msg_id: str) -> bool:
        """A recalled (撤回) message keeps its place in the transcript but loses its words."""
        cur = await self.conn.execute(
            "UPDATE messages SET text = '（撤回了一条消息）' WHERE chat_key = ? AND platform_msg_id = ? AND is_self = 0",
            (chat_key, platform_msg_id),
        )
        await self.conn.commit()
        return (cur.rowcount or 0) > 0

    async def is_own_message(self, chat_key: str, platform_msg_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM messages WHERE chat_key = ? AND platform_msg_id = ? AND is_self = 1 LIMIT 1",
            (chat_key, platform_msg_id),
        ) as cur:
            return await cur.fetchone() is not None

    async def update_message(self, row_id: int, text: str) -> None:
        await self.conn.execute("UPDATE messages SET text = ? WHERE id = ?", (text, row_id))
        await self.conn.commit()

    async def set_chat_muted(self, chat_key: str, muted: bool) -> None:
        platform, kind, _ = (chat_key.split(":", 2) + ["", ""])[:3]
        await self.conn.execute(
            """INSERT INTO chats (key, platform, kind, muted) VALUES (?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET muted = excluded.muted""",
            (chat_key, platform, kind, int(muted)),
        )
        await self.conn.commit()

    async def all_facts(self, limit: int = 3000) -> list[Fact]:
        async with self.conn.execute(
            "SELECT id, subject, content, importance, created_at FROM facts ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            return [Fact(**dict(r)) for r in await cur.fetchall()]

    async def older_messages(self, chat_key: str, before_id: int, limit: int = 2000) -> list[MessageRow]:
        async with self.conn.execute(
            "SELECT * FROM messages WHERE chat_key = ? AND id < ? ORDER BY id DESC LIMIT ?", (chat_key, before_id, limit)
        ) as cur:
            return [self._msg(r) for r in await cur.fetchall()]

    # ------------------------------------------------------------ friend requests / invites

    async def add_request(self, platform: str, kind: str, user_id: str, flag: str, *, user_name: str = "",
                          group_id: str | None = None, comment: str = "", sub_type: str = "") -> int:
        cur = await self.conn.execute(
            """INSERT INTO requests (platform, kind, user_id, user_name, group_id, comment, flag, sub_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (platform, kind, user_id, user_name, group_id, comment, flag, sub_type, time.time()),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def requests(self, status: str | None = "pending", limit: int = 100) -> list[dict[str, Any]]:
        query, args = "SELECT * FROM requests", ()
        if status:
            query, args = query + " WHERE status = ?", (status,)
        async with self.conn.execute(query + " ORDER BY id DESC LIMIT ?", (*args, limit)) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def request(self, request_id: int) -> dict[str, Any] | None:
        async with self.conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def decide_request(self, request_id: int, status: str, note: str = "") -> None:
        await self.conn.execute(
            "UPDATE requests SET status = ?, note = ?, decided_at = ? WHERE id = ?", (status, note, time.time(), request_id)
        )
        await self.conn.commit()

    # ------------------------------------------------------------ stickers

    async def add_sticker(self, file: str, sha: str, tags: str, description: str = "", source: str = "") -> int | None:
        try:
            cur = await self.conn.execute(
                "INSERT INTO stickers (file, sha, tags, description, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (file, sha, tags, description, source, time.time()),
            )
        except aiosqlite.IntegrityError:
            return None
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def stickers(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM stickers" + (" WHERE enabled = 1" if enabled_only else "") + " ORDER BY id DESC"
        async with self.conn.execute(query) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def update_sticker(self, sticker_id: int, **fields: Any) -> None:
        sets = {k: v for k, v in fields.items() if k in {"tags", "description", "enabled", "uses"}}
        if sets:
            cols = ", ".join(f"{k} = ?" for k in sets)
            await self.conn.execute(f"UPDATE stickers SET {cols} WHERE id = ?", (*sets.values(), sticker_id))
            await self.conn.commit()

    async def delete_sticker(self, sticker_id: int) -> dict[str, Any] | None:
        async with self.conn.execute("SELECT * FROM stickers WHERE id = ?", (sticker_id,)) as cur:
            row = await cur.fetchone()
        await self.conn.execute("DELETE FROM stickers WHERE id = ?", (sticker_id,))
        await self.conn.commit()
        return dict(row) if row else None

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
