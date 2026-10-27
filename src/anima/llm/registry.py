"""Configured providers, environment detection, and per-bot routing.

- ``data/providers.json`` (gitignored, mode 600) holds the providers you connected in the panel:
  endpoint, models, params, and either a stored key or the name of an env var holding it.
- ``data/<bot>/routing.json`` says which provider/model a bot uses for chat, for background
  work (diary, plan, reflection), and as a backup. Without it, ``bot.toml`` [llm] decides.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values

import anima.config as config
from anima.config import REPO_ROOT, Bot
from anima.llm.catalog import GATEWAYS, PRESET_BY_ID, PRESETS, VENDOR_ALIASES, Preset, Price, vendor_of

_SLUG = re.compile(r"[^a-z0-9]+")


def mask(secret: str) -> str:
    if not secret:
        return ""
    return f"{secret[:3]}…{secret[-4:]}" if len(secret) > 10 else "…" + secret[-2:]


def env_lookup(name: str) -> str:
    """Process environment first, then the repo's .env (re-read, so edits apply without a restart)."""
    if not name:
        return ""
    if os.environ.get(name):
        return os.environ[name]
    path = REPO_ROOT / ".env"
    if path.exists():
        return dotenv_values(path).get(name) or ""
    return ""


# ------------------------------------------------------------------ configured providers


@dataclass
class ProviderEntry:
    id: str
    preset: str
    name: str
    protocol: str
    base_url: str
    api_key: str = ""
    api_key_env: str = ""
    models: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    prices: dict[str, dict[str, Any]] = field(default_factory=dict)
    vision_models: list[str] = field(default_factory=list)
    enabled: bool = True
    last_test: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    virtual: bool = False  # synthesized from a preset, not saved

    @property
    def preset_obj(self) -> Preset | None:
        return PRESET_BY_ID.get(self.preset)

    def price_table(self, extra_models: list[str] | None = None) -> dict[str, Price]:
        table = dict(self.preset_obj.prices) if self.preset_obj else {}
        for model in [*self.models, *(extra_models or [])]:  # "deepseek/deepseek-flash" costs what DeepSeek charges
            vendor, bare = vendor_of(model)
            if vendor and bare in vendor.prices and model not in table:
                table[model] = vendor.prices[bare]
        for model, data in self.prices.items():
            price = Price.from_dict(data)
            if price:
                table[model] = price
        return table

    def chat_params(self, model: str = "") -> dict[str, Any]:
        base = dict(self.preset_obj.params) if self.preset_obj else {}
        if self.preset in GATEWAYS and model:
            vendor, _ = vendor_of(model)  # through magpie, DeepSeek still wants its own settings
            base = dict(vendor.params) if vendor else base
        base.update(self.params)
        return base

    def sees_images(self, model: str) -> bool:
        if model in self.vision_models or (self.preset_obj and model in self.preset_obj.vision_models):
            return True
        vendor, bare = vendor_of(model)
        return bool(vendor and bare in vendor.vision_models)


class ProviderStore:
    def __init__(self, path: Path | None = None):
        self.path = path or config.DATA_DIR / "providers.json"
        self._entries: dict[str, ProviderEntry] = {}
        self.load()

    def load(self) -> None:
        self._entries = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            for raw in data.get("providers", []):
                raw = {k: v for k, v in raw.items() if k in ProviderEntry.__dataclass_fields__ and k != "virtual"}
                entry = ProviderEntry(**raw)
                self._entries[entry.id] = entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"providers": [{k: v for k, v in asdict(e).items() if k != "virtual"} for e in self._entries.values()]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def all(self) -> list[ProviderEntry]:
        return list(self._entries.values())

    def get(self, provider_id: str) -> ProviderEntry | None:
        return self._entries.get(provider_id)

    def entry_for(self, provider_id: str) -> ProviderEntry | None:
        """A saved provider, or a preset used as-is (key from its usual env vars)."""
        if provider_id in self._entries:
            return self._entries[provider_id]
        p = PRESET_BY_ID.get(provider_id)
        if not p:
            return None
        return ProviderEntry(p.id, p.id, p.name, p.protocol, p.base_url, models=list(p.models),
                             vision_models=list(p.vision_models), virtual=True)

    def _new_id(self, base: str) -> str:
        slug = _SLUG.sub("-", base.lower()).strip("-") or "provider"
        candidate, n = slug, 2
        while candidate in self._entries:
            candidate, n = f"{slug}-{n}", n + 1
        return candidate

    def upsert(self, data: dict[str, Any]) -> ProviderEntry:
        pid = data.get("id")
        entry = self._entries.get(pid) if pid else None
        preset = PRESET_BY_ID.get(data.get("preset") or (entry.preset if entry else "custom")) or PRESET_BY_ID["custom"]
        if entry is None:
            entry = ProviderEntry(
                id=self._new_id(pid or preset.id),
                preset=preset.id,
                name=preset.name,
                protocol=preset.protocol,
                base_url=preset.base_url,
                models=list(preset.models),
                vision_models=list(preset.vision_models),
            )
        for key in ("name", "protocol", "base_url", "api_key_env", "models", "params", "prices", "vision_models", "enabled"):
            if key in data and data[key] is not None:
                setattr(entry, key, data[key])
        if data.get("api_key"):  # blank means "keep the current key"
            entry.api_key = data["api_key"].strip()
        if data.get("clear_key"):
            entry.api_key = ""
        entry.base_url = entry.base_url.rstrip("/")
        entry.models = list(dict.fromkeys(m.strip() for m in entry.models if m and m.strip()))
        entry.virtual = False
        self._entries[entry.id] = entry
        self.save()
        return entry

    def delete(self, provider_id: str) -> bool:
        if self._entries.pop(provider_id, None) is None:
            return False
        self.save()
        return True

    def record_test(self, provider_id: str, result: dict[str, Any]) -> None:
        entry = self._entries.get(provider_id)
        if entry:
            entry.last_test = {**result, "at": time.time()}
            self.save()

    @staticmethod
    def resolve_key(entry: ProviderEntry) -> tuple[str, str]:
        """(key, where it came from). Stored key, then the entry's env var, then the preset's usual ones."""
        if entry.api_key:
            return entry.api_key, "已保存在面板"
        names = [entry.api_key_env] if entry.api_key_env else []
        if entry.preset_obj:
            names += entry.preset_obj.env_keys
        for name in names:
            value = env_lookup(name)
            if value:
                return value, f"环境变量 {name}"
        return "", ""

    def public(self, entry: ProviderEntry) -> dict[str, Any]:
        """Safe for the browser: never the key itself."""
        key, source = self.resolve_key(entry)
        preset = entry.preset_obj
        needs_key = preset.needs_key if preset else True
        return {
            "id": entry.id,
            "preset": entry.preset,
            "name": entry.name,
            "protocol": entry.protocol,
            "base_url": entry.base_url,
            "models": entry.models,
            "params": entry.params,
            "effective_params": entry.chat_params(),
            "prices": {m: p.to_dict() for m, p in entry.price_table().items()},
            "vision_models": entry.vision_models,
            "enabled": entry.enabled,
            "last_test": entry.last_test,
            "api_key_env": entry.api_key_env,
            "key_hint": mask(key),
            "key_source": source,
            "has_key": bool(key) or not needs_key,
            "needs_key": needs_key,
            "virtual": entry.virtual,
            "color": preset.color if preset else "#8A8F98",
            "initials": preset.initials if preset else entry.name[:2].upper(),
        }


# ------------------------------------------------------------------ detection


@dataclass
class Detection:
    id: str
    preset: str
    name: str
    source: str
    key_hint: str = ""
    models: list[str] = field(default_factory=list)
    spec: dict[str, Any] = field(default_factory=dict)  # what importing would save
    imported: bool = False


_ANTHROPIC_COMPAT = {  # Claude Code pointed at a vendor's Anthropic-compatible endpoint
    "deepseek.com": "deepseek",
    "moonshot.cn": "kimi",
    "bigmodel.cn": "zhipu",
    "dashscope.aliyuncs.com": "qwen",
    "minimax": "minimax",
}


async def detect(store: ProviderStore) -> list[Detection]:
    """Providers that are ready to use on this machine: keys in env vars / .env, local model servers."""
    found: list[Detection] = []
    known_sources = {(e.preset, e.api_key_env) for e in store.all()}
    for p in PRESETS:
        for name in p.env_keys:
            value = env_lookup(name)
            if value:
                found.append(Detection(f"env:{name}", p.id, p.name, f"环境变量 {name}", mask(value),
                                       spec={"preset": p.id, "api_key_env": name},
                                       imported=(p.id, name) in known_sources))
    base = env_lookup("ANTHROPIC_BASE_URL")
    token_var = next((n for n in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY") if env_lookup(n)), "")
    for host, preset_id in _ANTHROPIC_COMPAT.items():
        if host in base and token_var:
            p = PRESET_BY_ID[preset_id]
            found.append(Detection(f"env:{token_var}@{preset_id}", p.id, p.name,
                                   f"Claude Code 接入 {p.name} 的环境变量（{token_var}）", mask(env_lookup(token_var)),
                                   spec={"preset": p.id, "api_key_env": token_var},
                                   imported=(p.id, token_var) in known_sources))
    async with httpx.AsyncClient(timeout=0.8) as client:
        for preset_id in ("magpie", "ollama", "lmstudio"):
            p = PRESET_BY_ID[preset_id]
            token = "magpie"
            if preset_id == "magpie":  # the Docker build wants a real gateway key even from this computer
                saved = store.get("magpie")
                token = (store.resolve_key(saved)[0] if saved else "") or env_lookup("MAGPIE_GATEWAY_KEY") or token
            try:
                resp = await client.get(f"{p.base_url}/models", headers={"Authorization": f"Bearer {token}"})
                if preset_id == "magpie" and resp.status_code == 401:
                    found.append(Detection("local:magpie", p.id, p.name,
                                           "本机 magpie 网关（需要网关密钥：运行 uv run anima magpie connect）",
                                           spec={"preset": p.id}, imported=store.get("magpie") is not None))
                    continue
                resp.raise_for_status()
                models = sorted(m["id"] for m in resp.json().get("data", []) if not m["id"].startswith("text-embedding"))
            except (httpx.HTTPError, ValueError, KeyError):
                continue
            label = "本机 magpie 网关" if preset_id == "magpie" else f"本机 {p.name}"
            found.append(Detection(f"local:{preset_id}", p.id, p.name, f"{label}（{len(models)} 个模型）",
                                   models=models, spec={"preset": p.id, "models": models},
                                   imported=any(e.preset == preset_id for e in store.all())))
    return found


def gateway_models(entry: ProviderEntry, key: str = "", timeout: float = 0.6) -> list[str]:
    """Model ids a running gateway offers right now (empty if it isn't running)."""
    try:
        resp = httpx.get(f"{entry.base_url}/models", headers={"Authorization": f"Bearer {key or 'magpie'}"}, timeout=timeout)
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", [])]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def via_gateway(vendor_preset: str, model: str, models: list[str]) -> str:
    """Pick the gateway's id for a vendor model: "deepseek-flash" -> "deepseek/deepseek-flash"."""
    mine = [m for m in models if "/" in m and VENDOR_ALIASES.get(m.split("/", 1)[0].lower()) == vendor_preset]
    exact = [m for m in mine if m.split("/", 1)[1] == model]
    return (exact or mine or [""])[0]


# ------------------------------------------------------------------ routing


@dataclass
class Target:
    provider: str
    model: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: Any) -> Target | None:
        if not data:
            return None
        if isinstance(data, str):  # "provider:model"
            provider, _, model = data.partition(":")
            return cls(provider, model)
        return cls(data["provider"], data.get("model", ""), dict(data.get("params") or {}))


@dataclass
class Routing:
    main: Target
    side: Target | None = None
    backups: list[Target] = field(default_factory=list)
    source: str = "bot.toml"

    def to_dict(self) -> dict[str, Any]:
        return {
            "main": asdict(self.main),
            "side": asdict(self.side) if self.side else None,
            "backups": [asdict(b) for b in self.backups],
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: str = "panel") -> Routing:
        main = Target.parse(data["main"])
        assert main is not None
        return cls(main, Target.parse(data.get("side")), [t for t in map(Target.parse, data.get("backups") or []) if t], source)


def routing_path(bot: Bot) -> Path:
    return bot.data_dir / "routing.json"


def load_routing(bot: Bot) -> Routing:
    path = routing_path(bot)
    if path.exists():
        return Routing.from_dict(json.loads(path.read_text(encoding="utf-8")), "panel")
    cfg = bot.config.llm
    params: dict[str, Any] = dict(cfg.params)
    if cfg.temperature is not None:
        params["temperature"] = cfg.temperature
    main = Target(cfg.provider, cfg.model, params)
    side = Target(cfg.provider, cfg.side_model) if cfg.side_model else None
    backups = [t for t in [Target.parse(cfg.backup)] if t]
    return Routing(main, side, backups, "bot.toml")


def save_routing(bot: Bot, routing: Routing) -> None:
    data = routing.to_dict()
    data.pop("source", None)
    routing_path(bot).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_routing(bot: Bot) -> None:
    routing_path(bot).unlink(missing_ok=True)
