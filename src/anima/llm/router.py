"""One brain, several providers: chat on one model, background work on another, backups on error."""

from __future__ import annotations

from typing import Any

from loguru import logger

from anima.llm.base import LLMError, LLMProvider, LLMResult


class RoutedLLM(LLMProvider):
    name = "routed"

    def __init__(self, main: LLMProvider, side: LLMProvider, backups: list[LLMProvider], source: str = "bot.toml"):
        super().__init__(main.model, side.side_model, main.max_tokens)
        self.main, self.side, self.backups, self.source = main, side, backups, source
        self.label = main.label

    @property
    def supports_vision(self) -> bool:
        return self.main.supports_vision

    async def _chain(self, providers: list[LLMProvider], call: str, *args: Any, **kwargs: Any) -> LLMResult:
        last: LLMError | None = None
        for i, provider in enumerate(providers):
            try:
                result: LLMResult = await getattr(provider, call)(*args, **kwargs)
            except LLMError as exc:
                last = exc
                logger.warning("{} failed ({}){}", provider.label, exc, ", trying the backup" if i + 1 < len(providers) else "")
                continue
            if i:
                result.provider = f"{provider.label}（备用）"
            return result
        assert last is not None
        raise last

    async def converse(self, *args: Any, **kwargs: Any) -> LLMResult:
        return await self._chain([self.main, *self.backups], "converse", *args, **kwargs)

    async def complete(self, *args: Any, **kwargs: Any) -> LLMResult:
        return await self._chain([self.side, *self.backups], "complete", *args, **kwargs)

    def describe(self) -> dict[str, Any]:
        def one(p: LLMProvider, model: str) -> dict[str, str]:
            return {"provider": p.label, "id": getattr(p, "provider_id", ""), "model": model}

        return {
            "main": one(self.main, self.main.model),
            "side": one(self.side, self.side.side_model),
            "backups": [one(b, b.model) for b in self.backups],
            "source": self.source,
        }
