"""Run AstrBot plugins inside Anima.

AstrBot (github.com/AstrBotDevs/AstrBot) has a large plugin collection. This module provides the
parts of ``astrbot.api`` that plugins use most, mapped onto Anima:

=====================================  =============================================================
AstrBot                                Anima
=====================================  =============================================================
``@filter.command("x")`` / groups      ``/x args`` command; typed arguments are parsed from the text
``@filter.event_message_type(...)``    runs on every message; ``event.stop_event()`` hides it from her
``@filter.regex(...)``                 runs on messages matching the pattern
``@filter.llm_tool(name=...)``         becomes one of her tools (schema from the docstring ``Args:``)
``@filter.on_llm_request()``           text added to ``req.system_prompt`` reaches her scene
``@filter.permission_type(ADMIN)``     owner only
``yield event.plain_result(...)``      sent as-is (text, images, @, faces)
``yield event.request_llm(prompt)``    she answers in character with that prompt as the cue
``self.context.get_using_provider()``  her background model (``text_chat`` → ``completion_text``)
``self.context.send_message(umo, …)``  send to a chat by its key
=====================================  =============================================================

Platform internals (``event.bot.api.call_action``, AstrBot's database, its web dashboard) are not
emulated; a plugin that needs them fails to load with an explanation instead of half-working.
"""

from __future__ import annotations

import asyncio
import enum
import hashlib
import importlib.util
import inspect
import json
import re
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from anima.core.events import Bubble, Chat, Incoming, Reply, Segment, Sender
from anima.plugin import Plugin, PluginContext
from anima.skills.base import Skill

if TYPE_CHECKING:
    from anima.core.brain import Brain
    from anima.plugin_host import PluginInfo


# ---------------------------------------------------------------- message components


class BaseComponent:
    type = "Unknown"

    def toDict(self) -> dict[str, Any]:  # noqa: N802 - AstrBot's name
        return {"type": self.type, "data": {k: v for k, v in self.__dict__.items()}}


class Plain(BaseComponent):
    type = "Plain"

    def __init__(self, text: str = "", convert: bool = True, **_: Any):
        self.text = str(text)


class Image(BaseComponent):
    type = "Image"

    def __init__(self, file: str = "", url: str = "", path: str = "", **_: Any):
        self.file, self.url, self.path = file, url, path

    @staticmethod
    def fromURL(url: str, **_: Any) -> Image:  # noqa: N802
        return Image(file=url, url=url)

    @staticmethod
    def fromFileSystem(path: str, **_: Any) -> Image:  # noqa: N802
        return Image(file=f"file:///{path}", path=str(path))

    @staticmethod
    def fromBase64(data: str, **_: Any) -> Image:  # noqa: N802
        return Image(file=f"base64://{data}")

    @staticmethod
    def fromBytes(data: bytes, **_: Any) -> Image:  # noqa: N802
        import base64

        return Image(file=f"base64://{base64.b64encode(data).decode()}")


class At(BaseComponent):
    type = "At"

    def __init__(self, qq: Any = "", name: str = "", **_: Any):
        self.qq, self.name = str(qq), name


class AtAll(At):
    def __init__(self, **_: Any):
        super().__init__("all", "全体成员")


class Face(BaseComponent):
    type = "Face"

    def __init__(self, id: Any = 0, **_: Any):  # noqa: A002
        self.id = int(id)


class Reply_(BaseComponent):
    type = "Reply"

    def __init__(self, id: Any = "", **_: Any):  # noqa: A002
        self.id = str(id)


class Record(BaseComponent):
    type = "Record"

    def __init__(self, file: str = "", url: str = "", text: str = "", **_: Any):
        self.file, self.url, self.text = file, url, text

    @staticmethod
    def fromFileSystem(path: str, **_: Any) -> Record:  # noqa: N802
        return Record(file=str(path))

    @staticmethod
    def fromURL(url: str, **_: Any) -> Record:  # noqa: N802
        return Record(file=url, url=url)


class Node(BaseComponent):
    type = "Node"

    def __init__(self, content: list | None = None, name: str = "", uin: Any = "", **_: Any):
        self.content, self.name, self.uin = list(content or []), name, str(uin)


class Nodes(BaseComponent):
    type = "Nodes"

    def __init__(self, nodes: list | None = None, **_: Any):
        self.nodes = list(nodes or [])


def _flatten(chain: list) -> list:
    out = []
    for comp in chain or []:
        if isinstance(comp, Nodes):
            for node in comp.nodes:
                out += _flatten(node.content)
        elif isinstance(comp, Node):
            out += _flatten(comp.content)
        elif isinstance(comp, str):
            out.append(Plain(comp))
        else:
            out.append(comp)
    return out


# ---------------------------------------------------------------- results and events


class MessageChain:
    def __init__(self, chain: list | None = None):
        self.chain = list(chain or [])
        self.use_t2i_ = None

    def message(self, text: str) -> MessageChain:
        self.chain.append(Plain(text))
        return self

    def url_image(self, url: str) -> MessageChain:
        self.chain.append(Image.fromURL(url))
        return self

    def file_image(self, path: str) -> MessageChain:
        self.chain.append(Image.fromFileSystem(path))
        return self

    def base64_image(self, data: str) -> MessageChain:
        self.chain.append(Image.fromBase64(data))
        return self

    def at(self, name: str, qq: Any) -> MessageChain:
        self.chain.append(At(qq=qq, name=name))
        return self

    def use_t2i(self, use: bool) -> MessageChain:
        self.use_t2i_ = use
        return self

    def get_plain_text(self) -> str:
        return " ".join(c.text for c in _flatten(self.chain) if isinstance(c, Plain))

    def squash_plain(self):
        return self


class MessageEventResult(MessageChain):
    def __init__(self, chain: list | None = None):
        super().__init__(chain)
        self._stop = False

    def stop_event(self) -> MessageEventResult:
        self._stop = True
        return self

    def continue_event(self) -> MessageEventResult:
        self._stop = False
        return self

    def set_result_content_type(self, *_: Any) -> MessageEventResult:
        return self


CommandResult = MessageEventResult


class LLMRequest:
    """``yield event.request_llm(...)``: she answers in character with this as the cue."""

    def __init__(self, prompt: str = "", system_prompt: str = "", contexts: list | None = None,
                 image_urls: list | None = None, **_: Any):
        self.prompt, self.system_prompt = prompt, system_prompt
        self.contexts, self.image_urls = list(contexts or []), list(image_urls or [])
        self.func_tool = None


ProviderRequest = LLMRequest


class LLMResponse:
    def __init__(self, text: str):
        self.completion_text = text
        self.role = "assistant"
        self.result_chain = MessageChain([Plain(text)])


class MessageType(enum.Enum):
    GROUP_MESSAGE = "GroupMessage"
    FRIEND_MESSAGE = "FriendMessage"
    OTHER_MESSAGE = "OtherMessage"


class AstrMessageEvent:
    def __init__(self, ev: Incoming, brain: Brain):
        self._ev, self._brain = ev, brain
        self.message_str = ev.text.strip()
        self.unified_msg_origin = ev.chat.key
        self.session_id = ev.chat.id
        self.platform_meta = types.SimpleNamespace(name=ev.chat.platform, id=ev.chat.platform)
        sender = types.SimpleNamespace(user_id=ev.sender.id, nickname=ev.sender.name)
        self.message_obj = types.SimpleNamespace(
            message=[Plain(ev.text)], message_str=ev.text, sender=sender, message_id=ev.message_id or "",
            group_id=ev.chat.id if ev.chat.kind != "private" else "", self_id="", raw_message=ev.meta,
            timestamp=int(ev.timestamp), session_id=ev.chat.id,
            type=MessageType.FRIEND_MESSAGE if ev.chat.kind == "private" else MessageType.GROUP_MESSAGE,
        )
        self.is_at_or_wake_command = ev.mentions_me or ev.text.startswith("/")
        self.is_wake = self.is_at_or_wake_command
        self.role = "admin" if brain.admin.is_owner(ev) else "member"
        self._result: MessageEventResult | None = None
        self._stopped = False
        self._extras: dict[str, Any] = {}
        self.call_llm = True

    # who and where
    def get_sender_name(self) -> str:
        return self._ev.sender.name

    def get_sender_id(self) -> str:
        return self._ev.sender.id

    def get_group_id(self) -> str:
        return self._ev.chat.id if self._ev.chat.kind != "private" else ""

    def get_self_id(self) -> str:
        return ""

    def get_platform_name(self) -> str:
        return {"qq": "aiocqhttp"}.get(self._ev.chat.platform, self._ev.chat.platform)

    def get_message_type(self) -> MessageType:
        return self.message_obj.type

    def is_private_chat(self) -> bool:
        return self._ev.chat.kind == "private"

    def is_admin(self) -> bool:
        return self.role == "admin"

    def get_message_str(self) -> str:
        return self.message_str

    def get_message_outline(self) -> str:
        return self.message_str

    def get_messages(self) -> list:
        return list(self.message_obj.message)

    def get_extra(self, key: str | None = None, default: Any = None) -> Any:
        return self._extras if key is None else self._extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    # results
    def make_result(self) -> MessageEventResult:
        return MessageEventResult()

    def plain_result(self, text: str) -> MessageEventResult:
        return MessageEventResult([Plain(text)])

    def image_result(self, url_or_path: str) -> MessageEventResult:
        is_url = str(url_or_path).startswith(("http://", "https://"))
        return MessageEventResult([Image.fromURL(url_or_path) if is_url else Image.fromFileSystem(url_or_path)])

    def chain_result(self, chain: list) -> MessageEventResult:
        return MessageEventResult(list(chain))

    def set_result(self, result: MessageEventResult | str) -> None:
        self._result = result if isinstance(result, MessageEventResult) else self.plain_result(str(result))

    def get_result(self) -> MessageEventResult | None:
        return self._result

    def clear_result(self) -> None:
        self._result = None

    def stop_event(self) -> None:
        self._stopped = True

    def continue_event(self) -> None:
        self._stopped = False

    def is_stopped(self) -> bool:
        return self._stopped

    def should_call_llm(self, call: bool) -> None:
        self.call_llm = call

    def request_llm(self, prompt: str, func_tool_manager: Any = None, session_id: str = "", contexts: list | None = None,
                    system_prompt: str = "", image_urls: list | None = None, conversation: Any = None) -> LLMRequest:
        return LLMRequest(prompt, system_prompt, contexts, image_urls)

    async def send(self, message: MessageChain | MessageEventResult | str) -> None:
        await send_chain(self._brain, self._ev.chat, message)


async def send_chain(brain: Brain, chat: Chat, message: Any) -> None:
    """Turn an AstrBot message chain into one bubble and deliver it."""
    chain = message.chain if isinstance(message, MessageChain) else [Plain(str(message))]
    segments: list[Segment] = []
    for comp in _flatten(chain):
        if isinstance(comp, Plain) and comp.text:
            segments.append(Segment("text", comp.text))
        elif isinstance(comp, At):
            segments.append(Segment("text", f"@{comp.name or comp.qq} "))
        elif isinstance(comp, Face):
            segments.append(Segment("text", "[表情]"))
        elif isinstance(comp, Image):
            path = await _image_path(brain, comp)
            if path:
                segments.append(Segment("image", path.name, str(path)))
        elif isinstance(comp, Record) and comp.text:
            segments.append(Segment("text", comp.text))
    if segments:
        text = "".join(s.value for s in segments if s.type == "text") or "[图片]"
        await brain.deliver(chat, Reply(bubbles=[Bubble(segments, source=text)]))


async def _image_path(brain: Brain, img: Image) -> Path | None:
    ref = img.path or img.url or img.file
    if not ref:
        return None
    ref = ref.removeprefix("file://")
    cache = brain.bot.data_dir / "plugins" / "_images"
    cache.mkdir(parents=True, exist_ok=True)
    if ref.startswith("base64://"):
        import base64

        data = base64.b64decode(ref.removeprefix("base64://"))
        path = cache / f"{hashlib.sha1(data).hexdigest()[:16]}.png"
        path.write_bytes(data)
        return path
    if ref.startswith(("http://", "https://")):
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(ref)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[astrbot] image download failed: {}", exc)
            return None
        ext = {"image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(resp.headers.get("content-type", ""), ".png")
        path = cache / f"{hashlib.sha1(ref.encode()).hexdigest()[:16]}{ext}"
        path.write_bytes(resp.content)
        return path
    path = Path(ref)
    return path if path.exists() else None


# ---------------------------------------------------------------- filters (decorators)


class EventMessageType(enum.Enum):
    ALL = "all"
    GROUP_MESSAGE = "group"
    PRIVATE_MESSAGE = "private"
    OTHER_MESSAGE = "other"


class PermissionType(enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"


class PlatformAdapterType(enum.Flag):
    AIOCQHTTP = enum.auto()
    QQOFFICIAL = enum.auto()
    TELEGRAM = enum.auto()
    WECOM = enum.auto()
    LARK = enum.auto()
    WECHATPADPRO = enum.auto()
    DINGTALK = enum.auto()
    DISCORD = enum.auto()
    SLACK = enum.auto()
    KOOK = enum.auto()
    VOCECHAT = enum.auto()
    WEIXIN_OFFICIAL_ACCOUNT = enum.auto()
    SATORI = enum.auto()
    MISSKEY = enum.auto()
    ALL = AIOCQHTTP | QQOFFICIAL | TELEGRAM | WECOM | LARK | WECHATPADPRO | DINGTALK | DISCORD | SLACK | KOOK | VOCECHAT | WEIXIN_OFFICIAL_ACCOUNT | SATORI | MISSKEY


def _mark(fn, **info):
    marks = getattr(fn, "__anima_astrbot__", None)
    if marks is None:
        marks = []
        try:
            fn.__anima_astrbot__ = marks
        except AttributeError:
            return fn
    marks.append(info)
    return fn


class _CommandGroup:
    def __init__(self, name: str, parent: _CommandGroup | None = None):
        self.full = f"{parent.full} {name}" if parent else name

    def __call__(self, fn):
        return _mark(fn, kind="group", name=self.full)

    def command(self, name: str, alias: set | None = None, **_: Any):
        return lambda fn: _mark(fn, kind="command", name=f"{self.full} {name}", alias=[f"{self.full} {a}" for a in alias or ()])

    def group(self, name: str, **_: Any) -> _CommandGroup:
        return _CommandGroup(name, self)

    command_group = group


def _filter_module() -> types.ModuleType:
    f = types.ModuleType("astrbot.api.event.filter")
    f.EventMessageType, f.PermissionType, f.PlatformAdapterType = EventMessageType, PermissionType, PlatformAdapterType

    def command(name: str, alias: set | None = None, priority: int = 0, **_: Any):
        return lambda fn: _mark(fn, kind="command", name=name, alias=list(alias or ()))

    def command_group(name: str, alias: set | None = None, **_: Any):
        group = _CommandGroup(name)

        def decorator(fn):
            _mark(fn, kind="group", name=name)
            fn.command = group.command
            fn.group = fn.command_group = group.group
            return fn
        return decorator

    f.command, f.command_group = command, command_group
    f.event_message_type = lambda t, **_: (lambda fn: _mark(fn, kind="listen", type=t))
    f.platform_adapter_type = lambda t, **_: (lambda fn: fn)
    f.regex = lambda pattern, **_: (lambda fn: _mark(fn, kind="regex", pattern=pattern))
    f.permission_type = lambda p, **_: (lambda fn: _mark(fn, kind="permission", level=p))
    f.llm_tool = lambda name=None, **_: (lambda fn: _mark(fn, kind="tool", name=name or fn.__name__))
    f.on_llm_request = lambda **_: (lambda fn: _mark(fn, kind="llm_request"))
    f.on_llm_response = lambda **_: (lambda fn: _mark(fn, kind="ignored"))
    f.on_decorating_result = lambda **_: (lambda fn: _mark(fn, kind="ignored"))
    f.after_message_sent = lambda **_: (lambda fn: _mark(fn, kind="ignored"))
    f.on_astrbot_loaded = lambda **_: (lambda fn: _mark(fn, kind="loaded"))
    f.on_platform_loaded = lambda **_: (lambda fn: _mark(fn, kind="loaded"))
    f.custom_filter = lambda *a, **k: (lambda fn: fn)
    return f


# ---------------------------------------------------------------- Star, Context, register


_REGISTERED: list[tuple[type, dict[str, Any]]] = []


def register(name: str = "", author: str = "", desc: str = "", version: str = "", repo: str = "", **_: Any):
    def decorator(cls):
        _REGISTERED.append((cls, {"name": name, "author": author, "desc": desc, "version": version, "repo": repo}))
        return cls
    return decorator


class AstrBotConfig(dict):
    def __init__(self, data: dict[str, Any], path: Path):
        super().__init__(data)
        self._path = path

    def save_config(self, replace_config: dict | None = None) -> None:
        if replace_config is not None:
            self.clear()
            self.update(replace_config)
        self._path.write_text(json.dumps(dict(self), ensure_ascii=False, indent=2), encoding="utf-8")


class _Provider:
    def __init__(self, brain: Brain):
        self._brain = brain

    def meta(self):
        return types.SimpleNamespace(id=self._brain.llm.name, model=self._brain.llm.model, type="anima")

    def get_model(self) -> str:
        return self._brain.llm.model

    async def text_chat(self, prompt: str = "", session_id: str | None = None, image_urls: list | None = None,
                        func_tool: Any = None, contexts: list | None = None, system_prompt: str = "", **_: Any) -> LLMResponse:
        history = "\n".join(f"{c.get('role')}: {c.get('content')}" for c in contexts or [] if isinstance(c, dict))
        result = await self._brain.llm.complete(system_prompt or "You are a helpful assistant.",
                                                f"{history}\n{prompt}".strip())
        self._brain.account(result)
        return LLMResponse(result.text)


class Context:
    def __init__(self, brain: Brain, info: PluginInfo, config: dict[str, Any]):
        self._brain, self._info, self._config = brain, info, config

    def get_config(self, umo: str | None = None) -> dict[str, Any]:
        return {"provider_settings": {"wake_prefix": "/"}, "wake_prefix": ["/"], "admins_id": list(self._brain.cfg.owners)}

    def get_using_provider(self, umo: str | None = None) -> _Provider:
        return _Provider(self._brain)

    def get_provider_by_id(self, *_: Any) -> _Provider:
        return _Provider(self._brain)

    def get_all_providers(self) -> list[_Provider]:
        return [_Provider(self._brain)]

    async def send_message(self, session: str, message_chain: MessageChain) -> bool:
        platform, kind, chat_id = (session.split(":", 2) + ["", ""])[:3]
        kind = {"GroupMessage": "group", "FriendMessage": "private"}.get(kind, kind)
        await send_chain(self._brain, Chat(platform or "qq", kind or "private", chat_id), message_chain)  # type: ignore[arg-type]
        return True

    def register_task(self, coro, desc: str = "") -> asyncio.Task:
        return self._brain.spawn(coro)

    def get_platform(self, *_: Any) -> None:
        return None

    def get_registered_star(self, name: str) -> Any:
        return None

    def get_all_stars(self) -> list:
        return []


class Star:
    def __init__(self, context: Context, config: Any = None, *_: Any, **__: Any):
        self.context = context
        if config is not None:
            self.config = config

    async def initialize(self) -> None: ...

    async def terminate(self) -> None: ...


class StarTools:
    data_dir: Path | None = None

    @classmethod
    def get_data_dir(cls, plugin_name: str | None = None) -> Path:
        assert cls.data_dir is not None
        return cls.data_dir


# ---------------------------------------------------------------- the fake astrbot package


def install_shim() -> None:
    """Make ``import astrbot.api…`` resolve to this layer (only if the real AstrBot isn't installed)."""
    if "astrbot" in sys.modules:
        return  # already the shim, or the real AstrBot
    if importlib.util.find_spec("astrbot") is not None:
        return

    def module(name: str, **attrs: Any) -> types.ModuleType:
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        mod.__anima_shim__ = True
        mod.__path__ = []  # a package, so submodules import
        sys.modules[name] = mod
        return mod

    comps = dict(BaseMessageComponent=BaseComponent, Plain=Plain, Image=Image, At=At, AtAll=AtAll, Face=Face,
                 Reply=Reply_, Record=Record, Node=Node, Nodes=Nodes, ComponentType=types.SimpleNamespace())
    filt = _filter_module()
    filt.__anima_shim__ = True
    sys.modules["astrbot.api.event.filter"] = filt
    event = dict(AstrMessageEvent=AstrMessageEvent, MessageEventResult=MessageEventResult, MessageChain=MessageChain,
                 CommandResult=CommandResult, EventResultType=types.SimpleNamespace(CONTINUE=0, STOP=1), filter=filt)
    star = dict(Context=Context, Star=Star, register=register, StarTools=StarTools)
    provider = dict(ProviderRequest=ProviderRequest, LLMResponse=LLMResponse, Provider=_Provider)
    platform = dict(MessageType=MessageType, AstrBotMessage=types.SimpleNamespace, MessageMember=types.SimpleNamespace,
                    PlatformMetadata=types.SimpleNamespace, AiocqhttpAdapter=object)
    api = dict(logger=logger, AstrBotConfig=AstrBotConfig, llm_tool=filt.llm_tool, sp=types.SimpleNamespace(
        get=lambda *a, **k: k.get("default"), put=lambda *a, **k: None))
    module("astrbot")
    module("astrbot.api", **api, message_components=None)
    module("astrbot.api.event", **event)
    module("astrbot.api.star", **star)
    module("astrbot.api.message_components", **comps)
    module("astrbot.api.provider", **provider)
    module("astrbot.api.platform", **platform)
    module("astrbot.api.all", **{**api, **event, **star, **comps, **provider, **platform})
    sys.modules["astrbot.api"].message_components = sys.modules["astrbot.api.message_components"]
    sys.modules["astrbot.api"].event = sys.modules["astrbot.api.event"]
    sys.modules["astrbot.api"].star = sys.modules["astrbot.api.star"]
    module("astrbot.core", logger=logger)
    module("astrbot.core.message", components=sys.modules["astrbot.api.message_components"])
    sys.modules["astrbot.core.message.components"] = sys.modules["astrbot.api.message_components"]
    module("astrbot.core.message.message_event_result", MessageChain=MessageChain, MessageEventResult=MessageEventResult)
    module("astrbot.core.star", Context=Context, Star=Star, register=register, StarTools=StarTools)
    module("astrbot.core.utils")
    module("astrbot.core.utils.astrbot_path", get_astrbot_data_path=lambda: str(StarTools.data_dir or "."))
    module("astrbot.core.config", AstrBotConfig=AstrBotConfig)
    module("astrbot.core.config.astrbot_config", AstrBotConfig=AstrBotConfig)


# ---------------------------------------------------------------- loading a plugin


def _tool_schema(fn) -> tuple[str, dict[str, Any]]:
    """Description and JSON schema from an AstrBot tool docstring (``Args:`` with ``name(type): text``)."""
    doc = inspect.getdoc(fn) or ""
    desc, _, args_part = doc.partition("Args:")
    props: dict[str, Any] = {}
    for m in re.finditer(r"^\s*(\w+)\s*\((\w+)\)\s*:\s*(.+)$", args_part, re.M):
        name, kind, text = m.groups()
        kind = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array",
                "dict": "object"}.get(kind.lower(), kind.lower())
        props[name] = {"type": kind if kind in ("string", "integer", "number", "boolean", "array", "object") else "string",
                       "description": text.strip()}
    sig = inspect.signature(fn)
    params = [p for p in list(sig.parameters.values())[1:] if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    for p in params:
        props.setdefault(p.name, {"type": "string"})
    required = [p.name for p in params if p.default is inspect.Parameter.empty]
    return desc.strip() or fn.__name__, {"type": "object", "properties": props, "required": required}


def _coerce(value: str, annotation: Any) -> Any:
    if annotation in (int, "int"):
        return int(value)
    if annotation in (float, "float"):
        return float(value)
    if annotation in (bool, "bool"):
        return value.lower() in ("1", "true", "yes", "on", "是", "开")
    return value


def _bind_args(fn, arg: str) -> list[Any]:
    """Command arguments from the text after the command, typed by the handler's annotations."""
    params = [p for p in list(inspect.signature(fn).parameters.values())[1:]
              if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    tokens = arg.split()
    out: list[Any] = []
    for i, p in enumerate(params):
        if i >= len(tokens):
            if p.default is inspect.Parameter.empty:
                raise ValueError(f"少了参数 {p.name}")
            out.append(p.default)
            continue
        value = " ".join(tokens[i:]) if i == len(params) - 1 and p.annotation in (str, "str", inspect.Parameter.empty) else tokens[i]
        out.append(_coerce(value, p.annotation))
    return out


async def _drain(result) -> list[Any]:
    """Everything a handler produced: yielded items from an async generator, or its return value."""
    if inspect.isasyncgen(result):
        return [item async for item in result]
    if inspect.isawaitable(result):
        result = await result
    if inspect.isgenerator(result):
        return list(result)
    return [] if result is None else [result]


class _Runner:
    """Delivers what an AstrBot handler yields."""

    def __init__(self, brain: Brain):
        self.brain = brain

    async def run(self, ev: Incoming, outputs: list[Any], event: AstrMessageEvent) -> None:
        for out in outputs:
            if isinstance(out, LLMRequest):
                note = out.prompt + (f"\n{out.system_prompt}" if out.system_prompt else "")
                await self.brain.speak(ev.chat, f"有人刚才说「{ev.text[:80]}」。{note}")
            elif isinstance(out, MessageChain):
                await send_chain(self.brain, ev.chat, out)
                if isinstance(out, MessageEventResult) and out._stop:
                    event.stop_event()
            elif isinstance(out, str) and out:
                await send_chain(self.brain, ev.chat, out)
        if event.get_result() is not None:
            await send_chain(self.brain, ev.chat, event.get_result())
            event.clear_result()


async def load_astrbot_plugin(info: PluginInfo, brain: Brain, config: dict[str, Any], data_dir: Path) -> Plugin:
    install_shim()
    StarTools.data_dir = data_dir
    _REGISTERED.clear()
    name = f"astrbot_plugin_{re.sub(r'[^a-zA-Z0-9_]', '_', info.id)}"
    spec = importlib.util.spec_from_file_location(name, info.path / "main.py", submodule_search_locations=[str(info.path)])
    if not spec or not spec.loader:
        raise ImportError("main.py 读不出来")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(info.path))  # plugins import their own helper modules by bare name
    try:
        spec.loader.exec_module(module)
    finally:
        if str(info.path) in sys.path:
            sys.path.remove(str(info.path))
    classes = [cls for cls, _ in _REGISTERED] or [v for v in vars(module).values()
                                                  if inspect.isclass(v) and issubclass(v, Star) and v is not Star]
    if not classes:
        raise TypeError("main.py 里没有 AstrBot 插件类（@register 或 Star 子类）")
    cls = classes[0]
    context = Context(brain, info, config)
    conf = AstrBotConfig(config, data_dir / "config.json")
    try:
        instance = cls(context, conf) if len(inspect.signature(cls.__init__).parameters) > 2 else cls(context)
    except TypeError:
        instance = cls(context)
    if not getattr(instance, "context", None):
        instance.context = context

    plugin = Plugin(info.id)
    runner = _Runner(brain)
    listeners: list[tuple[dict, Any]] = []
    llm_hooks: list[Any] = []
    for attr in dir(instance):
        method = getattr(instance, attr, None)
        marks = getattr(getattr(method, "__func__", method), "__anima_astrbot__", None)
        if not marks or not callable(method):
            continue
        owner_only = any(m["kind"] == "permission" and m["level"] == PermissionType.ADMIN for m in marks)
        for m in marks:
            if m["kind"] == "command":
                _add_command(plugin, m["name"], m.get("alias", []), method, owner_only, runner, brain)
            elif m["kind"] in ("listen", "regex"):
                listeners.append((m, method))
            elif m["kind"] == "tool":
                _add_tool(plugin, m["name"], method, runner, brain)
            elif m["kind"] == "llm_request":
                llm_hooks.append(method)
            elif m["kind"] == "loaded":
                plugin.hooks["start"].append(lambda ctx, _m=method: _drain(_call(_m)))

    if listeners:
        async def on_message(ctx: PluginContext, ev: Incoming):
            event = AstrMessageEvent(ev, brain)
            for mark, method in listeners:
                if mark["kind"] == "regex" and not re.search(mark["pattern"], ev.text):
                    continue
                kind = mark.get("type")
                if kind == EventMessageType.GROUP_MESSAGE and ev.chat.kind == "private":
                    continue
                if kind == EventMessageType.PRIVATE_MESSAGE and ev.chat.kind != "private":
                    continue
                await runner.run(ev, await _drain(method(event)), event)
                if event.is_stopped():
                    return False
            return None
        plugin.hooks["message"].append(on_message)

    if llm_hooks:
        async def on_scene(ctx: PluginContext, chat: Chat, batch: list[Incoming]):
            if not batch:
                return None
            event = AstrMessageEvent(batch[-1], brain)
            req = LLMRequest(prompt=batch[-1].text, system_prompt="")
            for method in llm_hooks:
                await _drain(method(event, req))
            return req.system_prompt.strip() or None
        plugin.hooks["scene"].append(on_scene)

    if hasattr(instance, "initialize"):
        plugin.hooks["start"].insert(0, lambda ctx: _drain(_call(instance.initialize)))
    if hasattr(instance, "terminate"):
        plugin.hooks["stop"].append(lambda ctx: _drain(_call(instance.terminate)))
    return plugin


def _call(method):
    try:
        return method()
    except TypeError:
        return None


def _add_command(plugin: Plugin, name: str, aliases: list[str], method, owner_only: bool, runner: _Runner, brain: Brain) -> None:
    async def handler(ctx: PluginContext, ev: Incoming, arg: str) -> str:
        event = AstrMessageEvent(ev, brain)
        try:
            args = _bind_args(method, arg)
        except ValueError as exc:
            return f"用法不对：{exc}"
        await runner.run(ev, await _drain(method(event, *args)), event)
        return ""

    doc = (inspect.getdoc(method) or "").splitlines()
    plugin.command(name, help=doc[0] if doc else "", aliases=tuple(aliases), owner_only=owner_only)(handler)


def _add_tool(plugin: Plugin, name: str, method, runner: _Runner, brain: Brain) -> None:
    description, schema = _tool_schema(method)

    async def handler(ctx, args: dict[str, Any]) -> str:
        ev = ctx.batch[-1] if ctx.batch else Incoming(ctx.chat, ctx.sender or Sender("?", "?"), "")
        event = AstrMessageEvent(ev, brain)
        outputs = await _drain(method(event, **args))
        texts, sent = [], False
        for out in outputs:
            if isinstance(out, str):
                texts.append(out)
            elif isinstance(out, MessageChain):
                plain = out.get_plain_text()
                if any(isinstance(c, Image) for c in _flatten(out.chain)):
                    await send_chain(brain, ev.chat, out)
                    sent = True
                elif plain:
                    texts.append(plain)
        if sent:
            texts.append("（图片已经直接发出去了）")
        return "\n".join(texts) or "完成"

    plugin.skills.append(Skill(re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64], f"[AstrBot 插件 {plugin.id}] {description}"[:900],
                               schema, handler))
