"""Finds, installs, loads and runs plugins for the active persona.

Plugins live in two places: ``plugins/`` in this repository (bundled, versioned with the code) and
``data/plugins/`` (installed from the market, not committed). A persona turns them on by id in her
bot.toml (``plugins = ["hitokoto"]``) and configures them under ``[plugin_config.<id>]``.

Two kinds load here:

- **Anima plugins**: ``plugin.toml`` + an entry file that builds an ``anima.plugin.Plugin``.
- **AstrBot plugins**: a folder with ``main.py`` (and usually ``metadata.yaml``) written for
  AstrBot. They run on a compatibility layer (``anima.compat.astrbot``): commands, message
  listeners, LLM tools and LLM-request hooks work; platform-specific internals may not.

MCP servers are handled next door in ``anima.plugins``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import time
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tomlkit
from loguru import logger

from anima import config
from anima.plugin import Plugin, PluginContext, ToolContext, call_safely
from anima.skills.base import Skill

if TYPE_CHECKING:
    from anima.core.brain import Brain
    from anima.core.events import Chat, Incoming, Reply

ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
INSTALL_LIMIT = 40 * 1024 * 1024


def bundled_dir() -> Path:
    return config.REPO_ROOT / "plugins"


def installed_dir() -> Path:
    return config.DATA_DIR / "plugins"


@dataclass
class PluginInfo:
    id: str
    path: Path
    kind: str  # anima | astrbot
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    homepage: str = ""
    license: str = ""
    entry: str = "main.py"
    requirements: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    source: str = "bundled"  # bundled | installed

    def to_dict(self) -> dict[str, Any]:
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items() if k != "path"}


def read_info(folder: Path, source: str = "installed") -> PluginInfo | None:
    """What a plugin folder is, from its manifest; None if it isn't one."""
    manifest = folder / "plugin.toml"
    if manifest.exists():
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        pid = str(data.get("id") or folder.name)
        return PluginInfo(pid, folder, "anima", data.get("name", pid), str(data.get("version", "")),
                          data.get("description", ""), data.get("author", ""), data.get("homepage", ""),
                          data.get("license", ""), data.get("entry", "main.py"), list(data.get("requirements", [])),
                          list(data.get("permissions", [])), dict(data.get("config", {})), source)
    if (folder / "main.py").exists() and ((folder / "metadata.yaml").exists() or "astrbot" in
                                          (folder / "main.py").read_text(encoding="utf-8", errors="ignore")):
        meta = _yaml_flat(folder / "metadata.yaml")
        pid = str(meta.get("name") or folder.name)
        schema = {}
        if (folder / "_conf_schema.json").exists():
            try:
                schema = json.loads((folder / "_conf_schema.json").read_text(encoding="utf-8"))
            except ValueError:
                schema = {}
        reqs = (folder / "requirements.txt").read_text(encoding="utf-8").split() if (folder / "requirements.txt").exists() else []
        return PluginInfo(pid, folder, "astrbot", meta.get("display_name") or pid, str(meta.get("version", "")),
                          meta.get("desc", "") or meta.get("description", ""), meta.get("author", ""),
                          meta.get("repo", ""), "", "main.py", [r for r in reqs if not r.startswith("#")], [],
                          {k: {"type": v.get("type", "string"), "default": v.get("default"),
                               "label": v.get("description", k)} for k, v in schema.items() if isinstance(v, dict)},
                          source)
    return None


def _yaml_flat(path: Path) -> dict[str, str]:
    """metadata.yaml is a handful of ``key: value`` lines; no need for a YAML library."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#", "-")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip().strip("'\"")
    return out


def discover() -> dict[str, PluginInfo]:
    found: dict[str, PluginInfo] = {}
    for root, source in ((bundled_dir(), "bundled"), (installed_dir(), "installed")):
        if not root.is_dir():
            continue
        for folder in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
            try:
                info = read_info(folder, source)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[plugins] {} unreadable: {}", folder, exc)
                continue
            if info:
                found[info.id] = info
    return found


@dataclass
class Loaded:
    info: PluginInfo
    plugin: Plugin
    ctx: PluginContext
    tasks: list[asyncio.Task] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)


class PluginHost:
    def __init__(self, brain: Brain):
        self.brain = brain
        self.loaded: dict[str, Loaded] = {}
        self.errors: dict[str, str] = {}

    # ------------------------------------------------------------ lifecycle

    def enabled_ids(self) -> list[str]:
        return list(self.brain.cfg.plugins)

    async def start(self) -> None:
        available = discover()
        for pid in self.enabled_ids():
            if pid in available:
                await self.load(available[pid])
            else:
                self.errors[pid] = "找不到这个插件（没安装，或者文件夹被删了）"

    async def stop(self) -> None:
        for pid in list(self.loaded):
            await self.unload(pid)

    def config_for(self, info: PluginInfo) -> dict[str, Any]:
        defaults = {k: (v.get("default") if isinstance(v, dict) else v) for k, v in info.config_schema.items()}
        return defaults | dict(self.brain.cfg.plugin_config.get(info.id, {}))

    async def load(self, info: PluginInfo) -> Loaded | None:
        await self.unload(info.id)
        self.errors.pop(info.id, None)
        data_dir = self.brain.bot.data_dir / "plugins" / info.id
        data_dir.mkdir(parents=True, exist_ok=True)
        try:
            if info.kind == "astrbot":
                from anima.compat.astrbot import load_astrbot_plugin

                plugin = await load_astrbot_plugin(info, self.brain, self.config_for(info), data_dir)
            else:
                plugin = _import_anima_plugin(info)
        except Exception as exc:  # noqa: BLE001 - shown in the console
            self.errors[info.id] = _explain(exc)
            logger.warning("[plugins] {} failed to load: {}", info.id, self.errors[info.id])
            return None
        plugin.id, plugin.manifest = info.id, info.to_dict()
        ctx = PluginContext(self.brain, plugin, self.config_for(info), data_dir)
        loaded = Loaded(info, plugin, ctx)
        self.loaded[info.id] = loaded
        loaded.skills = [_bound(skill, ctx) for skill in plugin.skills]
        names = {s.name for s in loaded.skills}
        self.brain.skills = [s for s in self.brain.skills if s.name not in names] + loaded.skills
        for fn in plugin.hooks["start"]:
            await call_safely(fn, ctx, label=f"{info.id}.start")
        for timer in plugin.timers:
            loaded.tasks.append(asyncio.create_task(self._tick(loaded, timer)))
        logger.info("[plugins] {} on ({} tools, {} commands)", info.id, len(plugin.skills), len(set(plugin.commands.values())))
        return loaded

    async def unload(self, pid: str) -> None:
        loaded = self.loaded.pop(pid, None)
        if not loaded:
            return
        for task in loaded.tasks:
            task.cancel()
        for fn in loaded.plugin.hooks["stop"]:
            await call_safely(fn, loaded.ctx, label=f"{pid}.stop")
        self.brain.skills = [s for s in self.brain.skills if not any(s is mine for mine in loaded.skills)]

    async def _tick(self, loaded: Loaded, timer) -> None:
        while True:
            await asyncio.sleep(timer.seconds)
            await call_safely(timer.handler, loaded.ctx, timeout=max(30.0, timer.seconds), label=f"{loaded.info.id}.every")

    # ------------------------------------------------------------ hooks

    async def message(self, ev: Incoming) -> bool:
        """False when a plugin swallowed the message (she never sees it)."""
        for pid, loaded in list(self.loaded.items()):
            for fn in loaded.plugin.hooks["message"]:
                if await call_safely(fn, loaded.ctx, ev, label=f"{pid}.on_message") is False:
                    self.brain.trace.emit("plugin", plugin=pid, action="swallowed", text=ev.text[:60])
                    return False
        return True

    async def scene(self, chat: Chat, batch: list[Incoming]) -> list[str]:
        notes: list[str] = []
        for pid, loaded in list(self.loaded.items()):
            for fn in loaded.plugin.hooks["scene"]:
                out = await call_safely(fn, loaded.ctx, chat, batch, timeout=8, label=f"{pid}.on_scene")
                if isinstance(out, str) and out.strip():
                    notes.append(out.strip())
                elif isinstance(out, list):
                    notes += [str(n).strip() for n in out if str(n).strip()]
        return notes

    async def reply(self, chat: Chat, reply: Reply) -> None:
        for pid, loaded in list(self.loaded.items()):
            for fn in loaded.plugin.hooks["reply"]:
                await call_safely(fn, loaded.ctx, chat, reply, timeout=8, label=f"{pid}.on_reply")

    def find_command(self, text: str):
        """(loaded, command, argument) for ``/name arg``, or None."""
        text = text.strip()
        if not text.startswith(("/", "／")):
            return None
        name, _, arg = text[1:].partition(" ")
        for loaded in self.loaded.values():
            cmd = loaded.plugin.commands.get(name)
            if cmd is None and " " in arg.strip():  # two-word commands from command groups: "/todo add …"
                sub, _, rest = arg.strip().partition(" ")
                cmd = loaded.plugin.commands.get(f"{name} {sub}")
                if cmd is not None:
                    arg = rest
            elif cmd is None and arg.strip():
                cmd = loaded.plugin.commands.get(f"{name} {arg.strip()}")
                if cmd is not None:
                    arg = ""
            if cmd is not None:
                return loaded, cmd, arg.strip()
        return None

    async def command(self, ev: Incoming, is_owner: bool) -> str | None:
        found = self.find_command(ev.text)
        if not found:
            return None
        loaded, cmd, arg = found
        if cmd.owner_only and not is_owner:
            return "这个命令只有主人能用"
        self.brain.trace.emit("plugin", plugin=loaded.info.id, action="command", text=cmd.name)
        out = await call_safely(cmd.handler, loaded.ctx, ev, arg, timeout=60, label=f"{loaded.info.id}/{cmd.name}")
        return out if isinstance(out, str) else ""

    def help(self) -> list[dict[str, str]]:
        out = []
        for pid, loaded in self.loaded.items():
            for cmd in dict.fromkeys(loaded.plugin.commands.values()):
                out.append({"plugin": pid, "command": f"/{cmd.name}", "help": cmd.help, "owner_only": cmd.owner_only})
        return out

    # ------------------------------------------------------------ console

    def status(self) -> list[dict[str, Any]]:
        enabled = set(self.enabled_ids())
        out = []
        for pid, info in discover().items():
            loaded = self.loaded.get(pid)
            out.append(info.to_dict() | {
                "enabled": pid in enabled,
                "status": "running" if loaded else ("error" if pid in self.errors else "off"),
                "error": self.errors.get(pid, ""),
                "tools": [s.name for s in loaded.skills] if loaded else [],
                "commands": sorted({f"/{c.name}" for c in loaded.plugin.commands.values()}) if loaded else [],
                "config": self.config_for(info),
            })
        return out

    def _edit_toml(self, change) -> None:
        path = self.brain.bot.dir / "bot.toml"
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
        change(doc)
        new_cfg = config.BotConfig.model_validate(doc.unwrap())
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        self.brain.cfg.plugins, self.brain.cfg.plugin_config = new_cfg.plugins, new_cfg.plugin_config

    async def enable(self, pid: str, on: bool = True) -> None:
        available = discover()
        if on and pid not in available:
            raise KeyError(pid)

        def change(doc):
            current = [p for p in (doc.get("plugins") or []) if p != pid]
            doc["plugins"] = current + ([pid] if on else [])

        self._edit_toml(change)
        if on:
            await self.load(available[pid])
        else:
            await self.unload(pid)
            self.errors.pop(pid, None)

    async def configure(self, pid: str, values: dict[str, Any]) -> None:
        def change(doc):
            if "plugin_config" not in doc:
                doc["plugin_config"] = tomlkit.table(is_super_table=True)
            table = tomlkit.table()
            for key, value in values.items():
                if value is not None:
                    table[key] = value
            doc["plugin_config"][pid] = table

        self._edit_toml(change)
        if pid in self.loaded:
            await self.load(self.loaded[pid].info)


def _bound(skill: Skill, ctx: PluginContext) -> Skill:
    """The skill as the brain calls it, handing the plugin its own context (settings, folder, chat)."""
    async def handler(skill_ctx, args):
        return await skill.handler(ToolContext(ctx, skill_ctx), args)

    return Skill(skill.name, skill.description, skill.parameters, handler, skill.platforms)


def _import_anima_plugin(info: PluginInfo) -> Plugin:
    entry = info.path / info.entry
    if not entry.exists():
        raise FileNotFoundError(f"{info.entry} 不在插件文件夹里")
    name = f"anima_plugin_{re.sub(r'[^a-zA-Z0-9_]', '_', info.id)}"
    spec = importlib.util.spec_from_file_location(name, entry, submodule_search_locations=[str(info.path)])
    if not spec or not spec.loader:
        raise ImportError(f"无法加载 {entry}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    plugin = getattr(module, "plugin", None) or next((v for v in vars(module).values() if isinstance(v, Plugin)), None)
    if not isinstance(plugin, Plugin):
        raise TypeError(f"{info.entry} 里没有 anima.plugin.Plugin 对象（约定叫 plugin）")
    return plugin


def _explain(exc: BaseException) -> str:
    if isinstance(exc, ModuleNotFoundError):
        return f"缺少依赖 {exc.name}：在插件页点「安装依赖」，或者这个插件用到了还不支持的接口"
    if isinstance(exc, ImportError):
        return f"兼容层还不支持它用到的东西：{exc}"
    return f"{type(exc).__name__}: {exc}"[:300]


# ---------------------------------------------------------------- installing


def _github_zip(url: str) -> tuple[str, str]:
    """(archive url, subfolder) for https://github.com/o/r[/tree/branch/sub/dir]."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?(?:/tree/([^/]+)(/.*)?)?/?$", url.strip())
    if not m:
        return url, ""
    owner, repo, branch, sub = m.groups()
    ref = f"refs/heads/{branch}" if branch else "HEAD"
    return f"https://github.com/{owner}/{repo}/archive/{ref}.zip", (sub or "").strip("/")


async def download(url: str) -> bytes:
    import httpx

    archive, _ = _github_zip(url)
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        resp = await client.get(archive)
        resp.raise_for_status()
        if len(resp.content) > INSTALL_LIMIT:
            raise ValueError("压缩包太大了")
        return resp.content


def install_zip(data: bytes, source: str = "", subdir: str = "", pid: str | None = None) -> PluginInfo:
    """Unpack a plugin archive into data/plugins/<id>. Paths are checked; nothing runs yet."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "x"
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ValueError("不是 zip 文件") from exc
        total = 0
        for item in zf.infolist():
            rel = Path(item.filename)
            if rel.is_absolute() or ".." in rel.parts:
                continue
            total += item.file_size
            if total > INSTALL_LIMIT * 3:
                raise ValueError("解压后太大了")
            out = root / rel
            if item.is_dir():
                out.mkdir(parents=True, exist_ok=True)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(zf.read(item))
        base = root
        entries = [p for p in root.iterdir()] if root.exists() else []
        if len(entries) == 1 and entries[0].is_dir():
            base = entries[0]  # GitHub archives wrap everything in repo-branch/
        if subdir:
            base = base / subdir
        info = read_info(base) if base.is_dir() else None
        if info is None:
            candidates = [p.parent for p in base.rglob("plugin.toml")] + [p.parent for p in base.rglob("metadata.yaml")]
            info = next((i for i in (read_info(c) for c in candidates) if i), None)
        if info is None:
            raise ValueError("压缩包里找不到插件（plugin.toml，或 AstrBot 的 main.py + metadata.yaml）")
        pid = pid or info.id
        if not ID.match(pid):
            raise ValueError(f"插件 id 不合法：{pid}")
        target = installed_dir() / pid
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(info.path, target, ignore=shutil.ignore_patterns(".git", "__pycache__", ".github"))
        (target / ".anima-install.json").write_text(json.dumps({"source": source, "installed_at": time.time()},
                                                               ensure_ascii=False), encoding="utf-8")
        installed = read_info(target, "installed")
        assert installed is not None
        if installed.id != pid and info.kind == "anima":
            installed.id = pid
        return installed


async def install_from(url: str) -> PluginInfo:
    _, subdir = _github_zip(url)
    return install_zip(await download(url), source=url, subdir=subdir)


def uninstall(pid: str) -> None:
    target = installed_dir() / pid
    if not target.exists():
        raise FileNotFoundError("只能卸载从市场装的插件（自带的插件可以停用）")
    trash = config.DATA_DIR / "trash" / f"plugin-{pid}-{time.strftime('%Y%m%d-%H%M%S')}"
    trash.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), trash)


async def install_requirements(info: PluginInfo) -> str:
    """pip-install what a plugin declares, into Anima's own environment (uv if available)."""
    reqs = [r for r in info.requirements if r and not r.startswith(("-", "#"))]
    if not reqs:
        return "没有需要安装的依赖"
    uv = shutil.which("uv")
    cmd = [uv, "pip", "install", "--python", sys.executable, *reqs] if uv else [sys.executable, "-m", "pip", "install", *reqs]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
    text = out.decode("utf-8", errors="ignore")[-1500:]
    if proc.returncode != 0:
        raise RuntimeError(text)
    return text
