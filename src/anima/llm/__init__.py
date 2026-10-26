"""Language-model providers, and the factory that builds a bot's brain from its routing."""

from __future__ import annotations

from loguru import logger

from anima.config import Bot, LLMConfig
from anima.llm.base import LLMError, LLMProvider, LLMResult, ToolSpec, Turn, Usage
from anima.llm.catalog import GATEWAYS
from anima.llm.registry import ProviderEntry, ProviderStore, Target, gateway_models, load_routing, via_gateway

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
    if entry.preset in GATEWAYS and not key:
        key = "magpie"  # the gateway accepts any token from this computer
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

        provider = OpenAICompatProvider(
            model, model, base_url=entry.base_url, api_key=key, max_tokens=cfg.max_tokens,
            vision=entry.sees_images(model) and cfg.vision, params={**entry.chat_params(model), **target.params},
            label=entry.name,
        )
    provider.prices = entry.price_table([model])
    provider.provider_id = entry.id  # type: ignore[attr-defined]
    return provider, ""


def through_gateway(store: ProviderStore, target: Target, cfg: LLMConfig) -> tuple[LLMProvider | None, str]:
    """No key for a vendor? If a magpie gateway on this computer serves that vendor, use it there."""
    if target.provider in GATEWAYS:
        return None, ""
    gateway = store.entry_for("magpie")
    vendor = store.entry_for(target.provider)
    if gateway is None or vendor is None or not gateway.enabled:
        return None, ""
    key, _ = store.resolve_key(gateway)
    model = via_gateway(vendor.preset, target.model, gateway_models(gateway, key))
    if not model:
        return None, ""
    provider, _ = build_target(store, Target("magpie", model, target.params), cfg)
    if provider is not None:
        provider.label = f"{vendor.name}（经 magpie）"
    return provider, model


def make_provider(bot: Bot, *, force_fake: bool = False, store: ProviderStore | None = None) -> LLMProvider:
    from anima.llm.fake import FakeLLM
    from anima.llm.router import RoutedLLM

    cfg = bot.config.llm
    if force_fake or cfg.provider == "fake":
        return FakeLLM()
    store = store or ProviderStore()
    routing = load_routing(bot)
    main, why = build_target(store, routing.main, cfg)
    if main is None and "API key" in why:
        main, via = through_gateway(store, routing.main, cfg)
        if main is not None:
            logger.info("{}; using {} through the local magpie gateway instead", why, via)
    if main is None:
        logger.warning("{}: {} runs in demo mode (canned replies) until this is fixed", why, bot.config.identity.name)
        demo = FakeLLM()
        demo.note = why  # type: ignore[attr-defined]
        return demo
    side = None
    if routing.side:
        side = build_target(store, routing.side, cfg)[0] or through_gateway(store, routing.side, cfg)[0]
    backups = [p for p in (build_target(store, t, cfg)[0] for t in routing.backups) if p]
    return RoutedLLM(main, side or main, backups, routing.source)
