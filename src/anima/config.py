"""Bot configuration.

A bot is a folder under ``bots/``: ``bot.toml`` holds behaviour, ``persona.md`` and
friends hold the soul. Secrets never live there; they come from the repo-root ``.env``.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BOTS_DIR = REPO_ROOT / "bots"
DATA_DIR = REPO_ROOT / "data"

load_dotenv(REPO_ROOT / ".env", override=False)


def env(name: str | None, default: str | None = None) -> str | None:
    if not name:
        return default
    value = os.environ.get(name)
    return value if value else default


class IdentityConfig(BaseModel):
    name: str = "Bot"
    display_name: str = "Bot"
    aliases: list[str] = []
    timezone: str = "Asia/Shanghai"


class LLMConfig(BaseModel):
    provider: str = "anthropic"  # anthropic | openai_compat | fake
    model: str = "claude-opus-5-5"
    effort: str = "low"
    side_model: str | None = None  # memory reflection, diary, daily plan; defaults to `model`
    side_effort: str = "low"
    max_tokens: int = 4000
    web_search: bool = True
    fallbacks: bool = True  # server-side refusal fallback (Anthropic)
    vision: bool = True
    base_url: str | None = None  # openai_compat only
    api_key_env: str | None = None


class BehaviorConfig(BaseModel):
    group_chattiness: float = 0.08
    interest_boost: float = 0.25
    cooldown_seconds: float = 90
    max_bubbles: int = 5
    debounce_private: float = 2.5
    debounce_group: float = 4.0
    debounce_max: float = 12.0
    typing_cps: float = 6.0
    delays: bool = True
    history_limit: int = 40
    interests: list[str] = []


class LifeConfig(BaseModel):
    daily_plan: bool = True
    diary: bool = True
    diary_time: str = "23:20"
    insomnia_chance: float = 0.04
    greet_groups: list[str] = []  # chat keys, e.g. "qq:group:123456"
    idle_chatter: bool = True
    idle_chatter_hours: float = 3.0


class SafetyConfig(BaseModel):
    honest_about_ai: bool = True
    max_messages_per_minute: int = 12
    max_messages_per_chat_per_minute: int = 6


class PlatformConfig(BaseModel):
    """Common platform switch; each adapter validates its own extra keys."""

    model_config = ConfigDict(extra="allow")
    enabled: bool = False

    def extras(self) -> dict[str, Any]:
        return {"enabled": self.enabled, **(self.model_extra or {})}


class BotConfig(BaseModel):
    identity: IdentityConfig = IdentityConfig()
    llm: LLMConfig = LLMConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    life: LifeConfig = LifeConfig()
    safety: SafetyConfig = SafetyConfig()
    skills: list[str] = ["*"]
    platforms: dict[str, PlatformConfig] = {}

    def platform(self, name: str) -> PlatformConfig:
        return self.platforms.get(name) or PlatformConfig()


@dataclass
class Bot:
    key: str
    dir: Path
    config: BotConfig

    @property
    def data_dir(self) -> Path:
        path = DATA_DIR / self.key
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def secrets_dir(self) -> Path:
        path = self.data_dir / "secrets"
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
        return path

    def read(self, relative: str, default: str = "") -> str:
        path = self.dir / relative
        return path.read_text(encoding="utf-8") if path.exists() else default

    def read_toml(self, relative: str) -> dict[str, Any]:
        path = self.dir / relative
        if not path.exists():
            return {}
        with path.open("rb") as fh:
            return tomllib.load(fh)


def list_bots() -> list[str]:
    return sorted(p.name for p in BOTS_DIR.iterdir() if p.is_dir() and not p.name.startswith("_"))


def load_bot(key: str) -> Bot:
    bot_dir = BOTS_DIR / key
    if not (bot_dir / "bot.toml").exists():
        raise FileNotFoundError(f"No bot named {key!r} (expected {bot_dir / 'bot.toml'})")
    with (bot_dir / "bot.toml").open("rb") as fh:
        raw = tomllib.load(fh)
    return Bot(key=key, dir=bot_dir, config=BotConfig.model_validate(raw))
