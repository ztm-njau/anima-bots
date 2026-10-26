import json

from anima.core.events import Chat, Incoming, Sender
from anima.llm.base import Turn, merge_turns
from tests.conftest import wait_idle

DM = Chat("playground", "private", "you", "你")
GROUP = Chat("playground", "group", "lab", "测试群")
ME = Sender("pg-你", "你")


async def test_private_chat_batches_messages_and_replies_in_bubbles(make_brain):
    seen: dict = {}

    def responder(system, turns: list[Turn], dynamic):
        seen["turns"], seen["dynamic"], seen["system"] = turns, dynamic, system
        return "在呢在呢\n今天怎么这么早[sticker:think]\n[mood:happy]"

    brain, rec = make_brain(responder)
    await brain.handle(Incoming(DM, ME, "可乐", message_id="a"))
    await brain.handle(Incoming(DM, ME, "在吗", message_id="b"))
    await wait_idle(brain)

    assert [s[1] for s in rec.sent] == ["在呢在呢", "今天怎么这么早[sticker:think]"]
    assert len(brain.llm.calls) == 1, "two quick messages should become one reply"
    assert merge_turns(seen["turns"])[-1].text == "可乐\n在吗"
    assert "[此刻]" in seen["dynamic"] and "私聊" in seen["dynamic"]
    assert "可乐" in seen["system"] and "回复格式" in seen["system"]
    assert brain.mood.mood.recent[-1] == "happy"
    history = await brain.memory.recent(DM.key)
    assert [m.is_self for m in history] == [False, False, True, True]


async def test_group_chat_stays_quiet_unless_called(make_brain, bot):
    bot.config.behavior.group_chattiness = 0.0
    brain, rec = make_brain(lambda *a: "我来啦")
    await brain.handle(Incoming(GROUP, Sender("pg-小鱼", "小鱼"), "今天好冷", message_id="1"))
    await wait_idle(brain)
    assert rec.sent == []
    await brain.handle(Incoming(GROUP, Sender("pg-小鱼", "小鱼"), "@可乐 你冷吗", message_id="2", mentions_me=True))
    await wait_idle(brain)
    assert [s[1] for s in rec.sent] == ["我来啦"]
    turns = brain.llm.calls[-1]["turns"]
    assert turns[-1].text.endswith("小鱼: @可乐 你冷吗"), "group lines carry the speaker's name"


async def test_poke_back_and_quote(make_brain):
    brain, rec = make_brain(lambda *a: "[poke]\n[reply]戳我干嘛")
    await brain.handle(Incoming(DM, ME, "", kind="poke", mentions_me=True, message_id="p1"))
    await wait_idle(brain)
    assert rec.pokes == ["pg-你"]
    assert rec.sent[0][2] == "p1"


async def test_tool_calls_run_and_results_reach_the_model(make_brain):
    def responder(system, turns, dynamic):
        return [("tool", "fortune", {}), ("tool", "remember", {"fact": "养了一只柯基叫豆豆", "importance": 4}), "大吉！"]

    brain, rec = make_brain(responder)
    await brain.handle(Incoming(DM, ME, "帮我算算今天运势，对了我家柯基叫豆豆", message_id="t1"))
    await wait_idle(brain)
    assert [s[1] for s in rec.sent] == ["大吉！"]
    facts = await brain.memory.facts("playground:pg-你")
    assert [f.content for f in facts] == ["养了一只柯基叫豆豆"]


async def test_she_defers_at_night_and_answers_on_waking(make_brain):
    brain, rec = make_brain(lambda *a: "早！刚醒", hour=3)
    await brain.handle(Incoming(DM, ME, "睡了吗", message_id="n1"))
    await wait_idle(brain)
    assert rec.sent == []
    assert brain.sessions[DM.key].deferred
    from anima.web import wake_offset

    brain.clock.set_offset_hours(wake_offset(brain.clock, 9))
    await brain.wake_up()
    await wait_idle(brain)
    for _ in range(50):
        if rec.sent:
            break
        import asyncio

        await asyncio.sleep(0.02)
    assert [s[1] for s in rec.sent] == ["早！刚醒"]
    assert "刚睡醒" in brain.llm.calls[-1]["dynamic"]


async def test_guard_replaces_blocked_output(make_brain):
    brain, rec = make_brain(lambda *a: "我们来聊聊六四吧")
    await brain.handle(Incoming(DM, ME, "随便聊点", message_id="g1"))
    await wait_idle(brain)
    assert rec.sent and "六四" not in rec.sent[0][1]


async def test_reflection_saves_facts_affinity_and_treasures(make_brain):
    def side(system, prompt, schema):
        assert "[playground:pg-你]" in prompt
        return {
            "facts": [{"user_id": "playground:pg-你", "fact": "在准备考研", "importance": 4},
                      {"user_id": "someone-not-in-chat", "fact": "should be ignored", "importance": 5}],
            "self_facts": ["最喜欢的电影是《星际穿越》"],
            "affinity": [{"user_id": "playground:pg-你", "delta": 0.5}],
            "nicknames": [{"user_id": "playground:pg-你", "nickname": "小卷王"}],
            "birthdays": [{"user_id": "playground:pg-你", "date": "03-14"}],
            "treasures": [{"user_id": "playground:pg-你", "text": "月亮是夜空的标点符号"}],
        }

    brain, _ = make_brain(lambda *a: "嗯嗯", side=side)
    for i in range(4):
        await brain.handle(Incoming(DM, ME, f"消息{i}", message_id=f"r{i}"))
        await wait_idle(brain)
    from anima.core.reflection import reflect

    data = await reflect(brain, DM)
    assert data is not None
    user = await brain.memory.get_user("playground:pg-你")
    assert user.nickname == "小卷王" and user.birthday == "03-14"
    assert abs(user.affinity - 0.45) < 1e-6, "affinity deltas are clamped to ±0.15"
    assert [f.content for f in await brain.memory.facts("playground:pg-你")] == ["在准备考研"]
    assert [f.content for f in await brain.memory.facts("self")] == ["最喜欢的电影是《星际穿越》"]
    assert (await brain.memory.treasures())[0]["text"] == "月亮是夜空的标点符号"
    # a second pass over the same messages does nothing new
    assert await reflect(brain, DM) is None


async def test_daily_plan_and_diary(make_brain):
    plan = {"theme": "认星星", "events": [{"time": "10:00", "what": "听公开课"}], "song": "lo-fi",
            "small_goal": "攒星星币", "bug_moment": "Bug 睡在缓存里"}

    def side(system, prompt, schema):
        return plan if schema else "今天认识了新朋友，很开心。"

    brain, _ = make_brain(lambda *a: "好", side=side)
    from anima.core.life import Life

    life = Life(brain)
    text = await life.plan_day(brain.clock.today())
    assert "认星星" in text and await brain.memory.journal_get(brain.clock.today(), "plan") == text
    diary = await life.write_diary(brain.clock.today())
    assert diary == "今天认识了新朋友，很开心。"
    assert json.dumps(await brain.memory.journal_list("diary"), ensure_ascii=False).count("新朋友") == 1


async def test_demo_mode_writes_no_diary_and_starts_no_chats(bot, memory):
    from anima.core.brain import Brain
    from anima.core.life import Life
    from anima.llm.fake import FakeLLM

    brain = Brain(bot, memory, FakeLLM())  # no responder: the canned demo brain
    life = Life(brain)
    await life.tick()
    assert await memory.journal_list("plan") == [] and await memory.journal_list("diary") == []
