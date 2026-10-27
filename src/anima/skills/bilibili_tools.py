"""Look at Bilibili videos people share, so she can react like someone who actually clicked."""

from __future__ import annotations

import re

import httpx

from anima.skills.base import SkillContext, skill

_BV = re.compile(r"(BV[0-9A-Za-z]{10})")
_AV = re.compile(r"\bav(\d+)", re.I)
_SHORT = re.compile(r"https?://(?:b23\.tv|bili2233\.cn)/[0-9A-Za-z]+")


async def resolve_video_id(text: str) -> tuple[str | None, int | None]:
    short = _SHORT.search(text)
    if short:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            resp = await client.get(short.group(0))
            text = resp.headers.get("location", text)
    if m := _BV.search(text):
        return m.group(1), None
    if m := _AV.search(text):
        return None, int(m.group(1))
    return None, None


@skill(
    "bilibili_video",
    "查看一个B站视频的信息（标题、UP主、简介、数据、AI总结）。别人分享了B站链接或BV号时用。",
    {"link": {"type": "string", "description": "BV号、av号、b23.tv 短链或完整链接"}},
    required=["link"],
)
async def bilibili_video(ctx: SkillContext, args: dict) -> dict:
    try:
        from bilibili_api import video
    except ImportError:
        return {"error": "这台电脑没装 B 站的库（bilibili-api-python），看不了视频信息"}

    bvid, aid = await resolve_video_id(args["link"])
    if not bvid and not aid:
        return {"error": "没认出视频号"}
    credential = getattr(ctx.brain, "bilibili_credential", None)
    v = video.Video(bvid=bvid, aid=aid, credential=credential)
    info = await v.get_info()
    stat = info.get("stat", {})
    result = {
        "title": info.get("title"),
        "up": info.get("owner", {}).get("name"),
        "category": info.get("tname"),
        "duration_sec": info.get("duration"),
        "desc": (info.get("desc") or "")[:300],
        "views": stat.get("view"),
        "likes": stat.get("like"),
        "coins": stat.get("coin"),
        "favorites": stat.get("favorite"),
        "danmaku": stat.get("danmaku"),
    }
    try:
        ai = await v.get_ai_conclusion(cid=info.get("cid"), up_mid=info.get("owner", {}).get("mid"))
        summary = (ai.get("model_result") or {}).get("summary")
        if summary:
            result["ai_summary"] = summary[:400]
    except Exception:
        pass
    return result
