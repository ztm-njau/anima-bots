"""一言: a line from anime, books or poetry, via the public hitokoto.cn API."""

import httpx

from anima.plugin import Plugin

plugin = Plugin()
API = "https://v1.hitokoto.cn/"


async def fetch(categories: str) -> dict:
    params = [("c", c.strip()) for c in categories.split(",") if c.strip()]
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(API, params=params)
        resp.raise_for_status()
        return resp.json()


def line(data: dict) -> str:
    source = data.get("from_who") or data.get("from") or ""
    return f"「{data.get('hitokoto', '')}」" + (f" —— {source}" if source else "")


@plugin.skill("hitokoto", "随机来一句动画、文学、诗词里的好句子。想引用一句话、或者对方要一句话时用。")
async def hitokoto(ctx, args):
    return line(await fetch(ctx.config.get("categories", "")))


@plugin.command("一言", help="来一句", aliases=["hitokoto"])
async def command(ctx, ev, arg):
    return line(await fetch(ctx.config.get("categories", "")))
