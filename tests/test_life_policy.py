import random
from datetime import datetime
from zoneinfo import ZoneInfo

from anima.config import BehaviorConfig
from anima.core.clock import Clock
from anima.core.events import Chat, Incoming, Sender
from anima.core.mood import MoodEngine
from anima.core.policy import ChatStats, Policy
from anima.core.schedule import LifeState, Schedule

TZ = ZoneInfo("Asia/Shanghai")
AWAKE = LifeState("自由时间", "active", 0.85)
ASLEEP = LifeState("睡觉", "asleep", 0.1)
GROUP = Chat("qq", "group", "1")
DM = Chat("qq", "private", "9")


def ev(chat, text, **kw):
    return Incoming(chat, Sender("9", "小明"), text, **kw)


def test_schedule_weekday_weekend_and_nights(bot):
    sched = Schedule(bot.read_toml("life.toml"), Clock(), insomnia_chance=0)
    monday_3am = datetime(2026, 10, 26, 3, 0, tzinfo=TZ)
    monday_9pm = datetime(2026, 10, 26, 21, 0, tzinfo=TZ)
    saturday_00_50 = datetime(2026, 10, 31, 0, 50, tzinfo=TZ)  # Friday night: weekend rules, still up
    saturday_9am = datetime(2026, 10, 31, 9, 0, tzinfo=TZ)  # sleeping in
    assert sched.state(monday_3am).asleep
    assert sched.state(monday_9pm).availability == "active"
    assert not sched.state(saturday_00_50).asleep
    assert sched.state(saturday_9am).asleep
    assert sched.next_wake(monday_3am).strftime("%H:%M") == "08:30"


def test_private_messages_are_answered_or_deferred_overnight():
    policy = Policy(BehaviorConfig(), ["可乐"], random.Random(1))
    assert policy.decide(DM, [ev(DM, "在吗")], AWAKE, ChatStats()).act == "reply"
    assert policy.decide(DM, [ev(DM, "在吗")], ASLEEP, ChatStats()).act == "defer"


def test_group_mentions_always_get_through():
    policy = Policy(BehaviorConfig(group_chattiness=0), ["可乐"], random.Random(1))
    assert policy.decide(GROUP, [ev(GROUP, "可乐你怎么看")], AWAKE, ChatStats()).act == "reply"
    assert policy.decide(GROUP, [ev(GROUP, "hi", mentions_me=True)], AWAKE, ChatStats()).act == "reply"
    assert policy.decide(GROUP, [ev(GROUP, "随便聊聊")], AWAKE, ChatStats()).act == "ignore"


def test_group_chattiness_respects_interest_cooldown_and_listen_only():
    cfg = BehaviorConfig(group_chattiness=0.05, interest_boost=0.6, interests=["流星"])
    policy = Policy(cfg, ["可乐"], random.Random(3))
    hot = [ev(GROUP, "今晚有流星雨吗")]
    replies = sum(policy.decide(GROUP, hot, AWAKE, ChatStats()).act == "reply" for _ in range(200))
    cooled = sum(policy.decide(GROUP, hot, AWAKE, ChatStats(seconds_since_self=10)).act == "reply" for _ in range(200))
    assert replies > cooled * 2
    listen = [ev(GROUP, "可乐", meta={"listen_only": True})]
    assert policy.decide(GROUP, listen, AWAKE, ChatStats()).act == "ignore"
    assert policy.decide(GROUP, hot, AWAKE, ChatStats(can_speak=False)).act == "ignore"


def test_mood_drifts_back_to_baseline():
    mood = MoodEngine()
    mood.feel("sad", 2.0, now=1000.0)
    low = mood.current(1000.0).valence
    later = mood.current(1000.0 + 6 * 3600).valence
    assert low < later < MoodEngine.BASE_VALENCE + 0.01
    assert mood.label(0.1) == "困"
    assert not mood.feel("not-a-feeling")
