"""Reminders: "可乐，明早八点叫我起床" actually works."""

from __future__ import annotations

from datetime import datetime

from anima.skills.base import SkillContext, skill


@skill(
    "set_reminder",
    "帮当前说话的人设一个提醒，到时间你会在这个聊天里提醒他。根据背景信息里的当前时间换算成具体时刻。",
    {
        "when": {"type": "string", "description": "本地时间 ISO 格式，比如 2026-10-26T08:00"},
        "text": {"type": "string", "description": "要提醒的事"},
    },
    required=["when", "text"],
)
async def set_reminder(ctx: SkillContext, args: dict) -> dict:
    try:
        due = datetime.fromisoformat(args["when"].strip())
    except ValueError:
        return {"error": "时间格式不对，要 ISO 格式，比如 2026-10-26T08:00"}
    if due.tzinfo is None:
        due = due.replace(tzinfo=ctx.clock.tz)
    if due.timestamp() < ctx.clock.timestamp() - 60:
        return {"error": "这个时间已经过去了"}
    name = ctx.sender.name if ctx.sender else ""
    rid = await ctx.memory.add_reminder(ctx.chat.key, due.timestamp(), args["text"], ctx.user_key, name)
    return {"ok": True, "id": rid, "due": ctx.clock.describe(due.astimezone(ctx.clock.tz))}
