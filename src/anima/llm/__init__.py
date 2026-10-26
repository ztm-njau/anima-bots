"""Language-model providers, and the factory that builds a bot's brain from its routing."""

from __future__ import annotations

from loguru import logger

from anima.config import Bot, LLMConfig
from anima.llm.base import LLMError, LLMProvider, LLMResult, ToolSpec, Turn, Usage
from anima.llm.registry import ProviderEntry, ProviderStore, Target, load_routing

__all__ = ["LLMError", "LLMProvider", "LLMResult", "ToolSpec", "Turn", "Usage", "build_target", "make_provider"]


def _legacy_entry(target: Target, cfg: LLMConfig) -> ProviderEntry | None:
    """bot.toml written before the provider panel: provider = "openai_compat" with a base_url."""
    if target.provider == "openai_compat":
        return ProviderEntry("openai_compat", "custom", "OpenAI 兼容", "openai", (cfg.base_url or "").rstrip("/"),
                             api_key_env=cfg.api_key_env or "", virtual=True)
    return None


def build_target(store: ProviderStore, target: Target, cfg: LLMConfig) -> tuple[LLMProvider | None, str]:
    """A ready provider for one routing target, or (None, why not)."""
    entry = _legacy_entry(target, cfg) or store.entry_for(target.provider)
    if entry is None:
        return None, f"不认识的模型提供商 {target.provider!r}"
    if not entry.enabled:
        return None, f"{entry.name} 已停用"
    key, _ = store.resolve_key(entry)
    preset = entry.preset_obj
    if (preset.needs_key if preset else True) and not key:
        return None, f"{entry.name} 还没有 API key"
    model = target.model or (preset.default_model if preset else "") or (entry.models[0] if entry.models else "")
    if not model:
        return None, f"{entry.name} 还没选模型"
    if entry.protocol == "anthropic":
        from anima.llm.anthropic_provider import AnthropicProvider

        official = not entry.base_url or "api.anthropic.com" in entry.base_url
        provider: LLMProvider = AnthropicProvider(
            model, model, api_key=key, effort=cfg.effort, side_effort=cfg.side_effort, max_tokens=cfg.max_tokens,
            web_search=cfg.web_search and official, fallbacks=cfg.fallbacks and official, vision=cfg.vision,
            base_url=None if official else entry.base_url, label=entry.name,
        )
    else:
        from anima.llm.openai_compat import OpenAICompatProvider

        vision = model in entry.vision_models or bool(preset and model in preset.vision_models)
        provider = OpenAICompatProvider(
            model, model, base_url=entry.base_url, api_key=key, max_tokens=cfg.max_tokens,
            vision=vision and cfg.vision, params={**entry.chat_params(), **target.params}, label=entry.name,
        )
    provider.prices = entry.price_table()
    provider.provider_id = entry.id  # type: ignore[attr-defined]
    return provider, ""


def make_provider(bot: Bot, *, force_fake: bool = False, store: ProviderStore | None = None) -> LLMProvider:
    from anima.llm.fake import FakeLLM
    from anima.llm.router import RoutedLLM

    cfg = bot.config.llm
    if force_fake or cfg.provider == "fake":
        return FakeLLM()
    store = store or ProviderStore()
    routing = load_routing(bot)
    main, why = build_target(store, routing.main, cfg)
    if main is None:
        logger.warning("{}: {} runs in demo mode (canned replies) until this is fixed", why, bot.config.identity.name)
        demo = FakeLLM()
        demo.note = why  # type: ignore[attr-defined]
        return demo
    side = build_target(store, routing.side, cfg)[0] if routing.side else None
    backups = [p for p in (build_target(store, t, cfg)[0] for t in routing.backups) if p]
    return RoutedLLM(main, side or main, backups, routing.source)
