"""Her boundaries: she can walk away from a conversation, the way a person would."""

from __future__ import annotations

from anima.skills.base import SkillContext, skill


@skill(
    "end_chat",
    "暂时不理当前说话的人：对方骚扰、辱骂、反复逼你越界，或者你真的被惹烦了时用。"
    "用了之后在这次回复里说一句离开的话（比如「我先不跟你聊了」）。时间到了会自动恢复。",
    {
        "minutes": {"type": "integer", "minimum": 5, "maximum": 1440, "description": "多久不理，默认 60"},
        "reason": {"type": "string", "description": "为什么（只记在你心里）"},
    },
)
async def end_chat(ctx: SkillContext, args: dict) -> dict:
    minutes = max(5, min(1440, int(args.get("minutes") or 60)))
    until = ctx.clock.timestamp() + minutes * 60
    await ctx.memory.update_user(ctx.user_key, silenced_until=until)
    await ctx.memory.adjust_affinity(ctx.user_key, -0.1)
    ctx.brain.trace.emit("end_chat", user=ctx.sender.name if ctx.sender else "", minutes=minutes,
                         reason=args.get("reason", ""))
    return {"ok": True, "silent_minutes": minutes}
