"""倒数日: dates people care about, remembered per chat. She knows how many days are left."""

import json
from datetime import date

from anima.plugin import Plugin

plugin = Plugin()


def load(ctx) -> dict:
    path = ctx.data_dir / "days.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(ctx, data: dict) -> None:
    (ctx.data_dir / "days.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def left(day: str, today: date) -> int:
    return (date.fromisoformat(day) - today).days


@plugin.skill("countdown_add", "记下一个重要日子（考试、生日、旅行出发日），之后能算还剩几天。",
              {"title": {"type": "string", "description": "这一天是什么，比如 期末考试"},
               "date": {"type": "string", "description": "日期，YYYY-MM-DD"}}, required=["title", "date"])
async def add(ctx, args):
    data = load(ctx)
    chat = ctx_chat_key(ctx)
    date.fromisoformat(args["date"])  # refuse nonsense early
    data.setdefault(chat, {})[args["title"]] = args["date"]
    save(ctx, data)
    return {"ok": True, "days_left": left(args["date"], ctx.clock.now().date())}


def ctx_chat_key(ctx) -> str:
    chat = getattr(ctx, "chat", None)
    return chat.key if chat else "global"


@plugin.command("倒数日", help="看看这里记着的日子")
async def show(ctx, ev, arg):
    today = ctx.clock.now().date()
    days = load(ctx).get(ev.chat.key, {})
    lines = [f"{title}：还有 {left(d, today)} 天（{d}）" for title, d in sorted(days.items(), key=lambda x: x[1])
             if left(d, today) >= 0]
    return "\n".join(lines) or "这里还没有记着的日子，跟她说「帮我记一下 6 月 7 日高考」就行"


@plugin.on_scene
async def remind(ctx, chat, batch):
    today = ctx.clock.now().date()
    days = load(ctx).get(chat.key, {})
    soon = [f"{title}还有 {left(d, today)} 天" if left(d, today) else f"今天就是{title}"
            for title, d in days.items() if 0 <= left(d, today) <= 7]
    return f"这个聊天里记着的日子：{'；'.join(soon)}。合适的时候可以自然地提一句。" if soon else None
