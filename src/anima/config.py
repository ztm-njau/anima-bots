"""Bot configuration.

A bot is a folder under ``bots/``: ``bot.toml`` holds behaviour, ``persona.md`` and
friends hold the soul. Secrets never live there; they come from the repo-root ``.env``.
"""

from __future__ import annotations

import json
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
    tagline: str = ""  # one line for the persona gallery
    avatar: str = ""  # an image in the bot folder, e.g. "avatar.png"
    color: str = ""  # accent colour for her avatar, e.g. "#b5482e"
    tags: list[str] = []
    author: str = ""


class LLMConfig(BaseModel):
    # A provider id from the panel or the preset catalog ("deepseek", "anthropic", "kimi", "ollama", ...),
    # "openai_compat" with base_url/api_key_env, or "fake". The panel's routing overrides this.
    provider: str = "deepseek"
    model: str = "deepseek-flash"
    side_model: str | None = None  # memory reflection, diary, daily plan; defaults to `model`
    backup: str | None = None  # "provider:model" tried when the main model errors
    temperature: float | None = None
    params: dict[str, Any] = {}  # extra request fields for OpenAI-compatible providers
    effort: str = "low"  # Claude only
    side_effort: str = "low"
    max_tokens: int = 4000
    web_search: bool = True  # Claude only
    fallbacks: bool = True  # Claude only: server-side refusal fallback
    vision: bool = True
    base_url: str | None = None  # provider = "openai_compat" only
    api_key_env: str | None = None


class BehaviorConfig(BaseModel):
    group_chattiness: float = 0.08
    interest_boost: float = 0.25
    cooldown_seconds: float = 90
    max_bubbles: int = 5
    debounce_private: float = 2.5  # how long she waits for someone to finish typing
    debounce_group: float = 4.0
    debounce_max: float = 12.0  # never wait longer than this after the first message
    debounce_unfinished: float = 2.5  # extra wait when the last message trails off ("然后，" "在吗")
    interrupt: bool = True  # rethink (or stop mid-reply) when the person adds something
    typing_cps: float = 6.0
    bubble_split: int = 36  # lines longer than this are cut at sentence breaks
    bubble_hard: int = 72  # and lines longer than this at commas too
    reply_budget: float = 24.0  # most seconds of typing one reply may take, all bubbles together
    group_max_bubbles: int = 3
    follow_up_seconds: float = 150  # someone she just answered keeps her attention this long
    interjections_per_hour: int = 4  # unprompted chime-ins per group
    repeat_chance: float = 0.3  # chance she joins a 复读 chain
    auto_quote: bool = True  # quote the message she answers once the group has moved on
    name_false_friends: list[str] = []  # words that contain her name but aren't about her, e.g. 喝可乐
    delays: bool = True
    history_limit: int = 40
    interests: list[str] = []
    caption_images: bool = True  # describe images once and keep the description in memory
    collect_stickers: float = 0.5  # chance she saves a sticker someone sent (0 = never)
    shared_stickers: bool = True  # also use the shared starter pack in bots/_template/memes
    sticker_cap: int = 600
    lore_budget: int = 1800  # characters of 世界书 per turn
    recall: bool = True  # bring up related old facts and moments


class ChatOverride(BaseModel):
    """Per-chat tuning in bot.toml: ``[chats."qq:group:123456"]``. Unset fields follow [behavior]."""

    mode: str = "normal"  # normal | quiet (only when spoken to) | lively
    chattiness: float | None = None
    debounce: float | None = None
    max_bubbles: int | None = None
    cooldown_seconds: float | None = None
    interjections_per_hour: int | None = None
    repeat_chance: float | None = None
    interests: list[str] | None = None  # replaces her usual interests here
    note: str = ""  # what she should know about this chat, e.g. "天文社的群，大家都叫她乐乐"


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
    owners: list[str] = []  # user keys like "qq:123456" who may use / commands
    identity: IdentityConfig = IdentityConfig()
    llm: LLMConfig = LLMConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    life: LifeConfig = LifeConfig()
    safety: SafetyConfig = SafetyConfig()
    skills: list[str] = ["*"]
    plugins: list[str] = []  # Anima plugins she uses (plugins/ and data/plugins/), by id
    plugin_config: dict[str, dict[str, Any]] = {}  # [plugin_config.<id>] settings for each plugin
    platforms: dict[str, PlatformConfig] = {}
    chats: dict[str, ChatOverride] = {}

    def platform(self, name: str) -> PlatformConfig:
        return self.platforms.get(name) or PlatformConfig()

    def behavior_for(self, chat_key: str) -> BehaviorConfig:
        """[behavior] with this chat's overrides applied."""
        o = self.chats.get(chat_key)
        if o is None:
            return self.behavior
        b, update = self.behavior, {}
        kind = chat_key.split(":")[1] if chat_key.count(":") >= 2 else ""
        if o.chattiness is not None:
            update["group_chattiness"] = o.chattiness
        if o.debounce is not None:
            update["debounce_private" if kind == "private" else "debounce_group"] = o.debounce
        if o.max_bubbles is not None:
            update["max_bubbles"] = update["group_max_bubbles"] = o.max_bubbles
        for name in ("cooldown_seconds", "interjections_per_hour", "repeat_chance", "interests"):
            if getattr(o, name) is not None:
                update[name] = getattr(o, name)
        if o.mode == "quiet":
            update |= {"group_chattiness": 0.0, "interest_boost": 0.0, "repeat_chance": 0.0, "interjections_per_hour": 0}
        elif o.mode == "lively":
            update["group_chattiness"] = min(0.6, update.get("group_chattiness", b.group_chattiness) * 2)
            update["interjections_per_hour"] = update.get("interjections_per_hour", b.interjections_per_hour) * 2
        return b.model_copy(update=update)


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

    def file(self, relative: str) -> Path:
        """Her own copy of a file, or the shared one in bots/_template (schedule, stickers, guard…)."""
        own = self.dir / relative
        return own if own.exists() else shared_dir() / relative

    def read(self, relative: str, default: str = "") -> str:
        path = self.file(relative)
        return path.read_text(encoding="utf-8") if path.exists() else default

    def read_toml(self, relative: str) -> dict[str, Any]:
        path = self.file(relative)
        if not path.exists():
            return {}
        with path.open("rb") as fh:
            return tomllib.load(fh)


def shared_dir() -> Path:
    return BOTS_DIR / "_template"


def list_bots() -> list[str]:
    return sorted(p.name for p in BOTS_DIR.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", ".")) and (p / "bot.toml").exists())


def _settings_path() -> Path:
    return DATA_DIR / "anima.json"


def app_settings() -> dict[str, Any]:
    try:
        return json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def default_bot() -> str:
    """The persona `anima play` starts when none is named: the last one chosen, else the first."""
    bots = list_bots()
    chosen = app_settings().get("default_bot")
    if chosen in bots:
        return chosen
    if not bots:
        raise FileNotFoundError(f"No bots in {BOTS_DIR}; create one with `uv run anima new <name>`")
    return bots[0]


def set_default_bot(key: str) -> None:
    settings = app_settings() | {"default_bot": key}
    _settings_path().parent.mkdir(parents=True, exist_ok=True)
    _settings_path().write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def load_bot(key: str) -> Bot:
    bot_dir = BOTS_DIR / key
    if not (bot_dir / "bot.toml").exists():
        raise FileNotFoundError(f"No bot named {key!r} (expected {bot_dir / 'bot.toml'})")
    with (bot_dir / "bot.toml").open("rb") as fh:
        raw = tomllib.load(fh)
    return Bot(key=key, dir=bot_dir, config=BotConfig.model_validate(raw))
