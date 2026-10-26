"""Any OpenAI-compatible chat endpoint: DeepSeek, Kimi, GLM, Qwen, Doubao, OpenRouter, Ollama, LM Studio.

Kept separate from the Anthropic provider on purpose; the two speak different wire formats.
The prompt layout mirrors the Claude one (stable system prompt first, history, the per-turn
scene as a trailing system message), which is also what prefix caches like DeepSeek's reward.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, AuthenticationError

from anima.llm.base import LLMError, LLMProvider, LLMResult, ToolExecutor, ToolSpec, Turn, Usage, merge_turns

_THINK = re.compile(r"<think>.*?</think>", re.S)
_SAMPLING = ("temperature", "top_p", "presence_penalty", "frequency_penalty")


def _usage(raw: Any) -> Usage:
    if not raw:
        return Usage()
    prompt = raw.prompt_tokens or 0
    # DeepSeek reports prompt_cache_hit_tokens; OpenAI-style APIs report prompt_tokens_details.cached_tokens.
    cached = getattr(raw, "prompt_cache_hit_tokens", None)
    if cached is None:
        details = getattr(raw, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
    cached = cached or 0
    return Usage(input_tokens=max(0, prompt - cached), output_tokens=raw.completion_tokens or 0, cache_read=cached)


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
        params: dict[str, Any] | None = None,
        side_params: dict[str, Any] | None = None,
        timeout: float = 90.0,
        label: str = "",
    ):
        super().__init__(model, side_model, max_tokens)
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key or "not-needed", timeout=timeout, max_retries=1)
        self.base_url = base_url
        self.vision = vision
        self.params = dict(params or {})
        # Side tasks (JSON reflection, diary) default to the same body extras but no sampling tweaks.
        self.side_params = dict(side_params) if side_params is not None else {
            k: v for k, v in self.params.items() if k not in _SAMPLING
        }
        self.label = label or self.label

    @property
    def supports_vision(self) -> bool:
        return self.vision

    def _kwargs(self, params: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in params.items():
            if key == "extra_body" and isinstance(value, dict):
                out["extra_body"] = value
            elif key in _SAMPLING or key in ("reasoning_effort", "seed", "max_tokens"):
                out[key] = value
        return out

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
            raise LLMError(f"{self.label}: API key rejected") from exc
        except APITimeoutError as exc:
            raise LLMError(f"{self.label}: request timed out") from exc
        except APIStatusError as exc:
            raise LLMError(f"{self.label}: error {exc.status_code}: {exc.message}") from exc
        except APIConnectionError as exc:
            raise LLMError(f"{self.label}: cannot reach {self.base_url}") from exc

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
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens, **self._kwargs(self.params)}
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools
            ]
        result = LLMResult(text="", model=self.model)
        for round_no in range(max_rounds + 1):
            resp = await self._create(messages=messages, **kwargs)
            result.usage.add(_usage(resp.usage))
            result.model = resp.model or self.model
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
                    parsed.append((call, args if isinstance(args, dict) else {}))
                outputs = await asyncio.gather(*(execute(c.function.name, a) for c, a in parsed))
                for (call, args), output in zip(parsed, outputs, strict=True):
                    result.tool_calls.append({"name": call.function.name, "input": args, "output": output})
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
                continue
            result.text = _THINK.sub("", msg.content or "").strip()
            result.stop_reason = resp.choices[0].finish_reason or ""
            break
        return self.priced(result)

    async def complete(self, system: str, prompt: str, *, schema: dict | None = None, max_tokens: int = 3000) -> LLMResult:
        sys_text = system
        kwargs: dict[str, Any] = {"model": self.side_model, "max_tokens": max_tokens, **self._kwargs(self.side_params)}
        if schema:
            sys_text += (
                "\n\nOutput a single json object (只输出一个 JSON 对象) that follows this JSON Schema, "
                "with no other text:\n" + json.dumps(schema, ensure_ascii=False)
            )
            kwargs["response_format"] = {"type": "json_object"}
        kwargs["messages"] = [{"role": "system", "content": sys_text}, {"role": "user", "content": prompt}]
        resp = await self._create(**kwargs)
        text = _THINK.sub("", resp.choices[0].message.content or "").strip()
        if schema:
            start, end = text.find("{"), text.rfind("}")
            text = text[start : end + 1] if start >= 0 and end > start else text
        result = LLMResult(text=text, model=resp.model or self.side_model, usage=_usage(resp.usage),
                           stop_reason=resp.choices[0].finish_reason or "")
        return self.priced(result)

    async def see(self, image, prompt: str) -> str:
        if not (self.vision and image.data):
            raise LLMError(f"{self.label} can't see images")
        resp = await self._create(
            model=self.model, max_tokens=200, **self._kwargs(self.side_params),
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{image.media_type};base64,{image.data}"}},
                {"type": "text", "text": prompt},
            ]}],
        )
        return _THINK.sub("", resp.choices[0].message.content or "").strip()

    async def list_models(self) -> list[str]:
        try:
            page = await self.client.models.list()
        except (APIStatusError, APIConnectionError, APITimeoutError) as exc:
            raise LLMError(f"{self.label}: could not list models ({exc})") from exc
        return sorted({m.id for m in page.data})
