"""Any OpenAI-compatible chat endpoint: DeepSeek, Qwen (DashScope), Kimi, GLM, LM Studio, Ollama.

Useful as a cheap or fully local alternative to Claude. Kept separate from the Anthropic
provider on purpose; the two speak different wire formats.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, AuthenticationError

from anima.llm.base import LLMError, LLMProvider, LLMResult, ToolExecutor, ToolSpec, Turn, Usage, merge_turns

_THINK = re.compile(r"<think>.*?</think>", re.S)


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(
        self,
        model: str,
        side_model: str | None = None,
        *,
        base_url: str,
        api_key: str | None = None,
        max_tokens: int = 2000,
        vision: bool = False,
    ):
        super().__init__(model, side_model, max_tokens)
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key or "not-needed")
        self.vision = vision

    @property
    def supports_vision(self) -> bool:
        return self.vision

    def _messages(self, system: str, turns: list[Turn], dynamic: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for turn in merge_turns(turns):
            if turn.role == "user" and self.vision and turn.images:
                parts: list[dict[str, Any]] = [
                    {"type": "image_url", "image_url": {"url": f"data:{img.media_type};base64,{img.data}"}}
                    for img in turn.images[:4]
                    if img.data
                ]
                parts.append({"type": "text", "text": turn.text})
                messages.append({"role": "user", "content": parts})
            else:
                messages.append({"role": turn.role, "content": turn.text})
        messages.append({"role": "system", "content": dynamic})
        return messages

    async def _create(self, **kwargs: Any) -> Any:
        try:
            return await self.client.chat.completions.create(**kwargs)
        except AuthenticationError as exc:
            raise LLMError("API key rejected by the OpenAI-compatible endpoint") from exc
        except APIStatusError as exc:
            raise LLMError(f"LLM endpoint error {exc.status_code}: {exc.message}") from exc
        except APIConnectionError as exc:
            raise LLMError("Cannot reach the LLM endpoint") from exc

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
        messages = self._messages(system, turns, dynamic)
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens}
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools
            ]
        result = LLMResult(text="", model=self.model)
        for round_no in range(max_rounds + 1):
            resp = await self._create(messages=messages, **kwargs)
            if resp.usage:
                result.usage.add(Usage(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0))
            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            if calls and round_no < max_rounds:
                messages.append(msg.model_dump(exclude_none=True))
                parsed = []
                for call in calls:
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    parsed.append((call, args))
                outputs = await asyncio.gather(*(execute(c.function.name, a) for c, a in parsed))
                for (call, args), output in zip(parsed, outputs, strict=True):
                    result.tool_calls.append({"name": call.function.name, "input": args, "output": output})
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
                continue
            result.text = _THINK.sub("", msg.content or "").strip()
            result.stop_reason = resp.choices[0].finish_reason or ""
            return result
        return result

    async def complete(self, system: str, prompt: str, *, schema: dict | None = None, max_tokens: int = 3000) -> LLMResult:
        kwargs: dict[str, Any] = {
            "model": self.side_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if schema:
            kwargs["messages"][0]["content"] += (
                "\n\n只输出一个 JSON 对象，符合这个 JSON Schema，不要任何其他文字：\n"
                + json.dumps(schema, ensure_ascii=False)
            )
            kwargs["response_format"] = {"type": "json_object"}
        resp = await self._create(**kwargs)
        text = _THINK.sub("", resp.choices[0].message.content or "").strip()
        if schema:
            start, end = text.find("{"), text.rfind("}")
            text = text[start : end + 1] if start >= 0 and end > start else text
        usage = Usage(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0) if resp.usage else Usage()
        return LLMResult(text=text, model=self.side_model, usage=usage)
