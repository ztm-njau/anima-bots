"""Claude via the official Anthropic SDK.

Prompt layout, chosen for cache hits: the persona system prompt is stable and cached; the
conversation history gets a second cache breakpoint on its last turn; everything volatile
(time, mood, memories, why she's replying) rides in a trailing mid-conversation system
message, so it never invalidates the cached prefix.
"""

from __future__ import annotations

import asyncio
from typing import Any

import anthropic

from anima.llm.base import LLMError, LLMProvider, LLMResult, ToolExecutor, ToolSpec, Turn, Usage, merge_turns

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-fable-5", "claude-sonnet-5-5")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_CACHE = {"type": "ephemeral"}


def _usage(resp: Any) -> Usage:
    u = resp.usage
    return Usage(
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-opus-5-5",
        side_model: str | None = None,
        *,
        api_key: str | None = None,
        effort: str = "low",
        side_effort: str = "low",
        max_tokens: int = 4000,
        web_search: bool = True,
        fallbacks: bool = True,
        vision: bool = True,
    ):
        super().__init__(model, side_model, max_tokens)
        self.client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()
        self.effort = effort
        self.side_effort = side_effort
        self.web_search = web_search
        self.fallbacks = fallbacks
        self.vision = vision

    @property
    def supports_vision(self) -> bool:
        return self.vision

    async def _create(self, model: str, **kwargs: Any) -> Any:
        try:
            if self.fallbacks and model in _FALLBACK_MODELS:
                return await self.client.beta.messages.create(
                    model=model, betas=[_FALLBACK_BETA], fallbacks="default", **kwargs
                )
            return await self.client.messages.create(model=model, **kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic API key is missing or invalid (set ANTHROPIC_API_KEY in .env)") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Model {model!r} not found") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"Bad request: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Rate limited by the Anthropic API") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Cannot reach the Anthropic API") from exc

    def _messages(self, turns: list[Turn]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for turn in merge_turns(turns):
            content: list[dict[str, Any]] = []
            if turn.role == "user" and self.vision:
                for image in turn.images[:4]:
                    if image.data:
                        source = {"type": "base64", "media_type": image.media_type, "data": image.data}
                    elif image.url:
                        source = {"type": "url", "url": image.url}
                    else:
                        continue
                    content.append({"type": "image", "source": source})
            content.append({"type": "text", "text": turn.text})
            messages.append({"role": turn.role, "content": content})
        messages[-1]["content"][-1]["cache_control"] = _CACHE
        return messages

    def _tools(self, tools: list[ToolSpec]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
        ]
        if self.web_search:
            payload.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 2})
        return payload

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
        messages = self._messages(turns)
        messages.append({"role": "system", "content": dynamic})
        kwargs: dict[str, Any] = {
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": _CACHE}],
            "output_config": {"effort": effort or self.effort},
        }
        tool_payload = self._tools(tools)
        if tool_payload:
            kwargs["tools"] = tool_payload

        result = LLMResult(text="", model=self.model)
        for _ in range(max_rounds + 2):
            resp = await self._create(self.model, messages=messages, **kwargs)
            result.usage.add(_usage(resp))
            result.model = getattr(resp, "model", self.model)
            result.stop_reason = resp.stop_reason or ""

            if resp.stop_reason == "refusal":
                result.refused = True
                return result
            if resp.stop_reason == "pause_turn":  # a server tool (web search) wants to keep going
                messages.append({"role": "assistant", "content": resp.content})
                continue

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            for block in resp.content:
                if block.type == "server_tool_use":
                    result.tool_calls.append({"name": block.name, "input": dict(block.input or {}), "server": True})
            if resp.stop_reason == "tool_use" and tool_uses and len(result.tool_calls) < max_rounds * 3:
                messages.append({"role": "assistant", "content": resp.content})
                outputs = await asyncio.gather(*(execute(b.name, dict(b.input or {})) for b in tool_uses))
                for block, output in zip(tool_uses, outputs, strict=True):
                    result.tool_calls.append({"name": block.name, "input": dict(block.input or {}), "output": output})
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": b.id, "content": out}
                            for b, out in zip(tool_uses, outputs, strict=True)
                        ],
                    }
                )
                continue

            result.text = "".join(b.text for b in resp.content if b.type == "text")
            return result
        return result

    async def complete(self, system: str, prompt: str, *, schema: dict | None = None, max_tokens: int = 3000) -> LLMResult:
        output_config: dict[str, Any] = {"effort": self.side_effort}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        resp = await self._create(
            self.side_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config=output_config,
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return LLMResult(
            text=text,
            model=getattr(resp, "model", self.side_model),
            usage=_usage(resp),
            refused=resp.stop_reason == "refusal",
            stop_reason=resp.stop_reason or "",
        )
