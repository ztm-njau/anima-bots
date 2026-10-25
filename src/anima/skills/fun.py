"""Small rituals people love: daily fortune, tarot, dice, choosing for the indecisive."""

from __future__ import annotations

import hashlib
import random
import re

from anima.skills.base import SkillContext, skill

LEVELS = [("大吉", 10), ("中吉", 22), ("小吉", 28), ("吉", 22), ("末吉", 12), ("小凶", 6)]
GOOD = [
    "早睡", "喝热水", "整理桌面", "给老朋友发消息", "出门晒太阳", "吃顿好的", "听新歌", "看星星",
    "摸鱼十分钟", "学一个冷知识", "夸夸自己", "认真吃早饭", "散步", "拍天空", "表白（谨慎）",
]
BAD = [
    "熬夜", "冲动消费", "和人抬杠", "立flag", "空腹喝咖啡", "翻旧账", "点外卖超过两份",
    "看恐怖片", "通宵打游戏", "说“我再睡五分钟”", "相信“这次肯定不堵车”",
]
COLORS = ["可乐红", "星空蓝", "薄荷绿", "奶油白", "落日橙", "樱花粉", "雾霾紫", "柠檬黄"]

MAJOR_ARCANA = [
    ("愚者", "新的开始、冒险、天真", "鲁莽、犹豫不决"),
    ("魔术师", "创造力、行动、资源齐备", "空想、手段不正"),
    ("女祭司", "直觉、秘密、静观", "忽视内心、表面化"),
    ("皇后", "丰盛、温柔、滋养", "依赖、过度付出"),
    ("皇帝", "秩序、掌控、责任", "专制、僵化"),
    ("教皇", "传统、指引、学习", "叛逆、墨守成规"),
    ("恋人", "选择、契合、心动", "犹豫、失衡"),
    ("战车", "意志、胜利、前进", "失控、方向不明"),
    ("力量", "勇气、温柔的坚持", "自我怀疑、急躁"),
    ("隐士", "独处、反思、寻找答案", "孤立、逃避"),
    ("命运之轮", "转机、循环、好运将至", "低谷、时机未到"),
    ("正义", "公平、因果、清醒", "偏颇、逃避责任"),
    ("倒吊人", "换个角度、暂停、放下", "无谓的牺牲、拖延"),
    ("死神", "结束与新生、告别", "抗拒改变"),
    ("节制", "平衡、调和、耐心", "失衡、过度"),
    ("恶魔", "欲望、束缚、诱惑", "挣脱、觉醒"),
    ("高塔", "突变、打破、真相", "躲过一劫、内在动荡"),
    ("星星", "希望、治愈、灵感", "失望、信心不足"),
    ("月亮", "迷惘、潜意识、不安", "迷雾散去"),
    ("太阳", "快乐、成功、活力", "短暂的阴霾"),
    ("审判", "觉醒、召唤、重来", "自责、拒绝面对"),
    ("世界", "圆满、完成、旅程结束", "差一点点、未完成"),
]
LOTS = [
    ("上上签", "星河落在你窗前，想做的事尽管去做"),
    ("上签", "风是顺的，走慢一点也会到"),
    ("上签", "有人在悄悄惦记你，记得回一下消息"),
    ("中签", "云会散的，先把饭吃好"),
    ("中签", "答案在第二次尝试里"),
    ("下签", "今天适合躺平，明天再战（这签可以重抽）"),
]


def _seeded(*parts: str) -> random.Random:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return random.Random(int(digest[:12], 16))


@skill(
    "fortune",
    "给当前说话的人算今日运势。同一个人同一天结果固定（问两次也一样，这才像真的）。",
)
async def fortune(ctx: SkillContext, args: dict) -> dict:
    rng = _seeded("fortune", ctx.user_key, ctx.clock.today())
    level = rng.choices([lv for lv, _ in LEVELS], weights=[w for _, w in LEVELS])[0]
    return {
        "date": ctx.clock.today(),
        "level": level,
        "lucky_color": rng.choice(COLORS),
        "lucky_number": rng.randint(0, 99),
        "good_for": rng.sample(GOOD, 2),
        "avoid": rng.sample(BAD, 2),
        "tip": "用你自己的话、带点个人风格地解读，别照念",
    }


@skill(
    "tarot",
    "抽塔罗牌（大阿卡纳）。count=1 单张指引；count=3 过去/现在/未来。",
    {
        "count": {"type": "integer", "enum": [1, 3]},
        "question": {"type": "string", "description": "对方想问的事（可选）"},
    },
)
async def tarot(ctx: SkillContext, args: dict) -> dict:
    count = 3 if args.get("count") == 3 else 1
    rng = random.Random()
    cards = rng.sample(MAJOR_ARCANA, count)
    positions = ["过去", "现在", "未来"] if count == 3 else ["指引"]
    drawn = []
    for pos, (name, upright, reversed_) in zip(positions, cards, strict=True):
        is_rev = rng.random() < 0.3
        drawn.append({"position": pos, "card": name, "orientation": "逆位" if is_rev else "正位",
                      "meaning": reversed_ if is_rev else upright})
    return {"question": args.get("question", ""), "cards": drawn,
            "tip": "像朋友一样解读，温柔一点，别搞得太玄乎"}


@skill(
    "dice",
    "掷骰子，支持 NdM+K 写法，比如 1d6、2d20、1d100+5。",
    {"expr": {"type": "string"}},
    required=["expr"],
)
async def dice(ctx: SkillContext, args: dict) -> dict:
    match = re.fullmatch(r"\s*(\d{0,2})d(\d{1,4})\s*([+-]\s*\d{1,4})?\s*", args.get("expr", "1d6").lower())
    if not match:
        return {"error": "看不懂这个骰子写法，用 1d6 这种格式"}
    n, sides = int(match.group(1) or 1), int(match.group(2))
    mod = int(match.group(3).replace(" ", "")) if match.group(3) else 0
    n, sides = max(1, min(n, 20)), max(2, sides)
    rolls = [random.randint(1, sides) for _ in range(n)]
    return {"rolls": rolls, "modifier": mod, "total": sum(rolls) + mod}


@skill(
    "choose",
    "帮选择困难的人做决定：从选项里随机挑一个。",
    {"options": {"type": "array", "items": {"type": "string"}, "minItems": 2}},
    required=["options"],
)
async def choose(ctx: SkillContext, args: dict) -> dict:
    options = [o for o in args.get("options", []) if o.strip()]
    if len(options) < 2:
        return {"error": "至少要两个选项"}
    return {"picked": random.choice(options), "from": options}


@skill("draw_lot", "抽一支“可乐签”，带一句签文。")
async def draw_lot(ctx: SkillContext, args: dict) -> dict:
    level, verse = random.choice(LOTS)
    return {"lot": level, "verse": verse}
