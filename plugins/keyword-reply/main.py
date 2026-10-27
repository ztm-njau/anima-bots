"""Fixed answers for keywords: rules, links, passwords. No model call, so it costs nothing."""

from anima.plugin import Plugin

plugin = Plugin()


def rules(ctx) -> list[tuple[str, str]]:
    out = []
    for raw in str(ctx.config.get("rules", "")).splitlines():
        key, sep, answer = raw.partition("=>")
        if sep and key.strip() and answer.strip():
            out.append((key.strip(), answer.strip()))
    return out


@plugin.on_message
async def reply_to_keywords(ctx, ev):
    text = ev.text.strip()
    for key, answer in rules(ctx):
        if (text == key) if ctx.config.get("exact") else (key in text):
            await ctx.send(ev.chat, answer)
            return False  # answered; she doesn't need to see it
    return None


@plugin.command("关键词", help="看看设置了哪些关键词", owner_only=True)
async def list_rules(ctx, ev, arg):
    return "\n".join(f"{k} → {v}" for k, v in rules(ctx)) or "还没有设置关键词"
