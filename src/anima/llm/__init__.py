"""Language-model providers and the factory that picks one from bot.toml."""

from __future__ import annotations

from loguru import logger

from anima.config import Bot, env
from anima.llm.base import LLMError, LLMProvider, LLMResult, ToolSpec, Turn, Usage

__all__ = ["LLMError", "LLMProvider", "LLMResult", "ToolSpec", "Turn", "Usage", "make_provider", "estimate_cost"]

# USD per million tokens: input, output, cache read. Display only.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-fable-5-1": (10.0, 50.0, 0.25),
}


def estimate_cost(model: str, usage: Usage) -> float:
    price = next((p for name, p in PRICES.items() if model.startswith(name)), None)
    if not price:
        return 0.0
    inp, out, cached = price
    return (
        usage.input_tokens * inp + usage.cache_write * inp * 1.25 + usage.cache_read * cached + usage.output_tokens * out
    ) / 1_000_000


def make_provider(bot: Bot, *, force_fake: bool = False) -> LLMProvider:
    cfg = bot.config.llm
    if force_fake or cfg.provider == "fake":
        from anima.llm.fake import FakeLLM

        return FakeLLM()
    if cfg.provider == "anthropic":
        key = env(cfg.api_key_env or "ANTHROPIC_API_KEY")
        if not key and not env("ANTHROPIC_AUTH_TOKEN"):
            from anima.llm.fake import FakeLLM

            logger.warning("No ANTHROPIC_API_KEY in .env, {} runs in demo mode (canned replies)", bot.config.identity.name)
            return FakeLLM()
        from anima.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            cfg.model,
            cfg.side_model,
            api_key=key,
            effort=cfg.effort,
            side_effort=cfg.side_effort,
            max_tokens=cfg.max_tokens,
            web_search=cfg.web_search,
            fallbacks=cfg.fallbacks,
            vision=cfg.vision,
        )
    if cfg.provider == "openai_compat":
        from anima.llm.openai_compat import OpenAICompatProvider

        if not cfg.base_url:
            raise LLMError("llm.base_url is required for provider = 'openai_compat'")
        return OpenAICompatProvider(
            cfg.model,
            cfg.side_model,
            base_url=cfg.base_url,
            api_key=env(cfg.api_key_env),
            max_tokens=cfg.max_tokens,
            vision=cfg.vision,
        )
    raise LLMError(f"Unknown llm.provider {cfg.provider!r}")
