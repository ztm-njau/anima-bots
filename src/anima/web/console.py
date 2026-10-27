"""HTTP API behind the console: people, requests, 世界书, 表情包, plugins, settings."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import tomlkit
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from anima.config import BotConfig
from anima.core.cards import card_fields, create_bot_from_card, read_card
from anima.core.lorebook import LoreEntry, from_sillytavern
from anima.plugins import RECOMMENDED

if TYPE_CHECKING:
    from anima.runtime import Runtime

# Settings the console edits: (section path, key). Saved into bot.toml with comments kept.
SETTINGS: dict[str, tuple[str, str]] = {
    "owners": ("", "owners"),
    "display_name": ("identity", "display_name"),
    "aliases": ("identity", "aliases"),
    "group_chattiness": ("behavior", "group_chattiness"),
    "interests": ("behavior", "interests"),
    "cooldown_seconds": ("behavior", "cooldown_seconds"),
    "delays": ("behavior", "delays"),
    "caption_images": ("behavior", "caption_images"),
    "collect_stickers": ("behavior", "collect_stickers"),
    "recall": ("behavior", "recall"),
    "debounce_private": ("behavior", "debounce_private"),
    "debounce_group": ("behavior", "debounce_group"),
    "debounce_max": ("behavior", "debounce_max"),
    "interrupt": ("behavior", "interrupt"),
    "typing_cps": ("behavior", "typing_cps"),
    "bubble_split": ("behavior", "bubble_split"),
    "reply_budget": ("behavior", "reply_budget"),
    "max_bubbles": ("behavior", "max_bubbles"),
    "group_max_bubbles": ("behavior", "group_max_bubbles"),
    "follow_up_seconds": ("behavior", "follow_up_seconds"),
    "interjections_per_hour": ("behavior", "interjections_per_hour"),
    "repeat_chance": ("behavior", "repeat_chance"),
    "auto_quote": ("behavior", "auto_quote"),
    "name_false_friends": ("behavior", "name_false_friends"),
    "daily_plan": ("life", "daily_plan"),
    "diary": ("life", "diary"),
    "diary_time": ("life", "diary_time"),
    "greet_groups": ("life", "greet_groups"),
    "idle_chatter": ("life", "idle_chatter"),
    "qq.enabled": ("platforms.qq", "enabled"),
    "qq.groups": ("platforms.qq", "groups"),
    "qq.listen_groups": ("platforms.qq", "listen_groups"),
    "qq.friend_requests": ("platforms.qq", "friend_requests"),
    "qq.group_invites": ("platforms.qq", "group_invites"),
    "qq.friend_keywords": ("platforms.qq", "friend_keywords"),
    "bilibili.enabled": ("platforms.bilibili", "enabled"),
    "bilibili.live_rooms": ("platforms.bilibili", "live_rooms"),
    "bilibili.post_diary": ("platforms.bilibili", "post_diary"),
    "wechat.enabled": ("platforms.wechat", "enabled"),
    "douyin.enabled": ("platforms.douyin", "enabled"),
    "douyin.live_rooms": ("platforms.douyin", "live_rooms"),
}
NEEDS_RESTART = {k for k in SETTINGS if k.endswith(".enabled") or k.endswith("live_rooms")}
CHAT_FIELDS = ("mode", "chattiness", "debounce", "max_bubbles", "repeat_chance", "note")


def _decode(payload: dict[str, Any]) -> bytes:
    data = payload.get("data") or ""
    if "," in data and data.startswith("data:"):
        data = data.split(",", 1)[1]
    try:
        return base64.b64decode(data)
    except ValueError as exc:
        raise HTTPException(400, "文件读不出来") from exc


def _get(doc: Any, section: str, key: str) -> Any:
    node = doc
    for part in [p for p in section.split(".") if p]:
        node = node.get(part, {}) if hasattr(node, "get") else {}
    value = node.get(key) if hasattr(node, "get") else None
    return value.unwrap() if hasattr(value, "unwrap") else value


def _set(doc: Any, section: str, key: str, value: Any) -> None:
    node = doc
    for part in [p for p in section.split(".") if p]:
        if part not in node:
            node[part] = tomlkit.table()
        node = node[part]
    node[key] = value


def console_router(runtime: Runtime) -> APIRouter:
    router = APIRouter(prefix="/api/console")
    brain = runtime.brain
    memory = brain.memory

    # ------------------------------------------------------------ overview

    @router.get("/overview")
    async def overview() -> dict[str, Any]:
        users = await memory.users(limit=10000)
        return {
            "bot": brain.cfg.identity.display_name,
            "model": f"{brain.llm.label} · {brain.llm.model}",
            "demo": bool(getattr(brain.llm, "demo", False)),
            "people": len(users),
            "blocked": sum(1 for u in users if u.blocked),
            "requests": len(await memory.requests()),
            "lore": len(brain.lorebook.entries()),
            "stickers": await brain.memes.count(),
            "plugins": sum(1 for p in runtime.plugins.status() if p["status"] == "running"),
            "skills": len(brain.skills),
            "platforms": sorted(brain.adapters),
            "cost": brain.cost_text(),
        }

    # ------------------------------------------------------------ people

    @router.get("/people")
    async def people(q: str = "") -> list[dict[str, Any]]:
        out = []
        for user in await memory.users(q):
            facts = await memory.facts(user.key, 50)
            out.append({**user.to_dict(), "facts": len(facts)})
        return out

    @router.get("/people/{key}")
    async def person(key: str) -> dict[str, Any]:
        user = await memory.get_user(key)
        if not user:
            raise HTTPException(404, "没有这个人")
        facts = await memory.facts(key, 100)
        return {**user.to_dict(), "fact_list": [{"id": f.id, "content": f.content, "importance": f.importance} for f in facts]}

    @router.patch("/people/{key}")
    async def edit_person(key: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        fields = {k: body[k] for k in ("nickname", "profile", "notes", "blocked", "affinity", "silenced_until") if k in body}
        if "blocked" in fields:
            fields["blocked"] = int(bool(fields["blocked"]))
        await memory.update_user(key, **fields)
        return await person(key)

    @router.post("/people/{key}/facts")
    async def add_fact(key: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        await memory.add_fact(key, str(body.get("content", "")), int(body.get("importance", 3)), source="console")
        return await person(key)

    @router.delete("/people/{key}/facts/{fact_id}")
    async def delete_fact(key: str, fact_id: int) -> dict[str, Any]:
        await memory.forget(fact_id)
        return await person(key)

    @router.post("/people/{key}/forget")
    async def forget_person(key: str) -> dict[str, Any]:
        await memory.delete_user_memories(key)
        return await person(key)

    # ------------------------------------------------------------ requests

    @router.get("/requests")
    async def requests(status: str = "") -> list[dict[str, Any]]:
        return await memory.requests(status or None)

    @router.post("/requests/{request_id}")
    async def decide(request_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return {"result": await brain.admin.decide(request_id, bool(body.get("approve")))}

    # ------------------------------------------------------------ 世界书

    @router.get("/lore")
    async def lore() -> dict[str, Any]:
        return {name: [e.__dict__ for e in entries] for name, entries in brain.lorebook.books.items()}

    @router.put("/lore/{name}")
    async def save_lore(name: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        entries = [LoreEntry(**{k: v for k, v in e.items() if k in LoreEntry.__dataclass_fields__})
                   for e in body.get("entries", []) if e.get("content")]
        saved = brain.lorebook.save(name, entries)
        return {"name": saved, "books": await lore()}

    @router.delete("/lore/{name}")
    async def delete_lore(name: str) -> dict[str, Any]:
        brain.lorebook.delete(name)
        return await lore()

    @router.post("/lore/import")
    async def import_lore(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """A SillyTavern world book, or the character book inside a character card (PNG or JSON)."""
        raw = _decode(body)
        try:
            data = read_card(raw)
        except Exception as exc:
            raise HTTPException(400, f"读不懂这个文件：{exc}") from exc
        book = card_fields(data)["character_book"] if ("data" in data or "spec" in data) else data
        entries = from_sillytavern(book or {})
        if not entries:
            raise HTTPException(400, "里面没有世界书条目")
        name = (body.get("name") or body.get("filename") or "导入").rsplit(".", 1)[0]
        saved = brain.lorebook.save(name, entries)
        return {"name": saved, "count": len(entries), "books": await lore()}

    @router.post("/lore/test")
    async def test_lore(body: dict[str, Any] = Body(...)) -> list[str]:
        return brain.lorebook.triggered(str(body.get("text", "")), brain.cfg.behavior.lore_budget)

    @router.post("/cards/import")
    async def import_card(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            folder = create_bot_from_card(_decode(body), body.get("folder") or None)
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(400, f"读不懂这张角色卡：{exc}") from exc
        return {"bot": folder.name, "run": f"uv run anima play {folder.name}"}

    # ------------------------------------------------------------ 表情包

    @router.get("/stickers")
    async def stickers() -> list[dict[str, Any]]:
        return [{"id": s.id, "url": f"/sticker/{s.id}", "tags": s.tags, "description": s.description,
                 "source": s.source, "uses": s.uses} for s in await brain.memes.all()]

    @router.post("/stickers")
    async def upload_sticker(body: dict[str, Any] = Body(...)) -> list[dict[str, Any]]:
        name = str(body.get("filename") or "sticker.png")
        tags = [t for t in str(body.get("tags") or "").replace("，", " ").split() if t]
        if not tags:
            tags = [name.rsplit(".", 1)[0]]
        await brain.memes.add(_decode(body), "." + name.rsplit(".", 1)[-1], tags, str(body.get("description") or ""),
                              source="console")
        return await stickers()

    @router.patch("/stickers/{sticker_id}")
    async def edit_sticker(sticker_id: int, body: dict[str, Any] = Body(...)) -> list[dict[str, Any]]:
        fields = {}
        if "tags" in body:
            fields["tags"] = " ".join(str(body["tags"]).replace("，", " ").split())
        if "description" in body:
            fields["description"] = str(body["description"])
        await memory.update_sticker(sticker_id, **fields)
        return await stickers()

    @router.delete("/stickers/{sticker_id}")
    async def delete_sticker(sticker_id: int) -> list[dict[str, Any]]:
        await brain.memes.remove(sticker_id)
        return await stickers()

    # ------------------------------------------------------------ plugins (MCP)

    @router.get("/plugins")
    async def plugins() -> dict[str, Any]:
        return {"servers": runtime.plugins.status(), "recommended": RECOMMENDED, "path": str(runtime.plugins.path)}

    @router.put("/plugins/{name}")
    async def save_plugin(name: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        config = body.get("config")
        if not isinstance(config, dict) or not (config.get("command") or config.get("url")):
            raise HTTPException(400, "需要 command（本机命令）或 url（远程 MCP）")
        servers = runtime.plugins.load_config()
        servers[name] = config
        runtime.plugins.save_config(servers)
        await runtime.plugins.start_server(name, config)
        return await plugins()

    @router.post("/plugins/{name}/restart")
    async def restart_plugin(name: str) -> dict[str, Any]:
        config = runtime.plugins.load_config().get(name)
        if config is None:
            raise HTTPException(404, "没有这个插件")
        await runtime.plugins.start_server(name, config)
        return await plugins()

    @router.post("/plugins/{name}/toggle")
    async def toggle_plugin(name: str) -> dict[str, Any]:
        servers = runtime.plugins.load_config()
        if name not in servers:
            raise HTTPException(404, "没有这个插件")
        servers[name]["disabled"] = not servers[name].get("disabled", False)
        runtime.plugins.save_config(servers)
        await runtime.plugins.start_server(name, servers[name])
        return await plugins()

    @router.delete("/plugins/{name}")
    async def delete_plugin(name: str) -> dict[str, Any]:
        servers = runtime.plugins.load_config()
        servers.pop(name, None)
        runtime.plugins.save_config(servers)
        await runtime.plugins.stop_server(name)
        return await plugins()

    # ------------------------------------------------------------ settings

    def toml_path():
        return runtime.bot.dir / "bot.toml"

    async def chat_rows(doc: Any) -> list[dict[str, Any]]:
        """Every group she can see, with its overrides (blank = follow the defaults)."""
        saved = (doc.get("chats") or {}).unwrap() if doc.get("chats") else {}
        keys: dict[str, str] = {}
        qq = (doc.get("platforms") or {}).get("qq") or {}
        for g in [*(qq.get("groups") or []), *(qq.get("listen_groups") or [])]:
            keys[f"qq:group:{g}"] = ""
        for row in await memory.chats():
            if row.get("kind") == "group" and (row["key"] in keys or row["key"] in saved):
                keys[row["key"]] = row.get("title") or ""
        for key in saved:
            keys.setdefault(key, "")
        return [{"key": k, "title": title, **{f: (saved.get(k) or {}).get(f) for f in CHAT_FIELDS}}
                for k, title in keys.items()]

    def effective(doc: Any, section: str, key: str) -> Any:
        """The value in bot.toml, or the built-in default she is actually using."""
        value = _get(doc, section, key)
        if value is None and section in ("behavior", "life", "identity"):
            value = getattr(getattr(brain.cfg, section), key, None)
        return value

    @router.get("/settings")
    async def settings() -> dict[str, Any]:
        doc = tomlkit.parse(toml_path().read_text(encoding="utf-8"))
        return {
            "values": {name: effective(doc, sec, key) for name, (sec, key) in SETTINGS.items()},
            "chats": await chat_rows(doc),
            "persona": runtime.bot.read("persona.md"),
            "examples": runtime.bot.read("examples.md"),
            "needs_restart": sorted(NEEDS_RESTART),
        }

    @router.put("/settings")
    async def save_settings(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        doc = tomlkit.parse(toml_path().read_text(encoding="utf-8"))
        changed = []
        for name, value in (body.get("values") or {}).items():
            if name in SETTINGS and effective(doc, *SETTINGS[name]) != value:
                _set(doc, *SETTINGS[name], value)
                changed.append(name)
        if isinstance(body.get("chats"), dict):
            if "chats" not in doc:
                doc["chats"] = tomlkit.table(is_super_table=True)
            table = doc["chats"]
            for key, fields in body["chats"].items():
                clean = {f: v for f, v in (fields or {}).items()
                         if f in CHAT_FIELDS and v not in (None, "") and not (f == "mode" and v == "normal")}
                old = table[key].unwrap() if key in table else {}
                if clean != old:
                    changed.append(f"chats.{key}")
                    if clean:
                        sub = tomlkit.table()
                        for f, v in clean.items():
                            sub[f] = v
                        table[key] = sub
                    elif key in table:
                        del table[key]
            if not table:
                del doc["chats"]
        new_cfg = BotConfig.model_validate(doc.unwrap())  # refuse anything that wouldn't load
        toml_path().write_text(tomlkit.dumps(doc), encoding="utf-8")
        for name in ("persona", "examples"):
            if isinstance(body.get(name), str) and body[name] != runtime.bot.read(f"{name}.md"):
                (runtime.bot.dir / f"{name}.md").write_text(body[name], encoding="utf-8")
                changed.append(name)
        # Live: behaviour, life, owners, names, QQ groups. Platforms switching on/off need a restart.
        cfg = brain.cfg
        cfg.owners, cfg.behavior, cfg.life, cfg.chats = new_cfg.owners, new_cfg.behavior, new_cfg.life, new_cfg.chats
        cfg.identity, cfg.platforms = new_cfg.identity, new_cfg.platforms
        brain.policy.cfg = new_cfg.behavior
        brain.policy.aliases = [a.lower() for a in [*new_cfg.identity.aliases, new_cfg.identity.name,
                                                     new_cfg.identity.display_name] if a]
        brain.policy.interests = [i.lower() for i in new_cfg.behavior.interests if i]
        brain.humanizer.cfg = new_cfg.behavior
        brain.humanizer.scale = 1.0 if new_cfg.behavior.delays else 0.0
        runtime.life.cfg = new_cfg.life
        qq = brain.adapters.get("qq")
        if qq is not None and hasattr(qq, "speak_groups"):
            extras = new_cfg.platform("qq").extras()
            qq.speak_groups = {str(g) for g in extras.get("groups", [])}
            qq.listen_groups = {str(g) for g in extras.get("listen_groups", [])}
        brain.prompt._system = None  # persona edits apply from the next reply
        return {"changed": changed, "restart": sorted(set(changed) & NEEDS_RESTART), **(await settings())}

    return router


def sticker_route(runtime: Runtime):
    async def sticker_file(sticker_id: str):
        brain = runtime.brain
        for sticker in await brain.memes.all():
            if sticker.id == sticker_id and sticker.path.exists():
                return FileResponse(sticker.path, media_type=sticker.media_type)
        raise HTTPException(404, "没有这个表情包")

    return sticker_file
