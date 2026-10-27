"""世界书, character cards, recall, owner controls, friend requests, 表情包, captions, MCP plugins."""

import base64
import io
import json
import shutil
import sys
import textwrap

import pytest

from anima.core.cards import card_fields, create_bot_from_card, read_card
from anima.core.events import Chat, Image, Incoming, Sender
from anima.core.lorebook import Lorebook, from_sillytavern
from anima.llm.fake import FakeLLM
from tests.conftest import Recorder, wait_idle

DM = Chat("playground", "private", "you")
ME = Sender("pg-你", "你")
QQ_GROUP = Chat("qq", "group", "123", "测试群")


class QQRecorder(Recorder):
    platform = "qq"
    capabilities = frozenset({"poke", "typing", "image"})

    def __init__(self):
        super().__init__()
        self.answered: list[tuple[int, bool]] = []

    async def answer_request(self, request, approve):
        self.answered.append((request["id"], approve))
        return True


# ------------------------------------------------------------------ 世界书 and cards

ST_WORLD = {"entries": {
    "0": {"uid": 0, "key": ["流星"], "keysecondary": [], "content": "{{char}}许过一个关于流星的愿望", "constant": False,
          "disable": False, "order": 100, "comment": "流星"},
    "1": {"uid": 1, "key": [], "content": "世界观：这里的人都会魔法", "constant": True, "order": 10},
    "2": {"uid": 2, "key": ["/龙(族|骑士)/"], "content": "龙族住在北方", "order": 50},
}}


def test_lorebook_triggers_and_imports_sillytavern(tmp_path):
    book = Lorebook(tmp_path)
    book.save("st", from_sillytavern(ST_WORLD))
    assert book.triggered("今天看到流星了", replacements={"{{char}}": "可乐"}) == [
        "世界观：这里的人都会魔法", "可乐许过一个关于流星的愿望"]
    assert "龙族住在北方" in book.triggered("我是龙骑士")
    assert book.triggered("随便聊聊") == ["世界观：这里的人都会魔法"]
    (tmp_path / "raw.json").write_text(json.dumps(ST_WORLD, ensure_ascii=False))
    assert len(Lorebook(tmp_path).books["raw"]) == 3, "a SillyTavern file dropped into the folder just works"


def _card_png(card: dict) -> bytes:
    from PIL import Image as PILImage
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("chara", base64.b64encode(json.dumps(card, ensure_ascii=False).encode()).decode())
    buf = io.BytesIO()
    PILImage.new("RGB", (8, 8), "pink").save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


def test_character_card_becomes_a_bot(tmp_path, monkeypatch):
    shutil.copytree("bots/_template", tmp_path / "_template")
    monkeypatch.setattr("anima.core.cards.BOTS_DIR", tmp_path)
    card = {"spec": "chara_card_v2", "data": {
        "name": "露娜", "description": "{{char}}是一只会说话的月光狐狸。", "personality": "温柔，爱吐槽",
        "first_mes": "你好呀，{{user}}～", "mes_example": "<START>\n{{user}}: 你是谁\n{{char}}: 月光的狐狸呀",
        "character_book": {"entries": [{"keys": ["月亮"], "content": "露娜在满月时最有精神", "enabled": True}]},
    }}
    png = _card_png(card)
    assert card_fields(read_card(png))["name"] == "露娜"
    folder = create_bot_from_card(png, "luna")
    persona = (folder / "persona.md").read_text()
    assert "露娜是一只会说话的月光狐狸" in persona and "不撒谎" in persona
    assert "你：月光的狐狸呀" in (folder / "examples.md").read_text()
    assert Lorebook(folder / "lorebook").triggered("今晚的月亮") == ["露娜在满月时最有精神"]
    assert 'display_name = "露娜"' in (folder / "bot.toml").read_text()


# ------------------------------------------------------------------ recall and scene

async def test_recall_and_lore_reach_her_scene(make_brain):
    seen = {}

    def responder(system, turns, dynamic):
        seen["dynamic"] = dynamic
        return "嗯嗯"

    brain, _ = make_brain(responder)
    await brain.memory.touch_user("qq", "42", "小明")
    await brain.memory.add_fact("qq:42", "小明在学吉他，最近在练指弹", 4)
    await brain.handle(Incoming(DM, ME, "我最近想学吉他，你有推荐吗", message_id="r1"))
    await wait_idle(brain)
    assert "小明：小明在学吉他" in seen["dynamic"], "she connects the topic to someone else she knows"
    await brain.handle(Incoming(DM, ME, "你家的猫还好吗", message_id="r2"))
    await wait_idle(brain)
    assert "[世界书" in seen["dynamic"] and "Bug" in seen["dynamic"]
    assert "[你的表情包]" in seen["dynamic"] and "笑死" in seen["dynamic"]


# ------------------------------------------------------------------ owner controls

async def test_owner_commands_block_and_mute(make_brain):
    brain, rec = make_brain(lambda *a: "在呢")
    qq = QQRecorder()
    qq.brain = brain
    brain.attach(qq)
    await brain.handle(Incoming(DM, ME, "/拉黑 10086", message_id="c1"))
    assert rec.sent[-1][1] == "已拉黑 10086"
    await brain.handle(Incoming(Chat("qq", "private", "10086"), Sender("10086", "坏人"), "在吗", message_id="c2"))
    await wait_idle(brain)
    assert qq.sent == [] and await brain.memory.recent("qq:private:10086") == []
    # someone who isn't the owner can't use commands
    brain.cfg.owners = []
    await brain.handle(Incoming(Chat("qq", "private", "7"), Sender("7", "路人"), "/放行 10086", message_id="c3"))
    await wait_idle(brain)
    assert (await brain.memory.get_user("qq:10086")).blocked == 1
    await brain.handle(Incoming(DM, ME, "/状态", message_id="c4"))
    assert "模型" in rec.sent[-1][1]


async def test_she_can_end_a_chat(make_brain):
    def responder(system, turns, dynamic):
        return [("tool", "end_chat", {"minutes": 30, "reason": "一直骂人"}), "我先不跟你聊了"]

    brain, rec = make_brain(responder)
    await brain.handle(Incoming(DM, ME, "骂人的话", message_id="e1"))
    await wait_idle(brain)
    assert rec.sent[-1][1] == "我先不跟你聊了"
    await brain.handle(Incoming(DM, ME, "喂", message_id="e2"))
    await wait_idle(brain)
    assert len(rec.sent) == 1, "she stays quiet until the silence runs out"
    assert (await brain.memory.get_user("playground:pg-你")).silenced_until > brain.clock.timestamp()


async def test_friend_requests_follow_the_rules(make_brain, bot):
    bot.config.owners = ["qq:1"]
    brain, _ = make_brain(lambda *a: "你好呀")
    qq = QQRecorder()
    qq.brain = brain
    brain.attach(qq)
    for _ in range(3):
        await brain.memory.touch_user("qq", "55", "熟人")
    assert await brain.admin.on_request("qq", "friend", "55", "flag-a", user_name="熟人") == "approve"
    assert await brain.admin.on_request("qq", "friend", "66", "flag-b", user_name="陌生人", comment="hi") == "pending"
    await wait_idle(brain)
    import asyncio

    await asyncio.sleep(0.1)
    assert qq.answered[0][1] is True
    assert any("陌生人" in s[1] and "/同意" in s[1] for s in qq.sent if s[0] == "qq:private:1"), "owner was asked"
    pending = await brain.memory.requests()
    assert [r["user_id"] for r in pending] == ["66"]
    assert "已同意" in await brain.admin.decide(pending[0]["id"], True)


async def test_demo_brain_stays_silent_on_real_platforms(bot, memory):
    from anima.core.brain import Brain

    brain = Brain(bot, memory, FakeLLM())
    brain.humanizer.scale = 0
    qq = QQRecorder()
    qq.brain = brain
    brain.attach(qq)
    await brain.handle(Incoming(Chat("qq", "private", "9"), Sender("9", "朋友"), "在吗", message_id="d1"))
    await wait_idle(brain)
    assert qq.sent == []


# ------------------------------------------------------------------ 表情包 and captions

async def test_meme_tag_sends_a_real_sticker(make_brain):
    rec = QQRecorder()
    brain, _ = make_brain(lambda *a: "哈哈哈\n[meme:笑死]", adapter=rec)
    await brain.handle(Incoming(Chat("qq", "private", "9"), Sender("9", "朋友"), "讲个笑话", message_id="m1"))
    await wait_idle(brain)
    images = [seg for b in rec.bubbles for seg in b.segments if seg.type == "image"]
    assert images and images[0].path.endswith("01.png") and "笑死" in images[0].path


class SeeingLLM(FakeLLM):
    @property
    def supports_vision(self):
        return True

    async def see(self, image, prompt):
        return "一只柴犬歪头斜眼看人｜狗头 无语 嫌弃"


async def test_images_are_captioned_and_stickers_collected(make_brain, bot, memory):
    from anima.core.brain import Brain
    from anima.web import wake_offset

    bot.config.behavior.collect_stickers = 1.0
    brain = Brain(bot, memory, SeeingLLM(lambda *a: "[silent]"))
    brain.humanizer.scale = 0
    brain.clock.set_offset_hours(wake_offset(brain.clock, 20))
    rec = Recorder()
    rec.brain = brain
    brain.attach(rec)
    png = base64.b64encode(_card_png({"name": "x"})).decode()
    ev = Incoming(Chat("playground", "group", "lab"), Sender("pg-小鱼", "小鱼"), "[表情包]", message_id="s1",
                  images=[Image(data=png, media_type="image/png")], meta={"sticker": True})
    await brain.handle(ev)
    await wait_idle(brain)
    import asyncio

    for _ in range(50):
        if await brain.memory.stickers():
            break
        await asyncio.sleep(0.02)
    row = (await brain.memory.recent("playground:group:lab"))[0]
    assert row.text == "[表情包：一只柴犬歪头斜眼看人]"
    saved = await brain.memory.stickers()
    assert saved and saved[0]["tags"] == "狗头 无语 嫌弃"
    picked = await brain.memes.pick("无语")
    assert picked is not None


# ------------------------------------------------------------------ MCP plugins

MCP_SERVER = textwrap.dedent('''
    from mcp.server.mcpserver import MCPServer
    server = MCPServer("calc")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    server.run()
''')


async def test_mcp_server_tools_become_her_skills(make_brain, tmp_path):
    from anima.plugins import PluginManager
    from anima.skills.base import SkillContext, run_skill

    brain, _ = make_brain()
    script = tmp_path / "calc_server.py"
    script.write_text(MCP_SERVER)
    plugins = PluginManager(brain)
    plugins.path = tmp_path / "mcp.json"
    plugins.save_config({"calc": {"command": sys.executable, "args": [str(script)]}})
    try:
        await plugins.start()
        state = plugins.servers["calc"]
        assert state.status == "running", state.error
        skill = next(s for s in brain.skills if s.name == "calc__add")
        out = await run_skill(skill, SkillContext(brain, DM, ME), {"a": 2, "b": 3})
        assert out.strip() == "5"
        assert plugins.status()[0]["tools"][0]["skill"] == "calc__add"
    finally:
        await plugins.stop()
    assert not any(s.name.startswith("calc__") for s in brain.skills)


@pytest.fixture
def scratch_bot(tmp_path, monkeypatch):
    """A copy of Claudette whose files the console may rewrite."""
    import anima.config as config

    shutil.copytree("bots/claudette", tmp_path / "bots" / "claudette")
    shutil.copytree("bots/_template", tmp_path / "bots" / "_template")
    monkeypatch.setattr(config, "BOTS_DIR", tmp_path / "bots")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    return tmp_path


async def test_console_settings_people_and_stickers(scratch_bot, monkeypatch):
    import httpx

    from anima.runtime import Runtime
    from anima.web import create_app

    monkeypatch.setattr("anima.runtime.load_bot", __import__("anima.config", fromlist=["load_bot"]).load_bot)
    runtime = Runtime("claudette", platforms=["playground"])
    await runtime.setup()
    try:
        app = create_app(runtime)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
            s = (await client.get("/api/console/settings")).json()
            assert s["values"]["qq.friend_requests"] == "smart" and "可乐" in s["persona"]
            values = {"owners": ["qq:12345"], "group_chattiness": 0.2, "qq.groups": [111, 222]}
            r = (await client.put("/api/console/settings", json={"values": values})).json()
            assert set(r["changed"]) == {"owners", "group_chattiness", "qq.groups"}
            toml = (runtime.bot.dir / "bot.toml").read_text()
            assert 'owners = ["qq:12345"]' in toml and "group_chattiness = 0.2" in toml
            assert "# Claudette (可乐)" in toml, "comments survive"
            assert runtime.brain.cfg.owners == ["qq:12345"] and runtime.brain.policy.cfg.group_chattiness == 0.2
            await runtime.memory.touch_user("qq", "42", "小明")
            await client.patch("/api/console/people/qq:42", json={"profile": "考研党，喜欢猫", "blocked": True})
            p = (await client.get("/api/console/people/qq:42")).json()
            assert p["profile"] == "考研党，喜欢猫" and p["blocked"] == 1
            png = base64.b64encode(_card_png({"name": "x"})).decode()
            stickers = (await client.post("/api/console/stickers", json={"filename": "doge.png", "data": png,
                                                                         "tags": "狗头 坏笑"})).json()
            mine = [s for s in stickers if s["source"] == "console"]
            assert mine and mine[0]["tags"] == ["狗头", "坏笑"]
            assert (await client.get(mine[0]["url"])).status_code == 200
            assert (await client.get("/api/console/overview")).json()["stickers"] >= 17
    finally:
        await runtime.brain.stop()
        await runtime.memory.close()


def test_every_page_has_the_language_toggle_and_english_for_its_words():
    import re
    from pathlib import Path

    static = Path("src/anima/web/static")
    i18n = (static / "i18n.js").read_text(encoding="utf-8")
    keys = set(re.findall(r'"((?:[^"\\\n]|\\.)*)":', i18n))
    for page in ("index.html", "providers.html", "console.html"):
        html = (static / page).read_text(encoding="utf-8")
        assert '<script src="/static/i18n.js' in html and "data-lang-slot" in html and "I18N.mount()" in html, page
        said = set(re.findall(r'\bt\("((?:[^"\\\n]|\\.)*)"', html))
        missing = {s for s in said if re.search(r"[一-鿿]", s) and s not in keys}
        assert not missing, f"{page}: no English for {sorted(missing)}"


async def test_openai_compatible_endpoint_serves_her_brain(make_brain, monkeypatch):
    import httpx
    from fastapi import FastAPI

    from anima.web import is_local
    from anima.web.openai_api import openai_router

    brain, _ = make_brain(lambda s, turns, d: "嗨嗨\n我是可乐[sticker:cute]")

    class R:
        pass

    runtime = R()
    runtime.brain, runtime.bot = brain, brain.bot
    app = FastAPI()
    app.include_router(openai_router(runtime, is_local))
    monkeypatch.delenv("ANIMA_API_KEY", raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
        models = (await client.get("/v1/models")).json()
        assert models["data"][0]["id"] == "claudette"
        resp = (await client.post("/v1/chat/completions", json={
            "model": "claudette", "user": "astrbot-42", "messages": [{"role": "user", "content": "你好"}]})).json()
        assert resp["choices"][0]["message"]["content"] == "嗨嗨\n我是可乐😋"
        assert (await client.get("/v1/models", headers={"host": "host.docker.internal:8765"})).status_code == 403
        monkeypatch.setenv("ANIMA_API_KEY", "k-123")
        ok = await client.get("/v1/models", headers={"host": "host.docker.internal:8765", "authorization": "Bearer k-123"})
        assert ok.status_code == 200
    history = await brain.memory.recent("api:private:astrbot-42")
    assert [m.is_self for m in history] == [False, True, True], "each conversation is remembered"
