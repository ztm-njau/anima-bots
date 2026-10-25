"""Remembering people: facts, nicknames, birthdays, and her collection of beautiful sentences."""

from __future__ import annotations

import re

from anima.skills.base import SkillContext, skill


@skill(
    "remember",
    "把一件值得记住的事存进长期记忆。朋友提到自己的近况、喜好、经历、计划、重要的人或事时用；"
    "你自己聊天中提到的关于你自己的新设定（喜欢的电影、做过的梦等）也记下来，保持前后一致。不用告诉对方你在记。",
    {
        "fact": {"type": "string", "description": "一句话写清楚，比如：在准备明年三月的考研复试"},
        "about": {
            "type": "string",
            "enum": ["speaker", "self", "chat"],
            "description": "speaker=当前说话的人, self=你自己, chat=这个群/这个聊天本身",
        },
        "importance": {"type": "integer", "minimum": 1, "maximum": 5, "description": "1 琐碎 ~ 5 非常重要"},
    },
    required=["fact"],
)
async def remember(ctx: SkillContext, args: dict) -> dict:
    about = args.get("about", "speaker")
    subject = {"speaker": ctx.user_key, "self": "self", "chat": ctx.chat.key}.get(about, ctx.user_key)
    new = await ctx.memory.add_fact(subject, args["fact"], int(args.get("importance", 3)), source=ctx.chat.key)
    return {"saved": new, "note": "已经记得" if not new else "记下了"}


@skill(
    "recall",
    "在记忆里翻找：关于某个人的事、以前聊过的话题。对方问“你还记得……吗”或你想不起来时用。",
    {
        "keywords": {"type": "array", "items": {"type": "string"}, "description": "2~4 个关键词"},
        "scope": {"type": "string", "enum": ["speaker", "everyone", "this_chat"]},
    },
    required=["keywords"],
)
async def recall(ctx: SkillContext, args: dict) -> dict:
    keywords = [k for k in args.get("keywords", []) if k][:6]
    scope = args.get("scope", "speaker")
    subjects = [ctx.user_key, "self"] if scope == "speaker" else None
    facts = await ctx.memory.search_facts(keywords, subjects=subjects, limit=8)
    chat_key = ctx.chat.key if scope in ("speaker", "this_chat") else None
    messages = await ctx.memory.search_messages(keywords, chat_key=chat_key, limit=8)
    return {
        "facts": [f.content for f in facts],
        "messages": [
            f"{ctx.clock.to_local(m.ts):%m-%d %H:%M} {'你' if m.is_self else m.sender_name}: {m.text[:80]}"
            for m in messages
        ],
    }


@skill(
    "call_me",
    "约定以后怎么称呼当前说话的人（对方要求的昵称，或你们自然形成的外号）。",
    {"nickname": {"type": "string"}},
    required=["nickname"],
)
async def call_me(ctx: SkillContext, args: dict) -> dict:
    nickname = args["nickname"].strip()[:20]
    await ctx.memory.update_user(ctx.user_key, nickname=nickname)
    return {"ok": True, "nickname": nickname}


@skill(
    "set_birthday",
    "记下当前说话人的生日，到那天你会记得祝福。",
    {"date": {"type": "string", "description": "MM-DD，比如 03-14"}},
    required=["date"],
)
async def set_birthday(ctx: SkillContext, args: dict) -> dict:
    match = re.search(r"(\d{1,2})\D+(\d{1,2})", args["date"])
    if not match:
        return {"ok": False, "error": "日期格式应为 MM-DD"}
    mmdd = f"{int(match.group(1)):02d}-{int(match.group(2)):02d}"
    await ctx.memory.update_user(ctx.user_key, birthday=mmdd)
    return {"ok": True, "birthday": mmdd}


@skill(
    "treasure",
    "把别人说的一句特别美、特别好笑或特别戳你的话，收进你的“美好句子收藏夹”。",
    {"text": {"type": "string"}},
    required=["text"],
)
async def treasure(ctx: SkillContext, args: dict) -> dict:
    name = ctx.sender.name if ctx.sender else ""
    added = await ctx.memory.add_treasure(args["text"].strip(), ctx.user_key, name)
    return {"ok": True, "new": added}
