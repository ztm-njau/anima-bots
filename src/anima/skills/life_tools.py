"""Her own life: today's little plan, her diary, her treasure box. Keeps her stories consistent."""

from __future__ import annotations

from anima.skills.base import SkillContext, skill


@skill("my_day", "回顾你自己今天的安排和最近的日记，聊到“你今天干嘛了”之类的话题时用。")
async def my_day(ctx: SkillContext, args: dict) -> dict:
    plan = await ctx.memory.journal_get(ctx.clock.today(), "plan")
    diaries = await ctx.memory.journal_list("diary", limit=2)
    return {"today_plan": plan, "recent_diary": diaries}


@skill("my_treasures", "翻看你的“美好句子收藏夹”，想分享或别人问起时用。")
async def my_treasures(ctx: SkillContext, args: dict) -> dict:
    items = await ctx.memory.treasures(limit=10)
    return {"sentences": [f"{i['text']}（{i['user_name'] or '某位网友'}）" for i in items]}
