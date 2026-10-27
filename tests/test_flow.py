"""Debounce, bubble splitting and group-chat judgement."""

import random
import time

from anima.config import BehaviorConfig, BotConfig, ChatOverride
from anima.core.debounce import settle_wait, unfinished
from anima.core.events import Bubble, Chat, Incoming, Segment, Sender
from anima.core.humanizer import Humanizer
from anima.core.policy import ChatStats, Policy, call_strength
from anima.core.schedule import LifeState
from anima.core.segment import split_text
from tests.conftest import wait_idle

AWAKE = LifeState("自由时间", "active", 0.85)
GROUP = Chat("playground", "group", "lab", "测试群")
DM = Chat("playground", "private", "you", "你")
FISH = Sender("pg-小鱼", "小鱼")
CAT = Sender("pg-阿猫", "阿猫")
DOG = Sender("pg-阿狗", "阿狗")
ALIASES = ["可乐", "claudette"]
FALSE_FRIENDS = BehaviorConfig().name_false_friends


def msg(text, sender=FISH, chat=GROUP, **kw):
    return Incoming(chat, sender, text, **kw)


# ---------------------------------------------------------------- splitting


def test_split_keeps_short_lines_and_cuts_long_ones_at_sentences():
    assert split_text("嗯嗯好的") == ["嗯嗯好的"]
    out = split_text("今天去看了流星雨！超级好看😭😭 你那边能看到吗？我们这边云有点多，不过后半夜散开了，一下子看到好几颗")
    assert out[0] == "今天去看了流星雨！"
    assert out[1].endswith("你那边能看到吗？"), "emoji stay with their sentence, a question ends its bubble"
    assert "".join(out).replace(" ", "") == "今天去看了流星雨！超级好看😭😭你那边能看到吗？我们这边云有点多，不过后半夜散开了，一下子看到好几颗"


def test_split_never_cuts_links_numbers_quotes_or_kaomoji():
    url = "https://www.bilibili.com/video/BV1xx411c7mD?p=2"
    out = split_text(f"你看这个 {url} 真的笑死我了！还有那个up主的上一期也很好笑，你一定要看")
    assert any(url in piece for piece in out)
    assert split_text("圆周率是3.14159，现在是12:30。我还没吃饭呢，等会儿去食堂看看有没有好吃的")[0] == "圆周率是3.14159，现在是12:30。"
    quoted = split_text("他说「我明天就去！你们等着吧。」然后就没有然后了……真的服了这个人(｡•́︿•̀｡)明天再问问他吧")
    assert quoted[0] == "他说「我明天就去！你们等着吧。」然后就没有然后了……"
    assert "(｡•́︿•̀｡)" in quoted[1]


def test_split_falls_back_to_commas_and_leaves_unbreakable_runs_whole():
    long = "我们这边云有点多，不过后半夜散开了，一下子看到好几颗，许了三个愿望，第一个是期末别挂科，第二个是猫猫健康，第三个保密"
    out = split_text(long, split=30, hard=40)
    assert len(out) > 1 and all(len(p) <= 40 for p in out)
    assert split_text("啊" * 90) == ["啊" * 90]


def test_shape_keeps_stickers_after_their_words_and_caps_bubbles():
    h = Humanizer(BehaviorConfig(), random.Random(1))
    text = "今天去看了流星雨！超级好看 你那边能看到吗？我们这边云有点多，不过后半夜散开了"
    out = h.shape([Bubble([Segment("text", text), Segment("sticker", "happy")], source=text)])
    assert len(out) == 3 and out[-1].segments[-1].type == "sticker"
    many = [Bubble([Segment("text", f"第{i}句")], source=f"第{i}句") for i in range(6)]
    capped = h.shape(many, max_bubbles=3)
    assert len(capped) == 3 and "第5句" in capped[-1].text


def test_long_replies_fit_the_typing_budget():
    h = Humanizer(BehaviorConfig(reply_budget=20), random.Random(3))
    bubbles = [Bubble([Segment("text", "这是一段很长很长的话" * 5)]) for _ in range(5)]
    plan = h.plan(bubbles)
    assert abs(sum(plan) - 20) < 0.01 and min(plan) >= 0.6
    short = h.plan([Bubble([Segment("text", "嗯")])])
    assert short[0] < 3


# ---------------------------------------------------------------- debounce


def test_debounce_waits_longer_for_unfinished_lines_and_less_for_questions():
    cfg = BehaviorConfig(debounce_private=2.5, debounce_unfinished=2.5)
    assert unfinished(msg("在吗", chat=DM)) and unfinished(msg("我跟你说，")) and unfinished(msg("", mentions_me=True))
    assert not unfinished(msg("今天吃什么？"))
    trailing = settle_wait([msg("然后呢，那个", chat=DM)], cfg, private=True)
    question = settle_wait([msg("你今天吃什么了？", chat=DM)], cfg, private=True)
    assert trailing == 5.0 and question < 2.5


def test_debounce_follows_the_senders_rhythm():
    cfg = BehaviorConfig(debounce_private=2.0)
    t = time.time()
    burst = [msg(text, chat=DM, timestamp=t + i * 4) for i, text in enumerate(["今天", "我去了", "动物园"])]
    assert settle_wait(burst, cfg, private=True) > 4.0


# ---------------------------------------------------------------- names and groups


def test_name_calls_versus_drinks():
    assert call_strength("可乐你怎么看", ALIASES, FALSE_FRIENDS) == 1.0
    assert call_strength("问问可乐", ALIASES, FALSE_FRIENDS) == 1.0
    assert call_strength("我觉得可乐说得对", ALIASES, FALSE_FRIENDS) == 0.5
    assert call_strength("今天喝了三瓶可乐", ALIASES, FALSE_FRIENDS) == 0
    assert call_strength("可乐鸡翅真好吃", ALIASES, FALSE_FRIENDS) == 0


def test_she_keeps_talking_with_her_partner_but_not_into_other_conversations():
    policy = Policy(BehaviorConfig(group_chattiness=0), ALIASES, random.Random(1))
    stats = ChatStats(seconds_since_self=20, partners={FISH.user_key("playground"): 20})
    replies = sum(policy.decide(GROUP, [msg("对啊我也这么觉得")], AWAKE, stats).act == "reply" for _ in range(50))
    assert replies > 30
    elsewhere = msg("@阿猫 你呢", meta={"at": ["阿猫"]})
    assert all(policy.decide(GROUP, [elsewhere], AWAKE, stats).act == "ignore" for _ in range(30))
    stranger = msg("哈哈哈", sender=CAT)
    assert all(policy.decide(GROUP, [stranger], AWAKE, stats).act == "ignore" for _ in range(30))


def test_hourly_cap_and_quiet_groups():
    policy = Policy(BehaviorConfig(group_chattiness=0.9, interjections_per_hour=2), ALIASES, random.Random(2))
    assert policy.decide(GROUP, [msg("随便聊聊")], AWAKE, ChatStats(interjections_hour=2)).act == "ignore"
    cfg = BotConfig(chats={GROUP.key: ChatOverride(mode="quiet")}).behavior_for(GROUP.key)
    assert cfg.group_chattiness == 0 and cfg.repeat_chance == 0
    assert all(policy.decide(GROUP, [msg("今晚有流星雨吗")], AWAKE, ChatStats(), cfg).act == "ignore" for _ in range(30))
    assert policy.decide(GROUP, [msg("可乐你在吗")], AWAKE, ChatStats(), cfg).act == "reply"


def test_target_is_whoever_spoke_to_her():
    policy = Policy(BehaviorConfig(), ALIASES)
    batch = [msg("@可乐 你看过星际穿越吗", mentions_me=True), msg("今天好热", sender=CAT), msg("是啊", sender=DOG)]
    assert policy.target(batch).sender == FISH


# ---------------------------------------------------------------- the whole brain


async def test_group_burst_from_others_does_not_delay_her_answer(make_brain, bot):
    bot.config.behavior.group_chattiness = 0
    brain, rec = make_brain(lambda *a: "看过！超喜欢")
    await brain.handle(msg("@可乐 你看过星际穿越吗", mentions_me=True, message_id="1"))
    session = brain.session(GROUP)
    timer = session.timer
    await brain.handle(msg("今天好热", sender=CAT, message_id="2"))
    assert session.timer is timer, "someone else's chatter doesn't reset her wait"
    await brain.handle(msg("是啊", sender=DOG, message_id="3"))
    await wait_idle(brain)
    assert [s[1] for s in rec.sent] == ["看过！超喜欢"]
    assert rec.sent[0][2] == "1", "the group moved on, so she quotes the question she answers"
    assert "这次主要回应 小鱼" in brain.llm.calls[-1]["dynamic"]


async def test_she_rethinks_when_they_add_something_while_she_types(make_brain):
    calls = []

    def responder(system, turns, dynamic):
        calls.append(turns[-1].text)
        if len(calls) == 1:
            brain.session(DM).buffer.append(Incoming(DM, Sender("pg-你", "你"), "算了不吃了", message_id="b"))
            return "吃火锅吧"
        return "啊？那你饿着吗"

    brain, rec = make_brain(responder)
    await brain.handle(Incoming(DM, Sender("pg-你", "你"), "晚上吃什么", message_id="a"))
    await wait_idle(brain)
    assert [s[1] for s in rec.sent] == ["啊？那你饿着吗"], "the first draft is dropped"
    assert len(calls) == 2


async def test_she_stops_mid_reply_and_picks_it_up_next_turn(make_brain, bot):
    bot.config.behavior.typing_cps = 6
    brain, rec = make_brain(lambda *a: "第一句\n第二句\n第三句")
    sent_before = rec.send

    async def send(chat, bubble, quote=None):
        msg_id = await sent_before(chat, bubble, quote)
        if len(rec.sent) == 1 and len(brain.llm.calls) == 1:
            await brain.handle(Incoming(DM, Sender("pg-你", "你"), "等等", message_id="z"))
        return msg_id

    rec.send = send
    await brain.handle(Incoming(DM, Sender("pg-你", "你"), "讲个故事", message_id="y"))
    await wait_idle(brain)
    assert [s[1] for s in rec.sent][:2] == ["第一句", "第一句"], "she stopped after one bubble and answered again"
    assert "第二句 / 第三句" in brain.llm.calls[-1]["dynamic"]


async def test_she_joins_a_repeat_chain_without_calling_the_model(make_brain, bot):
    bot.config.behavior.repeat_chance = 1.0
    bot.config.behavior.group_chattiness = 0
    brain, rec = make_brain(lambda *a: "不该被调用")
    for i, sender in enumerate([FISH, CAT, DOG]):
        await brain.handle(msg("下雪啦", sender=sender, message_id=f"r{i}"))
        await wait_idle(brain)
    assert [s[1] for s in rec.sent] == ["下雪啦"]
    assert brain.llm.calls == []


async def test_recalled_messages_are_forgotten_before_she_answers(make_brain):
    brain, rec = make_brain(lambda *a: "好")
    await brain.handle(Incoming(DM, Sender("pg-你", "你"), "我的密码是 abc123", message_id="x1"))
    await brain.retract(DM, "x1")
    await wait_idle(brain)
    assert rec.sent == [] and brain.llm.calls == []
    history = await brain.memory.recent(DM.key)
    assert history[0].text == "（撤回了一条消息）"


async def test_chat_note_reaches_the_scene(make_brain, bot):
    bot.config.chats = {GROUP.key: ChatOverride(note="天文社的群，大家叫她乐乐")}
    brain, rec = make_brain(lambda *a: "在！")
    await brain.handle(msg("@可乐", mentions_me=True, message_id="n1"))
    await wait_idle(brain)
    assert "天文社的群" in brain.llm.calls[-1]["dynamic"]
