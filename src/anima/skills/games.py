"""Chat games with hidden state the players can't see: guess the number, turtle soup, idiom chain.

The state lives in memory under ``game:<chat key>``. While a game runs, the brain puts the
state (including secrets, like the soup's answer) into her private context every turn.
"""

from __future__ import annotations

import random
import re

from anima.skills.base import SkillContext, skill

# Original lateral-thinking puzzles (海龟汤). "surface" is told to players; "answer" stays hidden.
SOUPS = [
    {
        "title": "电梯",
        "surface": "一个男人走进电梯，把每一层的按钮都按了一遍，然后满意地笑了。",
        "answer": "他是电梯检修员，正在做逐层停靠测试。每一层都准确停靠、开门，测试全部通过，所以他很满意。",
    },
    {
        "title": "一碗面",
        "surface": "一个人在小店点了一碗面，只吃了一口就哭了，结账时付了十倍的钱。",
        "answer": "面的味道和他去世的奶奶做的一模一样。一问才知道，店主小时候是被他奶奶收留过的孩子，手艺就是跟奶奶学的。他哭是因为想奶奶，多付钱是感谢。",
    },
    {
        "title": "不回复的号码",
        "surface": "她每天都给一个从不回复的号码发消息。终于有一天收到了回复，她却把这个号码删掉了。",
        "answer": "那是她已故父亲的旧号码，她一直把发消息当作写日记。后来号码被运营商回收给了新用户，对方回了一句“你是谁？”。她意识到是时候放下了。",
    },
    {
        "title": "灯塔",
        "surface": "一个女孩每天晚上都会对着窗外的黑暗说“晚安”。有一天她没有说，第二天整个村子的人都来敲她的门。",
        "answer": "她是灯塔看守人，每晚开灯前都会对着大海说晚安，这是她的习惯。那天她发高烧没能开灯，出海的渔民发现灯塔没亮，担心她出事，第二天都来看她。",
    },
    {
        "title": "冰箱",
        "surface": "小李每天早上都会对着冰箱说“早安”。今天冰箱第一次回答了他，他却非常失望。",
        "answer": "他以为家里的冰箱没有语音功能，说早安只是习惯。他妈妈偷偷给冰箱升级了智能系统，冰箱开口说的第一句是：“检测到您的酸奶已过期三天。”他本来正想吃那盒酸奶。",
    },
    {
        "title": "空白借书卡",
        "surface": "图书馆有一本旧诗集每周都会消失三天再出现，可借阅记录上一片空白。",
        "answer": "退休的老馆长还留着钥匙，每周悄悄把诗集带回家，读给卧病在床的老伴听，读完再放回去。那本诗集是他们年轻时一起在这个图书馆读过的。",
    },
]

CHENGYU_START = ["一帆风顺", "画蛇添足", "天马行空", "心花怒放", "守株待兔", "鸡飞狗跳", "春暖花开"]


def _key(ctx: SkillContext) -> str:
    return f"game:{ctx.chat.key}"


@skill(
    "game",
    "主持聊天小游戏。game: guess_number(猜1-100的数字) / turtle_soup(海龟汤，你知道汤底，对方提问你只答"
    "是/不是/无关/很接近) / idiom_chain(成语接龙)。action: start 开始, move 提交一步(猜的数字或接的成语，"
    "by=player/self), reveal 公布答案, stop 结束, status 查看。游戏进行中你的背景信息里会有它的状态。",
    {
        "action": {"type": "string", "enum": ["start", "move", "reveal", "stop", "status"]},
        "game": {"type": "string", "enum": ["guess_number", "turtle_soup", "idiom_chain"]},
        "move": {"type": "string", "description": "猜的数字，或者接的成语"},
        "by": {"type": "string", "enum": ["player", "self"]},
    },
    required=["action"],
)
async def game(ctx: SkillContext, args: dict) -> dict:
    action = args.get("action")
    state = await ctx.memory.get_state(_key(ctx))

    if action == "start":
        name = args.get("game") or "guess_number"
        if name == "guess_number":
            state = {"game": name, "secret": random.randint(1, 100), "tries": 0, "low": 1, "high": 100}
            public = {"rules": "我想好了一个 1~100 的数字，猜吧"}
        elif name == "turtle_soup":
            played = (state or {}).get("played", []) if state and state.get("game") == "turtle_soup" else []
            pool = [s for s in SOUPS if s["title"] not in played] or SOUPS
            soup = random.choice(pool)
            state = {"game": name, "title": soup["title"], "surface": soup["surface"], "answer": soup["answer"],
                     "questions": 0, "played": played + [soup["title"]]}
            public = {"surface": soup["surface"], "rules": "只能问能用是/不是回答的问题"}
        else:
            first = random.choice(CHENGYU_START)
            state = {"game": "idiom_chain", "used": [first], "last": first, "turn": "player"}
            public = {"first": first, "rules": f"接“{first[-1]}”字开头的成语，同音字也算"}
        await ctx.memory.set_state(_key(ctx), state)
        return {"started": name, **public}

    if not state:
        return {"error": "现在没有在玩游戏"}

    if action in ("stop", "reveal"):
        await ctx.memory.set_state(_key(ctx), None)
        reveal = {"guess_number": "secret", "turtle_soup": "answer"}.get(state["game"])
        return {"ended": state["game"], "answer": state.get(reveal) if reveal else state.get("used")}

    if action == "status":
        return state

    move = (args.get("move") or "").strip()
    if state["game"] == "guess_number":
        match = re.search(r"\d+", move)
        if not match:
            return {"error": "要猜一个数字"}
        guess = int(match.group())
        state["tries"] += 1
        if guess == state["secret"]:
            await ctx.memory.set_state(_key(ctx), None)
            return {"result": "猜中了", "tries": state["tries"], "secret": state["secret"]}
        if guess < state["secret"]:
            state["low"] = max(state["low"], guess + 1)
            verdict = "小了"
        else:
            state["high"] = min(state["high"], guess - 1)
            verdict = "大了"
        await ctx.memory.set_state(_key(ctx), state)
        return {"result": verdict, "tries": state["tries"], "range": [state["low"], state["high"]]}

    if state["game"] == "turtle_soup":
        state["questions"] += 1
        await ctx.memory.set_state(_key(ctx), state)
        return {"questions": state["questions"], "answer_for_you_only": state["answer"]}

    # idiom chain: enforce the mechanical rules, let her judge whether it's a real idiom
    idiom = re.sub(r"[^一-鿿]", "", move)
    if len(idiom) < 4:
        return {"valid": False, "reason": "成语一般是四个字哦"}
    if idiom in state["used"]:
        return {"valid": False, "reason": "这个用过了"}
    last_char = state["last"][-1]
    linked = idiom[0] == last_char
    state["used"].append(idiom)
    state["last"] = idiom
    state["turn"] = "self" if args.get("by", "player") == "player" else "player"
    await ctx.memory.set_state(_key(ctx), state)
    return {
        "accepted": idiom,
        "same_char_link": linked,
        "note": "首字不是同一个字，判断一下是不是同音字，是就算对" if not linked else "接上了",
        "next_char": idiom[-1],
        "count": len(state["used"]),
    }
