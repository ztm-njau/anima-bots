"""Provider-neutral interface to the language model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from anima.core.events import Image


@dataclass
class Turn:
    role: Literal["user", "assistant"]
    text: str
    images: list[Image] = field(default_factory=list)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read += other.cache_read
        self.cache_write += other.cache_write


@dataclass
class LLMResult:
    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    refused: bool = False
    stop_reason: str = ""
    cost: float = 0.0
    currency: str = ""
    provider: str = ""  # which configured provider answered (matters when a fallback kicks in)


ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


class LLMError(RuntimeError):
    pass


def merge_turns(turns: list[Turn]) -> list[Turn]:
    """Collapse consecutive same-role turns and make sure the conversation starts with the user."""
    merged: list[Turn] = []
    for turn in turns:
        if merged and merged[-1].role == turn.role:
            merged[-1] = Turn(turn.role, merged[-1].text + "\n" + turn.text, merged[-1].images + turn.images)
        else:
            merged.append(Turn(turn.role, turn.text, list(turn.images)))
    while merged and merged[0].role != "user":
        merged.pop(0)
    if not merged or merged[-1].role != "user":
        merged.append(Turn("user", "（暂时没有新消息）"))
    return merged


class LLMProvider(ABC):
    name: str = "base"

    def __init__(self, model: str, side_model: str | None = None, max_tokens: int = 4000):
        self.model = model
        self.side_model = side_model or model
        self.max_tokens = max_tokens
        self.label = self.name  # human name of the configured provider, e.g. "DeepSeek"
        self.prices: dict[str, Any] = {}  # model id -> catalog.Price

    @property
    def supports_vision(self) -> bool:
        return False

    def priced(self, result: LLMResult) -> LLMResult:
        """Fill in cost/currency from this provider's price table."""
        price = self.prices.get(result.model) or self.prices.get(self.model) or self.prices.get(self.side_model)
        result.provider = result.provider or self.label
        if price is not None:
            u = result.usage
            result.cost = price.cost(u.input_tokens, u.cache_read, u.output_tokens, u.cache_write)
            result.currency = price.currency
        return result

    @abstractmethod
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
        """One reply, running the tool loop until the model is done talking."""

    @abstractmethod
    async def complete(self, system: str, prompt: str, *, schema: dict | None = None, max_tokens: int = 3000) -> LLMResult:
        """A side task (diary, reflection, daily plan). With ``schema``, the text is JSON."""
