"""Reflection: after a stretch of conversation, she quietly works out what's worth remembering.

Runs on the side model in the background, reads the new part of a chat, and updates facts,
affinity, nicknames, birthdays, and her treasure box of beautiful sentences.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from anima.core.events import Chat
from anima.llm.base import LLMError

if TYPE_CHECKING:
    from anima.core.brain import Brain

REFLECT_SYSTEM = """\
你在帮一个叫「{name}」的虚拟角色整理记忆。下面是她参与的一段聊天记录，每行开头的方括号里是发言人的 ID，[self] 是她自己。
请提取值得长期记住的信息：
- facts：关于具体某个人的持久信息（身份、近况、计划、喜好、经历、重要的人/宠物），不要记录一次性的闲聊内容。user_id 必须是记录里出现过的 ID。
- self_facts：她自己在聊天里新说出的、关于她自己的设定（比如喜欢的电影、做过的梦），用于以后保持一致。
- affinity：这段对话让她对某人的好感变化，-0.15 到 0.15，大多数情况是 0 或很小的正数；被骂、被骚扰才是负数。
- nicknames：明确约定好的、她以后对某人的称呼。
- birthdays：明确提到的生日，MM-DD。
- treasures：别人说的特别美、特别好笑或特别戳人的一句话，原文摘录。没有就留空。
宁缺毋滥，没有就给空数组。"""

REFLECT_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "fact": {"type": "string"},
                    "importance": {"type": "integer"},
                },
                "required": ["user_id", "fact", "importance"],
                "additionalProperties": False,
            },
        },
        "self_facts": {"type": "array", "items": {"type": "string"}},
        "affinity": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}, "delta": {"type": "number"}},
                "required": ["user_id", "delta"],
                "additionalProperties": False,
            },
        },
        "nicknames": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}, "nickname": {"type": "string"}},
                "required": ["user_id", "nickname"],
                "additionalProperties": False,
            },
        },
        "birthdays": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}, "date": {"type": "string"}},
                "required": ["user_id", "date"],
                "additionalProperties": False,
            },
        },
        "treasures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["user_id", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["facts", "self_facts", "affinity", "nicknames", "birthdays", "treasures"],
    "additionalProperties": False,
}


async def reflect(brain: Brain, chat: Chat) -> dict | None:
    meta = await brain.memory.chat(chat.key)
    upto = meta["reflected_upto"] if meta else 0
    messages = await brain.memory.messages_after(chat.key, upto, limit=150)
    if len(messages) < 4:
        return None
    names = {m.sender_key: m.sender_name for m in messages if not m.is_self}
    transcript = "\n".join(
        f"[{'self' if m.is_self else m.sender_key}] {brain.cfg.identity.display_name if m.is_self else m.sender_name}: {m.text}"
        for m in messages
    )
    system = REFLECT_SYSTEM.format(name=brain.cfg.identity.display_name)
    try:
        result = await brain.llm.complete(system, transcript, schema=REFLECT_SCHEMA)
        data = json.loads(result.text)
    except (LLMError, json.JSONDecodeError) as exc:
        logger.warning("Reflection on {} failed: {}", chat.key, exc)
        return None
    brain.account(result)

    saved = 0
    for item in data.get("facts", []):
        if item.get("user_id") in names and await brain.memory.add_fact(
            item["user_id"], item.get("fact", ""), int(item.get("importance", 3)), source=f"reflect:{chat.key}"
        ):
            saved += 1
    for fact in data.get("self_facts", []):
        if await brain.memory.add_fact("self", fact, 3, source=f"reflect:{chat.key}"):
            saved += 1
    for item in data.get("affinity", []):
        if item.get("user_id") in names:
            await brain.memory.adjust_affinity(item["user_id"], max(-0.15, min(0.15, float(item.get("delta", 0)))))
    for item in data.get("nicknames", []):
        if item.get("user_id") in names and item.get("nickname"):
            await brain.memory.update_user(item["user_id"], nickname=item["nickname"][:20])
    for item in data.get("birthdays", []):
        if item.get("user_id") in names and len(item.get("date", "")) == 5:
            await brain.memory.update_user(item["user_id"], birthday=item["date"])
    for item in data.get("treasures", []):
        if item.get("text"):
            await brain.memory.add_treasure(item["text"], item.get("user_id", ""), names.get(item.get("user_id", ""), ""))

    await brain.memory.set_reflected(chat.key, messages[-1].id)
    brain.trace.emit("reflect", chat=chat.key, messages=len(messages), saved=saved)
    return data
