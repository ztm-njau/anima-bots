"""A scripted model for tests and for poking around before an API key exists."""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from typing import Any

from anima.llm.base import LLMProvider, LLMResult, ToolExecutor, ToolSpec, Turn, Usage

# A responder sees (system, turns, dynamic) and returns either reply text, or a list of
# steps where ("tool", name, input) calls a tool and a plain string is the final reply.
Responder = Callable[[str, list[Turn], str], str | list[Any]]

_DEMO_LINES = [
    ["我还没睡醒……其实是还没接上大脑", "去「模型」页接一个模型（DeepSeek 就行），我就能好好跟你聊了[sticker:cute]"],
    ["收到收到", "不过我现在只会说预设好的台词，像个复读机[sticker:facepalm]", "给我一把 API key 吧"],
    ["嘿嘿，这里是演示模式", "界面、心情、作息这些你都可以先玩玩看[sticker:doge]"],
]


def demo_responder(system: str, turns: list[Turn], dynamic: str) -> str:
    return "\n".join(random.choice(_DEMO_LINES))


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, responder: Responder | None = None, side: Callable[[str, str, dict | None], Any] | None = None):
        super().__init__("fake-model")
        self.label = "演示模式"
        self.demo = responder is None and side is None  # canned lines, no real model behind it
        self.responder = responder or demo_responder
        self.side = side
        self.calls: list[dict[str, Any]] = []

    async def converse(
        self,
        system: str,
        turns: list[Turn],
        dynamic: str,
        tools: list[ToolSpec],
        execute: ToolExecutor,
        *,
        effort: str | None = None,
        max_rounds: int = 4,
    ) -> LLMResult:
        self.calls.append({"system": system, "turns": turns, "dynamic": dynamic, "tools": [t.name for t in tools]})
        script = self.responder(system, turns, dynamic)
        steps = script if isinstance(script, list) else [script]
        result = LLMResult(text="", model=self.model, usage=Usage(len(system) // 2, 20))
        for step in steps:
            if isinstance(step, tuple) and step and step[0] == "tool":
                _, name, args = step
                output = await execute(name, args)
                result.tool_calls.append({"name": name, "input": args, "output": output})
            else:
                result.text = str(step)
        return result

    async def complete(self, system: str, prompt: str, *, schema: dict | None = None, max_tokens: int = 3000) -> LLMResult:
        if self.side:
            out = self.side(system, prompt, schema)
            text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        elif schema:
            text = json.dumps(_empty_for(schema), ensure_ascii=False)
        else:
            text = "今天也是普通又可爱的一天。"
        return LLMResult(text=text, model=self.model)


def _empty_for(schema: dict) -> Any:
    kind = schema.get("type")
    if kind == "object":
        return {k: _empty_for(v) for k, v in schema.get("properties", {}).items()}
    if kind == "array":
        return []
    if kind == "string":
        return ""
    if kind in ("integer", "number"):
        return 0
    if kind == "boolean":
        return False
    return None
