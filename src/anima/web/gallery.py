"""HTTP API for the console's 人设 (personas) and 扩展 (plugins, MCP, market) pages."""

from __future__ import annotations

import base64
import random
from typing import TYPE_CHECKING, Any

import tomlkit
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, Response

from anima import config, market, personas, plugin_host
from anima.core.events import Chat, Incoming, Sender

if TYPE_CHECKING:
    from anima.runtime import Runtime

IDENTITY_FIELDS = ("display_name", "name", "aliases", "tagline", "tags", "color", "author")


def _bytes(body: dict[str, Any]) -> bytes:
    data = str(body.get("data") or "")
    if data.startswith("data:") and "," in data:
        data = data.split(",", 1)[1]
    try:
        return base64.b64decode(data)
    except ValueError as exc:
        raise HTTPException(400, "文件读不出来") from exc


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, FileExistsError):
        return HTTPException(409, str(exc))
    if isinstance(exc, (FileNotFoundError, KeyError)):
        return HTTPException(404, f"找不到：{exc}")
    return HTTPException(400, str(exc))


def gallery_router(runtime: Runtime) -> APIRouter:
    router = APIRouter(prefix="/api/console")

    # ------------------------------------------------------------ personas

    @router.get("/personas")
    async def list_personas() -> dict[str, Any]:
        return {"active": runtime.bot.key, "default": config.default_bot(), "personas": personas.list_personas()}

    @router.get("/personas/{key}/avatar")
    async def avatar(key: str):
        try:
            bot = config.load_bot(key)
        except FileNotFoundError as exc:
            raise _fail(exc) from exc
        name = bot.config.identity.avatar
        path = bot.dir / name if name else next(iter(sorted(bot.dir.glob("avatar.*"))), None)
        if not path or not path.exists() or not path.resolve().is_relative_to(bot.dir.resolve()):
            raise HTTPException(404, "没有头像")
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    @router.post("/personas")
    async def create(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            key = personas.create(body)
        except Exception as exc:  # noqa: BLE001
            raise _fail(exc) from exc
        return {"key": key, **(await list_personas())}

    @router.post("/personas/draft")
    async def draft(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        idea = str(body.get("idea") or "").strip()
        if not idea:
            raise HTTPException(400, "先写一句你想要的她")
        llm = runtime.brain.llm
        if getattr(llm, "demo", False):
            raise HTTPException(400, "还没接上模型，没法帮你起草。先去「模型」接一个，或者直接填表")
        try:
            return {"form": await personas.draft(idea, llm)}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"起草失败：{exc}") from exc

    @router.post("/personas/import")
    async def import_persona(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        data, name = _bytes(body), str(body.get("filename") or "")
        try:
            if data[:2] == b"PK":
                key = personas.import_pack(data)
            else:
                from anima.core.cards import create_bot_from_card

                key = create_bot_from_card(data).name
        except Exception as exc:  # noqa: BLE001
            raise _fail(exc) from exc
        return {"key": key, "from": name, **(await list_personas())}

    @router.post("/personas/install")
    async def install_persona(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            key = await personas.install(str(body.get("source") or ""))
        except Exception as exc:  # noqa: BLE001
            raise _fail(exc) from exc
        return {"key": key, "name": config.load_bot(key).config.identity.display_name, **(await list_personas())}

    @router.post("/personas/{key}/duplicate")
    async def duplicate(key: str) -> dict[str, Any]:
        try:
            new_key = personas.duplicate(key)
        except Exception as exc:  # noqa: BLE001
            raise _fail(exc) from exc
        return {"key": new_key, **(await list_personas())}

    @router.post("/personas/{key}/activate")
    async def activate(key: str) -> dict[str, Any]:
        if key not in config.list_bots():
            raise HTTPException(404, f"没有人设 {key}")
        try:
            await runtime.switch(key)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(409, str(exc)) from exc
        return {"active": runtime.bot.key, "name": runtime.bot.config.identity.display_name}

    @router.post("/personas/{key}/default")
    async def make_default(key: str) -> dict[str, Any]:
        if key not in config.list_bots():
            raise HTTPException(404, f"没有人设 {key}")
        config.set_default_bot(key)
        return await list_personas()

    @router.delete("/personas/{key}")
    async def retire(key: str) -> dict[str, Any]:
        if key == runtime.bot.key:
            raise HTTPException(409, "正在用的人设不能移走，先切换到别的")
        try:
            where = personas.retire(key)
        except Exception as exc:  # noqa: BLE001
            raise _fail(exc) from exc
        return {"moved_to": str(where.relative_to(config.REPO_ROOT)) if where.is_relative_to(config.REPO_ROOT) else str(where),
                **(await list_personas())}

    @router.get("/personas/{key}/export")
    async def export(key: str) -> Response:
        try:
            data = personas.export_pack(key)
        except Exception as exc:  # noqa: BLE001
            raise _fail(exc) from exc
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{key}.anima.zip"'})

    @router.get("/personas/{key}/files")
    async def files(key: str) -> dict[str, Any]:
        try:
            bot = config.load_bot(key)
        except FileNotFoundError as exc:
            raise _fail(exc) from exc
        ident = bot.config.identity
        return {"key": key, "identity": {f: getattr(ident, f) for f in IDENTITY_FIELDS},
                "persona": (bot.dir / "persona.md").read_text(encoding="utf-8") if (bot.dir / "persona.md").exists() else "",
                "examples": bot.read("examples.md"), "own_examples": (bot.dir / "examples.md").exists(),
                "interests": bot.config.behavior.interests}

    @router.put("/personas/{key}/files")
    async def save_files(key: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            bot = config.load_bot(key)
        except FileNotFoundError as exc:
            raise _fail(exc) from exc
        doc = tomlkit.parse((bot.dir / "bot.toml").read_text(encoding="utf-8"))
        for field, value in (body.get("identity") or {}).items():
            if field in IDENTITY_FIELDS and value is not None:
                doc["identity"][field] = value
        if isinstance(body.get("interests"), list):
            doc["behavior"]["interests"] = [str(i) for i in body["interests"] if str(i).strip()]
        new_cfg = config.BotConfig.model_validate(doc.unwrap())
        (bot.dir / "bot.toml").write_text(tomlkit.dumps(doc), encoding="utf-8")
        for name in ("persona", "examples"):
            if isinstance(body.get(name), str) and body[name].strip():
                (bot.dir / f"{name}.md").write_text(body[name], encoding="utf-8")
        if key == runtime.bot.key:  # the active persona: apply from her next message
            brain = runtime.brain
            brain.cfg.identity = new_cfg.identity
            brain.cfg.behavior.interests = new_cfg.behavior.interests
            brain.policy.interests = [i.lower() for i in new_cfg.behavior.interests if i]
            brain.policy.aliases = [a.lower() for a in brain.names]
            brain.prompt._system = None
        return await files(key)

    @router.post("/personas/{key}/preview")
    async def preview(key: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Try a persona on the current model without switching: scratch memory, nothing remembered."""
        from anima.core.brain import Brain
        from anima.core.memory import Memory
        from anima.core.policy import Decision

        try:
            bot = config.load_bot(key)
        except FileNotFoundError as exc:
            raise _fail(exc) from exc
        message = str(body.get("message") or f"嗨{bot.config.identity.display_name}！第一次见面，介绍一下你自己吧")[:300]
        memory = await Memory(":memory:").open()
        try:
            brain = Brain(bot, memory, runtime.brain.llm, rng=random.Random())
            brain.skills = []
            chat = Chat("console", "private", "preview", "你")
            ev = Incoming(chat, Sender("preview", "你"), message, message_id="p1", mentions_me=True)
            await memory.record(chat.key, ev.user_key, "你", message, platform_msg_id="p1")
            reply = await brain.compose(chat, [ev], Decision("reply", "第一次见面", addressed=True, target=ev))
        finally:
            await memory.close()
        return {"message": message, "bubbles": [b.plain(lambda s: brain.stickers.emoji(s.value) if s.type == "sticker" else "")
                                                for b in reply.bubbles],
                "model": runtime.brain.llm.model, "demo": bool(getattr(runtime.brain.llm, "demo", False))}

    # ------------------------------------------------------------ plugins

    def host():
        return runtime.extensions

    @router.get("/extensions")
    async def extensions() -> dict[str, Any]:
        return {"plugins": host().status(), "commands": host().help(), "mcp": runtime.plugins.status(),
                "persona": runtime.bot.config.identity.display_name, "persona_key": runtime.bot.key,
                "bridge": _bridge_status(runtime)}

    @router.post("/extensions/install")
    async def install(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        source = str(body.get("source") or "").strip()
        try:
            if body.get("data"):
                info = plugin_host.install_zip(_bytes(body), source=str(body.get("filename") or "upload"))
            elif source.startswith(("https://", "http://")):
                info = await plugin_host.install_from(source)
            else:
                raise ValueError("填一个 GitHub 仓库地址或 zip 链接，或者上传 zip")
        except Exception as exc:  # noqa: BLE001
            raise _fail(exc) from exc
        if body.get("enable", True):
            await host().enable(info.id, True)
        return {"installed": info.to_dict(), **(await extensions())}

    @router.post("/extensions/{pid}/enable")
    async def enable(pid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            await host().enable(pid, bool(body.get("on", True)))
        except Exception as exc:  # noqa: BLE001
            raise _fail(exc) from exc
        return await extensions()

    @router.put("/extensions/{pid}/config")
    async def configure(pid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        if pid not in plugin_host.discover():
            raise HTTPException(404, pid)
        await host().configure(pid, dict(body.get("values") or {}))
        return await extensions()

    @router.post("/extensions/{pid}/requirements")
    async def requirements(pid: str) -> dict[str, Any]:
        info = plugin_host.discover().get(pid)
        if not info:
            raise HTTPException(404, pid)
        try:
            log = await plugin_host.install_requirements(info)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"安装依赖失败：{exc}") from exc
        if pid in host().enabled_ids():
            await host().load(info)
        return {"log": log, **(await extensions())}

    @router.delete("/extensions/{pid}")
    async def remove(pid: str) -> dict[str, Any]:
        if pid in host().enabled_ids():
            await host().enable(pid, False)
        try:
            plugin_host.uninstall(pid)
        except Exception as exc:  # noqa: BLE001
            raise _fail(exc) from exc
        return await extensions()

    # ------------------------------------------------------------ market

    @router.get("/market/{shelf}")
    async def shelf(shelf: str, q: str = "", refresh: bool = False) -> dict[str, Any]:
        try:
            items = await market.shelf(shelf, q, refresh)
        except KeyError as exc:
            raise HTTPException(404, shelf) from exc
        installed = plugin_host.discover()
        enabled = set(host().enabled_ids())
        servers = {s["name"] for s in runtime.plugins.status()}
        sources = {str(i.homepage or "").rstrip("/") for i in installed.values()}
        for item in items:
            pid = item.get("id")
            if item["kind"] in ("anima", "astrbot"):
                match = installed.get(pid) or next((i for i in installed.values()
                                                    if item.get("source") and str(i.homepage).rstrip("/") == item["source"].rstrip("/")), None)
                item["installed"] = bool(match) or (item.get("source", "").rstrip("/") in sources and bool(item.get("source")))
                item["enabled"] = bool(match and match.id in enabled)
                item["plugin_id"] = match.id if match else pid
            elif item["kind"] == "mcp":
                item["installed"] = pid in servers
            elif item["kind"] == "persona":
                item["installed"] = pid in config.list_bots()
        return {"shelf": shelf, "items": items}

    return router


def _bridge_status(runtime: Runtime) -> dict[str, Any]:
    qq = runtime.adapters.get("qq")
    bridge = getattr(qq, "bridge", None)
    if bridge is None:
        return {"available": False}
    return {"available": True, "listen": bridge.listen_port, "connect": bridge.connect_urls, "peers": len(bridge.peers),
            "prefixes": qq.cfg.bridge_prefixes}
