"""Provider registry, routing, the OpenAI-compatible wire format, and the panel's HTTP API."""

import json
import socket
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request

from anima.config import load_bot
from anima.llm import make_provider
from anima.llm.base import Turn
from anima.llm.catalog import PRESET_BY_ID, Price
from anima.llm.fake import FakeLLM
from anima.llm.openai_compat import OpenAICompatProvider
from anima.llm.registry import ProviderStore, Routing, Target, load_routing, save_routing
from anima.llm.router import RoutedLLM
from anima.web import is_local

BJ = ZoneInfo("Asia/Shanghai")


@pytest.fixture
def store(tmp_path, monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("anima.llm.registry.REPO_ROOT", tmp_path)  # no real .env in tests
    return ProviderStore(tmp_path / "providers.json")


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.setattr("anima.config.DATA_DIR", tmp_path / "data")
    return load_bot("claudette")


def test_deepseek_peak_pricing():
    price = PRESET_BY_ID["deepseek"].prices["deepseek-flash"]
    weekday_peak = datetime(2026, 10, 26, 10, 0, tzinfo=BJ)
    weekday_evening = datetime(2026, 10, 26, 21, 0, tzinfo=BJ)
    saturday_morning = datetime(2026, 10, 31, 10, 0, tzinfo=BJ)
    assert price.is_peak(weekday_peak) and not price.is_peak(weekday_evening) and not price.is_peak(saturday_morning)
    evening = price.cost(1_000_000, 0, 0, when=weekday_evening)
    assert evening == pytest.approx(1.0) and price.cost(1_000_000, 0, 0, when=weekday_peak) == pytest.approx(2.0)
    claude = Price(4.0, 0.2, 20.0, "USD", write_multiplier=1.25)
    assert claude.cost(0, 0, 0, cache_write=1_000_000) == pytest.approx(5.0)


def test_store_keeps_keys_private_and_resolves_env(store, monkeypatch):
    entry = store.upsert({"preset": "deepseek", "api_key": "sk-1234567890abcdef"})
    assert entry.id == "deepseek" and entry.base_url == "https://api.deepseek.com"
    public = store.public(entry)
    assert "sk-1234567890abcdef" not in json.dumps(public)
    assert public["key_hint"] == "sk-…cdef" and public["has_key"]
    assert oct(store.path.stat().st_mode & 0o777) == "0o600"
    # blank key on update keeps the old one; a second DeepSeek gets its own id
    store.upsert({"id": "deepseek", "name": "DS", "api_key": ""})
    assert store.get("deepseek").api_key == "sk-1234567890abcdef"
    assert store.upsert({"preset": "deepseek"}).id == "deepseek-2"
    # presets work without saving, keyed from their usual env vars
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-envvalue000001")
    virtual = store.entry_for("deepseek-2")
    assert store.resolve_key(virtual) == ("sk-envvalue000001", "环境变量 DEEPSEEK_API_KEY")
    assert store.entry_for("kimi").virtual and store.entry_for("nope") is None


async def test_detects_env_keys_and_claude_code_style_setups(store, monkeypatch):
    from anima.llm.registry import detect

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-abcdef")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-other-token-xyz9")
    found = {d.id: d for d in await detect(store)}
    assert found["env:DEEPSEEK_API_KEY"].preset == "deepseek"
    assert found["env:ANTHROPIC_AUTH_TOKEN@deepseek"].spec == {"preset": "deepseek", "api_key_env": "ANTHROPIC_AUTH_TOKEN"}
    assert all("sk-deepseek-abcdef" not in json.dumps(d.__dict__) for d in found.values())


def test_routing_falls_back_to_demo_without_a_key(bot, store):
    bot.config.llm.backup = None
    llm = make_provider(bot, store=store)
    assert isinstance(llm, FakeLLM) and "DeepSeek" in llm.note
    bot.config.llm.backup = "ollama:qwen2.5:1.5b"  # a key-less local backup stands in instead of demo mode
    stand_in = make_provider(bot, store=store)
    assert isinstance(stand_in, RoutedLLM) and stand_in.main.label.startswith("Ollama") and "先用备用" in stand_in.label
    store.upsert({"preset": "deepseek", "api_key": "sk-test-key-0000"})
    llm = make_provider(bot, store=store)
    assert isinstance(llm, RoutedLLM)
    assert (llm.label, llm.model) == ("DeepSeek", "deepseek-flash")
    assert llm.main.params["temperature"] == 1.3 and llm.main.params["extra_body"]["thinking"]["type"] == "disabled"
    assert "temperature" not in llm.side.side_params, "background tasks don't inherit sampling tweaks"
    assert llm.supports_vision


def test_panel_routing_overrides_bot_toml(bot, store):
    store.upsert({"preset": "ollama", "models": ["qwen2.5:1.5b"]})
    store.upsert({"preset": "deepseek", "api_key": "sk-test-key-0000"})
    save_routing(bot, Routing(Target("ollama", "qwen2.5:1.5b"), Target("deepseek", "deepseek-flash"),
                              [Target("deepseek", "deepseek-v4-pro")]))
    assert load_routing(bot).source == "panel"
    llm = make_provider(bot, store=store)
    assert (llm.main.label, llm.main.model) == ("Ollama", "qwen2.5:1.5b")
    assert llm.side.side_model == "deepseek-flash" and llm.backups[0].model == "deepseek-v4-pro"
    assert llm.describe()["source"] == "panel"


async def test_backup_takes_over_when_main_fails():
    from anima.llm.base import LLMError

    class Broken(FakeLLM):
        async def converse(self, *a, **k):
            raise LLMError("boom")

    main, backup = Broken(), FakeLLM(lambda *a: "备用在此")
    backup.label = "Ollama"
    routed = RoutedLLM(main, main, [backup])

    async def no_tools(name, args):
        return "{}"

    result = await routed.converse("sys", [Turn("user", "hi")], "scene", [], no_tools)
    assert result.text == "备用在此" and result.provider == "Ollama（备用）"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_openai_compat_wire_format_and_deepseek_cache_usage():
    seen = []
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        seen.append(body)
        usage = {"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050,
                 "prompt_cache_hit_tokens": 800, "prompt_cache_miss_tokens": 200}
        if len(seen) == 1:
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "fortune", "arguments": "{}"}}]}
            finish = "tool_calls"
        else:
            msg, finish = {"role": "assistant", "content": "大吉！\n今天适合早睡"}, "stop"
        return {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"], "usage": usage,
                "choices": [{"index": 0, "message": msg, "finish_reason": finish}]}

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    import asyncio

    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110 - uvicorn exposes no startup event
        await asyncio.sleep(0.02)
    try:
        provider = OpenAICompatProvider(
            "deepseek-flash", base_url=f"http://127.0.0.1:{port}/v1", api_key="sk-test",
            params=PRESET_BY_ID["deepseek"].params, label="DeepSeek",
        )
        provider.prices = dict(PRESET_BY_ID["deepseek"].prices)

        async def execute(name, args):
            return '{"level": "大吉"}'

        from anima.llm.base import ToolSpec

        result = await provider.converse("PERSONA", [Turn("user", "算个运势")], "[此刻] 20:00",
                                         [ToolSpec("fortune", "算运势", {"type": "object", "properties": {}})], execute)
        first, second = seen
        assert first["temperature"] == 1.3 and first["thinking"] == {"type": "disabled"}
        assert first["messages"][0] == {"role": "system", "content": "PERSONA"}
        assert first["messages"][-1] == {"role": "system", "content": "[此刻] 20:00"}, "scene rides last, prefix stays cacheable"
        assert second["messages"][-1]["role"] == "tool"
        assert result.text == "大吉！\n今天适合早睡" and result.tool_calls[0]["name"] == "fortune"
        assert (result.usage.input_tokens, result.usage.cache_read) == (400, 1600)
        assert result.currency == "CNY" and result.cost > 0
    finally:
        server.should_exit = True
        await task


def test_local_only_guard():
    assert is_local("127.0.0.1:8765", None)
    assert is_local("localhost:8765", "http://localhost:8765")
    assert not is_local("evil.example:8765", None), "DNS rebinding"
    assert not is_local("127.0.0.1:8765", "https://evil.example"), "cross-site request"


async def test_panel_api_end_to_end(tmp_path, monkeypatch, store):
    """Add a provider, route the bot to it, and watch the brain swap models live."""
    from anima.runtime import Runtime
    from anima.web import create_app

    monkeypatch.setattr("anima.config.DATA_DIR", tmp_path / "data")
    runtime = Runtime("claudette", platforms=["playground"])
    monkeypatch.setattr(runtime, "bot", load_bot("claudette"))
    runtime.bot.config.llm.backup = None
    await runtime.setup()
    try:
        app = create_app(runtime)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
            state = (await client.get("/api/providers")).json()
            assert state["active"] is None and "API key" in state["demo_note"]
            assert any(p["id"] == "deepseek" for p in state["presets"])
            added = (await client.post("/api/providers", json={"preset": "deepseek", "api_key": "sk-panel-key-0001"})).json()
            assert added["provider"]["key_hint"] == "sk-…0001" and "sk-panel-key-0001" not in json.dumps(added)
            routed = (await client.put("/api/routing", json={"main": {"provider": "deepseek", "model": "deepseek-flash",
                                                                      "params": {"temperature": 1.1}}})).json()
            assert routed["active"]["main"] == {"provider": "DeepSeek", "id": "deepseek", "model": "deepseek-flash"}
            assert runtime.brain.llm.main.params["temperature"] == 1.1
            blocked = await client.get("/api/providers", headers={"origin": "https://evil.example"})
            assert blocked.status_code == 403
            reset = (await client.delete("/api/routing")).json()
            assert reset["routing"]["source"] == "bot.toml"
    finally:
        await runtime.brain.stop()
        await runtime.memory.close()


# ------------------------------------------------------------------ magpie gateway

from contextlib import asynccontextmanager  # noqa: E402

from anima.llm.catalog import vendor_of  # noqa: E402


@asynccontextmanager
async def serve(app):
    import asyncio

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110 - uvicorn exposes no startup event
        await asyncio.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        server.should_exit = True
        await task


def fake_gateway(models):
    app = FastAPI()
    seen = {}

    @app.get("/v1/models")
    async def list_models(request: Request):
        seen["auth"] = request.headers.get("authorization")
        return {"object": "list", "data": [{"id": m, "object": "model"} for m in models]}

    return app, seen


def test_vendor_ids_map_to_presets():
    assert vendor_of("deepseek/deepseek-flash")[0].id == "deepseek"
    assert vendor_of("moonshotai/kimi-k3")[0].id == "kimi" and vendor_of("zai-org/GLM-5.3")[0].id == "zhipu"
    assert vendor_of("deepseek-flash") == (None, "deepseek-flash")


async def test_no_deepseek_key_but_magpie_serves_deepseek(bot, store):
    app, seen = fake_gateway(["auto/x", "ollama/qwen2.5:1.5b", "deepseek/deepseek-v4-pro", "deepseek/deepseek-flash"])
    async with serve(app) as base:
        store.upsert({"preset": "magpie", "base_url": base})
        import asyncio

        llm = await asyncio.to_thread(make_provider, bot, store=store)  # the gateway probe is a sync call
    assert isinstance(llm, RoutedLLM)
    assert (llm.label, llm.model) == ("DeepSeek（经 magpie）", "deepseek/deepseek-flash")
    assert seen["auth"] == "Bearer magpie", "loopback gateways take any token"
    assert llm.main.params["extra_body"]["thinking"]["type"] == "disabled", "DeepSeek's settings travel through"
    assert llm.main.prices["deepseek/deepseek-flash"].currency == "CNY" and llm.supports_vision


async def test_gateway_is_detected_and_imports_with_models(store, monkeypatch):
    from anima.llm.registry import detect

    app, _ = fake_gateway(["deepseek/deepseek-flash", "ollama/qwen2.5:1.5b"])
    async with serve(app) as base:
        monkeypatch.setattr(PRESET_BY_ID["magpie"], "base_url", base)
        for other in ("ollama", "lmstudio"):
            monkeypatch.setattr(PRESET_BY_ID[other], "base_url", "http://127.0.0.1:9/v1")  # nothing there
        found = {d.id: d for d in await detect(store)}
    gateway = found["local:magpie"]
    assert gateway.models == ["deepseek/deepseek-flash", "ollama/qwen2.5:1.5b"] and "magpie" in gateway.source
    entry = store.upsert(gateway.spec)
    assert entry.preset == "magpie" and store.public(entry)["has_key"], "no key needed for a local gateway"


async def test_key_guarded_magpie_is_still_detected(store, monkeypatch):
    """magpie's Docker build answers 401 without a gateway key: show it, with how to connect."""
    from fastapi.responses import JSONResponse

    from anima.llm.registry import detect

    app = FastAPI()

    @app.get("/v1/models")
    async def guarded():
        return JSONResponse({"error": "no API key was sent"}, status_code=401)

    async with serve(app) as base:
        monkeypatch.setattr(PRESET_BY_ID["magpie"], "base_url", base)
        for other in ("ollama", "lmstudio"):
            monkeypatch.setattr(PRESET_BY_ID[other], "base_url", "http://127.0.0.1:9/v1")
        found = {d.id: d for d in await detect(store)}
    assert "anima magpie connect" in found["local:magpie"].source


def test_one_process_per_bot(tmp_path, monkeypatch):
    from anima.runtime import AlreadyRunning, Runtime

    first = Runtime("claudette", platforms=[])
    first.claim()
    second = Runtime("claudette", platforms=[])
    with pytest.raises(AlreadyRunning):
        second.claim()
    first._lock.close()
    second.claim()  # free again once the first one is gone
    second._lock.close()
