"""HTTP API behind the 模型提供商 panel: connect providers, test them, route a bot's brain."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body, HTTPException

from anima.adapters.playground import PRIVATE
from anima.core.markup import parse_reply
from anima.llm import build_target
from anima.llm.base import LLMError, Turn
from anima.llm.catalog import GROUP_NAMES, PRESETS
from anima.llm.registry import Routing, Target, clear_routing, detect, load_routing, save_routing

if TYPE_CHECKING:
    from anima.runtime import Runtime

PING_SYSTEM = "这是一次连通性测试。"
PING_PROMPT = "只回复两个字：在呢"
PREVIEW_MESSAGE = "嗨{name}！第一次见面，跟我打个招呼、介绍一下自己吧"


def provider_router(runtime: Runtime) -> APIRouter:
    router = APIRouter(prefix="/api")
    store = runtime.store

    def state() -> dict[str, Any]:
        brain = runtime.brain
        llm = brain.llm
        active = llm.describe() if hasattr(llm, "describe") else None
        return {
            "bot": {"key": runtime.bot.key, "name": brain.cfg.identity.display_name},
            "presets": [p.to_dict() for p in PRESETS],
            "groups": GROUP_NAMES,
            "providers": [store.public(e) for e in store.all()],
            "routing": load_routing(runtime.bot).to_dict(),
            "active": active,
            "demo_note": getattr(llm, "note", "") if active is None else "",
            "cost": brain.cost_text(),
            "usage": brain.usage.__dict__,
        }

    def ready(provider_id: str, model: str | None):
        provider, why = build_target(store, Target(provider_id, model or ""), runtime.bot.config.llm)
        if provider is None:
            raise HTTPException(400, why)
        return provider

    @router.get("/providers")
    async def get_state() -> dict[str, Any]:
        return state()

    @router.post("/providers")
    async def upsert(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        entry = store.upsert(body)
        if entry.id in _routed_ids(runtime):
            runtime.rebuild_llm()
        return {"provider": store.public(entry), "state": state()}

    @router.delete("/providers/{provider_id}")
    async def delete(provider_id: str) -> dict[str, Any]:
        if not store.delete(provider_id):
            raise HTTPException(404, "没有这个提供商")
        runtime.rebuild_llm()
        return state()

    @router.post("/providers/{provider_id}/models")
    async def fetch_models(provider_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        provider = ready(provider_id, body.get("model"))
        try:
            models = await provider.list_models()  # type: ignore[attr-defined]
        except (LLMError, AttributeError) as exc:
            raise HTTPException(502, str(exc)) from exc
        entry = store.get(provider_id)
        if entry:
            store.upsert({"id": entry.id, "models": list(dict.fromkeys(entry.models + models))})
        return {"models": models, "state": state()}

    @router.post("/providers/{provider_id}/test")
    async def test(provider_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        provider = ready(provider_id, body.get("model"))
        started = time.perf_counter()
        try:
            result = await provider.complete(PING_SYSTEM, PING_PROMPT, max_tokens=32)
        except LLMError as exc:
            outcome = {"ok": False, "error": str(exc), "model": provider.model}
        else:
            runtime.brain.account(result)
            outcome = {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000),
                       "reply": result.text.strip()[:80], "model": result.model,
                       "usage": result.usage.__dict__, "cost": result.cost, "currency": result.currency}
        store.record_test(provider_id, outcome)
        return {**outcome, "state": state()}

    @router.post("/providers/{provider_id}/preview")
    async def preview(provider_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Hear how she sounds on this model: her full persona, one greeting, no tools."""
        provider = ready(provider_id, body.get("model"))
        brain = runtime.brain
        scene = await brain.scene(PRIVATE, [], "有人第一次来跟你打招呼（这是在试听你在这个模型上的样子）")

        async def no_tools(name: str, args: dict) -> str:
            return "{}"

        started = time.perf_counter()
        try:
            result = await provider.converse(brain.prompt.system(), [Turn("user", PREVIEW_MESSAGE.format(name=brain.cfg.identity.display_name))],
                                             brain.prompt.dynamic(scene), [], no_tools)
        except LLMError as exc:
            raise HTTPException(502, str(exc)) from exc
        brain.account(result)
        reply = parse_reply(result.text, brain.stickers, brain.cfg.behavior.max_bubbles, brain.names)
        bubbles = []
        for bubble in brain.humanizer.shape(reply.bubbles):
            text = "".join(s.value if s.type == "text" else brain.stickers.emoji(s.value) for s in bubble.segments)
            bubbles.append({"text": text, "voice": bubble.voice})
        return {"bubbles": bubbles, "raw": result.text, "model": result.model,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "cost": result.cost, "currency": result.currency, "usage": result.usage.__dict__}

    @router.post("/providers/{provider_id}/exam")
    async def exam(provider_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """考考她: the persona exam on this provider/model (scratch memory, real model calls)."""
        from anima import evals

        provider = ready(provider_id, body.get("model"))
        results = await evals.run(runtime.bot, provider)
        s = evals.summary(results)
        if s["currency"]:
            costs = runtime.brain.costs
            costs[s["currency"]] = costs.get(s["currency"], 0.0) + s["cost"]
        path = evals.save_report(runtime.bot, results, f"{provider.label} · {provider.model}")
        return {
            "summary": s,
            "report": str(path),
            "results": [
                {"title": r.scenario.title, "passed": r.passed, "lines": r.scenario.lines, "bubbles": r.bubbles,
                 "tools": r.tools, "failed": [n for n, ok in r.checks if not ok], "error": r.error,
                 "latency_ms": r.latency_ms}
                for r in results
            ],
        }

    @router.get("/providers/detect")
    async def detected() -> list[dict[str, Any]]:
        return [asdict(d) for d in await detect(store)]

    @router.post("/providers/import")
    async def import_detected(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        match = next((d for d in await detect(store) if d.id == body.get("id")), None)
        if match is None:
            raise HTTPException(404, "没找到这个来源")
        entry = store.upsert(dict(match.spec))
        return {"provider": store.public(entry), "state": state()}

    @router.put("/routing")
    async def set_routing(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            routing = Routing.from_dict(body)
        except (KeyError, AssertionError, TypeError) as exc:
            raise HTTPException(400, "需要 main.provider") from exc
        for target in [routing.main, routing.side, *routing.backups]:
            if target and store.entry_for(target.provider) is None:
                raise HTTPException(400, f"不认识的提供商 {target.provider}")
        save_routing(runtime.bot, routing)
        runtime.rebuild_llm()
        return state()

    @router.delete("/routing")
    async def reset_routing() -> dict[str, Any]:
        clear_routing(runtime.bot)
        runtime.rebuild_llm()
        return state()

    return router


def _routed_ids(runtime: Runtime) -> set[str]:
    routing = load_routing(runtime.bot)
    return {t.provider for t in [routing.main, routing.side, *routing.backups] if t}
