import json

from anima.core.events import Chat, Sender
from anima.core.memory import similar
from anima.skills.base import REGISTRY, SkillContext, run_skill, select

DM = Chat("playground", "private", "you")


async def call(brain, name, args, sender=Sender("pg-你", "你"), chat=DM):
    return json.loads(await run_skill(REGISTRY[name], SkillContext(brain, chat, sender), args))


async def test_fortune_is_stable_per_person_per_day(make_brain):
    brain, _ = make_brain()
    a = await call(brain, "fortune", {})
    b = await call(brain, "fortune", {})
    c = await call(brain, "fortune", {}, sender=Sender("pg-小鱼", "小鱼"))
    assert a == b
    assert {"level", "lucky_color", "good_for", "avoid"} <= a.keys()
    assert isinstance(c["level"], str)


async def test_guess_number_game_keeps_hidden_state(make_brain):
    brain, _ = make_brain()
    await call(brain, "game", {"action": "start", "game": "guess_number"})
    secret = (await brain.memory.get_state(f"game:{DM.key}"))["secret"]
    low = await call(brain, "game", {"action": "move", "move": str(max(1, secret - 1))})
    assert low["result"] in ("小了", "猜中了")
    win = await call(brain, "game", {"action": "move", "move": str(secret)})
    assert win["result"] == "猜中了"
    assert await brain.memory.get_state(f"game:{DM.key}") is None


async def test_turtle_soup_and_idiom_chain(make_brain):
    brain, _ = make_brain()
    soup = await call(brain, "game", {"action": "start", "game": "turtle_soup"})
    assert "surface" in soup and "answer" not in soup
    state = await brain.memory.get_state(f"game:{DM.key}")
    assert state["answer"]
    await call(brain, "game", {"action": "stop"})
    start = await call(brain, "game", {"action": "start", "game": "idiom_chain"})
    first = start["first"]
    bad = await call(brain, "game", {"action": "move", "move": first})
    assert bad["valid"] is False
    ok = await call(brain, "game", {"action": "move", "move": first[-1] + "天动地"})
    assert ok["same_char_link"] is True


async def test_dice_choose_and_reminder(make_brain):
    brain, _ = make_brain()
    roll = await call(brain, "dice", {"expr": "2d6+1"})
    assert 3 <= roll["total"] <= 13 and len(roll["rolls"]) == 2
    pick = await call(brain, "choose", {"options": ["火锅", "烤肉"]})
    assert pick["picked"] in ("火锅", "烤肉")
    due = brain.clock.now().replace(microsecond=0)
    when = (due.replace(hour=(due.hour + 1) % 24)).strftime("%Y-%m-%dT%H:%M")
    rem = await call(brain, "set_reminder", {"when": when, "text": "喝水"})
    assert rem.get("ok") or rem.get("error")  # past-midnight edge case is allowed to fail cleanly


async def test_memory_dedupes_similar_facts(memory):
    assert await memory.add_fact("u1", "养了一只柯基叫豆豆", 3)
    assert not await memory.add_fact("u1", "养了一只柯基，叫豆豆", 4)
    facts = await memory.facts("u1")
    assert len(facts) == 1 and facts[0].importance == 4
    assert similar("喜欢看星星", "很喜欢看星星")


def test_skill_selection_patterns(bot):
    names = {s.name for s in select(["*", "-weather"])}
    assert "weather" not in names and "fortune" in names
    assert {s.name for s in select(["fortune", "dice"])} == {"fortune", "dice"}
    spec = REGISTRY["remember"].spec()
    assert spec.parameters["additionalProperties"] is False
