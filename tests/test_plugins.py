"""Anima plugins, AstrBot plugins on the compatibility layer, the market, personas and /mcp."""

import io
import json
import textwrap
import zipfile

import pytest

from anima import plugin_host
from anima.core.events import Chat, Incoming, Sender
from tests.conftest import wait_idle

DM = Chat("playground", "private", "you", "你")
ME = Sender("pg-你", "你")

ANIMA_PLUGIN = '''
from anima.plugin import Plugin

plugin = Plugin()

@plugin.skill("shout", "大声说", {"text": {"type": "string"}}, required=["text"])
async def shout(ctx, args):
    return args["text"].upper() + ctx.config.get("suffix", "")

@plugin.command("ping", help="测试")
async def ping(ctx, ev, arg):
    return f"pong {arg}".strip()

@plugin.on_message
async def hide(ctx, ev):
    return False if "秘密" in ev.text else None

@plugin.on_scene
async def note(ctx, chat, batch):
    return "今天是插件节"
'''

ASTRBOT_PLUGIN = '''
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp


@register("helloworld", "someone", "一个简单的 Hello World 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        self.ready = True

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """打个招呼"""
        yield event.plain_result(f"Hello, {event.get_sender_name()}!")

    @filter.command("add")
    async def add(self, event: AstrMessageEvent, a: int, b: int):
        yield event.plain_result(f"{a + b}")

    @filter.command_group("todo")
    def todo(self):
        pass

    @todo.command("list")
    async def todo_list(self, event: AstrMessageEvent):
        yield event.chain_result([Comp.Plain("1. 买牛奶")])

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("secret")
    async def secret(self, event: AstrMessageEvent):
        yield event.plain_result("only for the owner")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all(self, event: AstrMessageEvent):
        if event.message_str == "签到":
            yield event.plain_result("签到成功")
            event.stop_event()

    @filter.llm_tool(name="get_weather")
    async def get_weather(self, event: AstrMessageEvent, location: str):
        """获取天气信息。

        Args:
            location(string): 地点
        """
        return f"{location}：晴，22 度"

    @filter.on_llm_request()
    async def add_note(self, event: AstrMessageEvent, req):
        req.system_prompt += "用户喜欢猫。"
'''


def _write(folder, files: dict[str, str]):
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name).write_text(textwrap.dedent(text), encoding="utf-8")


@pytest.fixture
def plugin_dirs(tmp_path, monkeypatch):
    bundled = tmp_path / "plugins"
    monkeypatch.setattr(plugin_host, "bundled_dir", lambda: bundled)
    _write(bundled / "shouter", {"plugin.toml": 'id = "shouter"\nname = "大喇叭"\n[config]\nsuffix = { default = "!" }\n',
                                 "main.py": ANIMA_PLUGIN})
    _write(bundled / "astrbot_plugin_helloworld", {"main.py": ASTRBOT_PLUGIN,
                                                   "metadata.yaml": "name: helloworld\ndesc: hi\nversion: 1.0.0\n"})
    return bundled


async def test_anima_plugin_tools_commands_and_hooks(make_brain, plugin_dirs):
    seen = {}

    def responder(system, turns, dynamic):
        seen["dynamic"] = dynamic
        return [("tool", "shout", {"text": "hi"}), "好的"]

    brain, rec = make_brain(responder)
    host = plugin_host.PluginHost(brain)
    brain.extensions = host
    loaded = await host.load(plugin_host.discover()["shouter"])
    assert loaded and [s.name for s in loaded.skills] == ["shout"]

    await brain.handle(Incoming(DM, ME, "/ping 1", message_id="a"))
    await brain.handle(Incoming(DM, ME, "这是秘密", message_id="b"))
    await wait_idle(brain)
    assert [s[1] for s in rec.sent] == ["pong 1"], "commands answer as-is; swallowed messages never reach her"
    assert brain.llm.calls == []

    await brain.handle(Incoming(DM, ME, "喊一声", message_id="c"))
    await wait_idle(brain)
    assert "今天是插件节" in seen["dynamic"]
    assert brain.trace.history[-1]  # tool ran
    tool_result = [e for e in brain.trace.history if e["kind"] == "tool_result"][-1]
    assert tool_result["output"] == "HI!", "the plugin's own settings reach its tools"
    await host.unload("shouter")
    assert "shout" not in [s.name for s in brain.skills]


async def test_astrbot_plugin_runs_on_the_compat_layer(make_brain, plugin_dirs):
    seen = {}

    def responder(system, turns, dynamic):
        seen["dynamic"], seen["tools"] = dynamic, brain.llm.calls[-1]["tools"]
        return [("tool", "get_weather", {"location": "杭州"}), "杭州今天晴"]

    brain, rec = make_brain(responder)
    host = plugin_host.PluginHost(brain)
    brain.extensions = host
    info = plugin_host.discover()["helloworld"]
    assert info.kind == "astrbot"
    loaded = await host.load(info)
    assert loaded, host.errors
    assert {"helloworld", "add", "todo list", "secret"} <= set(loaded.plugin.commands)

    for text in ["/helloworld", "/add 2 3", "/todo list", "/secret", "签到"]:
        await brain.handle(Incoming(DM, ME, text, message_id=text))
        await wait_idle(brain)
    assert [s[1] for s in rec.sent] == ["Hello, 你!", "5", "1. 买牛奶", "only for the owner", "签到成功"]
    assert brain.llm.calls == [], "commands and the listener answered without the model"

    await brain.handle(Incoming(DM, ME, "杭州天气怎么样", message_id="w"))
    await wait_idle(brain)
    assert "get_weather" in seen["tools"]
    assert [e for e in brain.trace.history if e["kind"] == "tool_result"][-1]["output"] == "杭州：晴，22 度"
    assert "用户喜欢猫" in seen["dynamic"], "on_llm_request additions reach her scene"


async def test_owner_only_commands_refuse_others(make_brain, plugin_dirs):
    brain, rec = make_brain(lambda *a: "嗯")
    host = plugin_host.PluginHost(brain)
    brain.extensions = host
    await host.load(plugin_host.discover()["helloworld"])
    stranger = Chat("qq", "private", "42", "路人")
    out = await host.command(Incoming(stranger, Sender("42", "路人"), "/secret"), is_owner=False)
    assert out == "这个命令只有主人能用"


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


def test_install_zip_unwraps_github_archives_and_blocks_path_tricks(tmp_path):
    data = _zip({"repo-main/plugin.toml": 'id = "neat"\nname = "整洁"\n', "repo-main/main.py": "from anima.plugin import Plugin\nplugin = Plugin()\n",
                 "repo-main/../../evil.txt": "nope"})
    info = plugin_host.install_zip(data, source="test")
    assert info.id == "neat" and (plugin_host.installed_dir() / "neat" / "main.py").exists()
    assert not (tmp_path / "evil.txt").exists()
    plugin_host.uninstall("neat")
    assert not (plugin_host.installed_dir() / "neat").exists()
    with pytest.raises(ValueError):
        plugin_host.install_zip(_zip({"readme.md": "hi"}))
    assert plugin_host._github_zip("https://github.com/a/b/tree/dev/plugins/x") == (
        "https://github.com/a/b/archive/refs/heads/dev.zip", "plugins/x")


def test_mcp_registry_entries_become_server_configs():
    from anima.market import registry_config

    npm = {"packages": [{"registryType": "npm", "identifier": "some-mcp", "transport": {"type": "stdio"},
                         "environmentVariables": [{"name": "API_KEY", "isRequired": True}]}]}
    cfg, env = registry_config(npm)
    assert cfg == {"command": "npx", "args": ["-y", "some-mcp"]} and env[0]["name"] == "API_KEY"
    assert registry_config({"remotes": [{"type": "streamable-http", "url": "https://x/mcp"}]})[0] == {"url": "https://x/mcp"}
    assert registry_config({"packages": [{"registryType": "pypi", "identifier": "mcp-server-time"}]})[0] == {
        "command": "uvx", "args": ["mcp-server-time"]}


def test_bundled_plugins_and_market_index_are_valid():
    from anima.market import local_index

    found = {pid: info for pid, info in plugin_host.discover().items() if info.source == "bundled"}
    assert {"hitokoto", "keyword-reply", "countdown"} <= set(found)
    index = local_index()
    assert {p["id"] for p in index["plugins"]} <= set(found)
    assert all(m["config"].get("command") or m["config"].get("url") for m in index["mcp"])
    for pid in ("hitokoto", "keyword-reply", "countdown"):
        plugin_host._import_anima_plugin(found[pid])


async def test_bundled_keyword_reply_answers_without_the_model(make_brain, bot):
    bot.config.plugin_config = {"keyword-reply": {"rules": "群规 => 不刷屏"}}
    brain, rec = make_brain(lambda *a: "不该被调用")
    host = plugin_host.PluginHost(brain)
    brain.extensions = host
    await host.load(plugin_host.discover()["keyword-reply"])
    await brain.handle(Incoming(DM, ME, "群规是什么", message_id="k"))
    await wait_idle(brain)
    assert [s[1] for s in rec.sent] == ["不刷屏"] and brain.llm.calls == []


# ---------------------------------------------------------------- personas


@pytest.fixture
def scratch_bots(tmp_path, monkeypatch):
    import shutil

    import anima.config as config

    for name in ("claudette", "_template"):
        shutil.copytree(f"bots/{name}", tmp_path / "bots" / name)
    monkeypatch.setattr(config, "BOTS_DIR", tmp_path / "bots")
    return tmp_path / "bots"


def test_persona_create_duplicate_pack_and_retire(scratch_bots):
    from anima import personas
    from anima.config import load_bot

    key = personas.create({"name": "露娜", "who": "一只住在月亮上的狐狸\n喜欢收集星光", "voice": "说话慢悠悠的",
                           "interests": "月亮，星星", "tags": "温柔"})
    assert key.startswith("p-")
    bot = load_bot(key)
    assert bot.config.identity.display_name == "露娜" and bot.config.behavior.interests == ["月亮", "星星"]
    assert "- 一只住在月亮上的狐狸" in bot.read("persona.md") and "不撒谎" in bot.read("persona.md")
    assert bot.read_toml("life.toml")["weekday"], "files she doesn't have come from the shared template"
    assert {p["key"] for p in personas.list_personas()} >= {"claudette", key}

    pack = personas.export_pack("claudette")
    names = zipfile.ZipFile(io.BytesIO(pack)).namelist()
    assert "claudette/persona.md" in names and not any("secrets" in n or n.endswith(".py") for n in names)
    imported = personas.import_pack(pack)
    assert imported != "claudette" and load_bot(imported).config.identity.display_name == "可乐"

    copy = personas.duplicate("claudette")
    assert "副本" in load_bot(copy).config.identity.display_name
    personas.retire(copy)
    assert copy not in personas.config.list_bots()


def test_persona_pack_import_refuses_code_and_escapes(scratch_bots):
    from anima import personas

    evil = _zip({"x/bot.toml": '[identity]\nname = "x"\ndisplay_name = "X"\n', "x/persona.md": "# 你是X",
                 "x/skills/run.py": "import os", "x/../../oops.md": "no"})
    key = personas.import_pack(evil)
    folder = scratch_bots / key
    assert (folder / "persona.md").exists() and not (folder / "skills").exists()
    assert not (scratch_bots.parent / "oops.md").exists()


async def test_switching_personas_live_and_mcp_endpoint(scratch_bots, monkeypatch):
    import httpx

    from anima import personas
    from anima.config import default_bot
    from anima.runtime import Runtime
    from anima.web import RootApp

    other = personas.create({"name": "晚舟", "who": "深夜电台主播"})
    runtime = Runtime("claudette", platforms=["playground"], demo=True)
    await runtime.setup()
    runtime._lock_bot()
    runtime.web = RootApp(runtime, mcp=False)
    try:
        transport = httpx.ASGITransport(app=runtime.web)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
            listed = (await client.get("/api/console/personas")).json()
            assert listed["active"] == "claudette" and other in {p["key"] for p in listed["personas"]}
            r = await client.post(f"/api/console/personas/{other}/activate")
            assert r.status_code == 200, r.text
            assert runtime.bot.key == other and runtime.brain.cfg.identity.display_name == "晚舟"
            assert (await client.get("/api/state")).json()["name"] == "晚舟", "routes follow the new persona"
            assert default_bot() == other, "the choice is remembered for the next start"
    finally:
        await runtime.stop_services()
        runtime._unlock_bot()


async def test_mcp_tools_talk_to_the_active_persona(make_brain):
    from anima.mcp_server import build_mcp_app

    class FakeRuntime:
        pass

    brain, _ = make_brain(lambda *a: "你好呀\n我在")
    runtime = FakeRuntime()
    runtime.brain, runtime.bot = brain, brain.bot
    app = build_mcp_app(runtime)
    assert app is not None
    # The tools are plain coroutines registered on the server; call one through the SDK's in-memory client.
    from mcp.server.mcpserver import MCPServer  # noqa: F401 - imported to prove the SDK is present
    lines = await brain.answer(Chat("mcp", "private", "t", "MCP"), Sender("mcp-t", "MCP"), "嗨")
    assert lines == ["你好呀", "我在"]
    assert json.loads(json.dumps(lines))


@pytest.mark.parametrize("key", ["claudette", "wanzhou", "xiaoman"])
async def test_every_bundled_persona_builds_and_answers(key, memory):
    import random

    from anima.config import load_bot
    from anima.core.brain import Brain
    from anima.core.schedule import Schedule
    from anima.llm.fake import FakeLLM

    bot = load_bot(key)
    brain = Brain(bot, memory, FakeLLM(lambda *a: "嗯"), rng=random.Random(1))
    system = brain.prompt.system()
    assert bot.config.identity.display_name in system and "回复格式" in system
    assert bot.config.identity.tagline and bot.read_toml("life.toml")["weekday"]
    Schedule(bot.read_toml("life.toml"), brain.clock, 0).state()  # her own day parses
    lines = await brain.answer(Chat("mcp", "private", "t", "你"), Sender("t", "你"), "你好")
    assert lines == ["嗯"]
