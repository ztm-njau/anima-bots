"""The market: where plugins, MCP servers and persona packs are found.

Five shelves, each normalised to the same entry shape for the console:

- ``anima``    Anima plugins: the index in ``market/index.json`` (refreshed from GitHub when online)
- ``mcp``      MCP servers: a curated list, plus live search of the official MCP Registry
- ``astrbot``  AstrBot's community collection (~1,300 plugins), installed onto the compatibility layer
- ``nonebot``  NoneBot2's registry: these run in NoneBot itself, connected through the OneBot bridge
- ``personas`` persona packs listed in the index

Remote lists are cached for six hours in ``data/market/``; every shelf still answers offline.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from anima import config

INDEX_URL = "https://raw.githubusercontent.com/ztm-njau/anima-bots/main/market/index.json"
ASTRBOT_URL = "https://raw.githubusercontent.com/AstrBotDevs/AstrBot_Plugins_Collection/main/plugins.json"
NONEBOT_URL = "https://raw.githubusercontent.com/nonebot/registry/results/plugins.json"
MCP_REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"
CACHE_SECONDS = 6 * 3600


def local_index() -> dict[str, Any]:
    path = config.REPO_ROOT / "market" / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _cache_path(name: str) -> Path:
    return config.DATA_DIR / "market" / f"{name}.json"


_FAILED: dict[str, float] = {}  # source -> when it last failed, so an offline source isn't retried every click


async def _fetch_json(url: str, name: str, refresh: bool = False) -> Any:
    path = _cache_path(name)
    if not refresh and path.exists() and time.time() - path.stat().st_mtime < CACHE_SECONDS:
        return json.loads(path.read_text(encoding="utf-8"))
    if not refresh and time.time() - _FAILED.get(name, 0) < 600:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    import httpx

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - offline: use what we have
        logger.info("[market] {} unavailable ({}), using cache", name, exc)
        _FAILED[name] = time.time()
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


SECTIONS = ("plugins", "mcp", "personas", "frameworks")


async def index(refresh: bool = False) -> dict[str, Any]:
    """The local index joined with the one on GitHub: new entries from either side show up, and for an
    entry both have, the GitHub copy (the newer description) wins."""
    local = local_index()
    remote = await _fetch_json(INDEX_URL, "anima-index", refresh)
    if not (isinstance(remote, dict) and remote.get("format") == "anima-market"):
        return local
    merged = dict(local)
    for section in SECTIONS:
        by_id = {e.get("id"): e for e in local.get(section, []) if isinstance(e, dict)}
        for entry in remote.get(section, []):
            if isinstance(entry, dict) and entry.get("id"):
                by_id[entry["id"]] = by_id.get(entry["id"], {}) | entry
        merged[section] = list(by_id.values())
    return merged


def _match(entry: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    hay = " ".join(str(entry.get(k, "")) for k in ("id", "name", "desc", "author")) + " " + " ".join(entry.get("tags", []))
    return all(word.lower() in hay.lower() for word in query.split())


async def shelf(kind: str, query: str = "", refresh: bool = False, limit: int = 60) -> list[dict[str, Any]]:
    if kind == "anima":
        items = [e | {"kind": "anima", "compat": "native"} for e in (await index(refresh)).get("plugins", [])]
    elif kind == "personas":
        items = [e | {"kind": "persona", "compat": "native"} for e in (await index(refresh)).get("personas", [])]
    elif kind == "mcp":
        items = [e | {"kind": "mcp", "compat": "native"} for e in (await index(refresh)).get("mcp", [])]
        if query:
            items = [e for e in items if _match(e, query)] + await search_mcp_registry(query, limit)
            return items[:limit]
    elif kind == "astrbot":
        data = await _fetch_json(ASTRBOT_URL, "astrbot", refresh) or {}
        items = [{"id": key, "name": v.get("display_name") or key, "desc": v.get("desc", ""), "author": v.get("author", ""),
                  "homepage": v.get("repo", ""), "source": v.get("repo", ""), "tags": v.get("tags") or [],
                  "kind": "astrbot", "compat": "partial"} for key, v in data.items() if isinstance(v, dict) and v.get("repo")]
    elif kind == "nonebot":
        data = await _fetch_json(NONEBOT_URL, "nonebot", refresh) or []
        items = [{"id": v.get("project_link") or v.get("module_name"), "name": v.get("name", ""), "desc": v.get("desc", ""),
                  "author": v.get("author", ""), "homepage": v.get("homepage", ""), "kind": "nonebot", "compat": "bridge",
                  "tags": [t.get("label", "") for t in v.get("tags") or []],
                  "install_hint": f"nb plugin install {v.get('project_link') or v.get('module_name')}"}
                 for v in data if isinstance(v, dict) and v.get("valid", True)]
    else:
        raise KeyError(kind)
    hits = [e for e in items if _match(e, query)]
    return hits[:limit]


def registry_config(server: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """An ``mcpServers`` entry for a Registry server, and the environment variables it asks for."""
    for remote in server.get("remotes") or []:
        if remote.get("type") in ("streamable-http", "http") and remote.get("url"):
            return {"url": remote["url"]}, []
    for pkg in server.get("packages") or []:
        if (pkg.get("transport") or {}).get("type", "stdio") != "stdio":
            continue
        ident, kind = pkg.get("identifier"), pkg.get("registryType") or pkg.get("registry_type")
        env = [{"name": v.get("name"), "description": v.get("description", ""), "required": bool(v.get("isRequired"))}
               for v in pkg.get("environmentVariables") or [] if v.get("name")]
        args = [a.get("value") for a in pkg.get("packageArguments") or [] if a.get("type") == "positional" and a.get("value")]
        if kind == "npm":
            return {"command": "npx", "args": ["-y", ident, *args]}, env
        if kind == "pypi":
            return {"command": "uvx", "args": [ident, *args]}, env
        if kind == "oci":
            return {"command": "docker", "args": ["run", "-i", "--rm", ident, *args]}, env
    return None, []


async def search_mcp_registry(query: str, limit: int = 30) -> list[dict[str, Any]]:
    """Live search of registry.modelcontextprotocol.io (latest version of each server only)."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(MCP_REGISTRY, params={"search": query, "limit": min(100, limit * 3), "version": "latest"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.info("[market] MCP registry search failed: {}", exc)
        return []
    out, seen = [], set()
    for item in data.get("servers") or []:
        server = item.get("server", item)
        name = server.get("name")
        if not name or name in seen:
            continue
        cfg, env = registry_config(server)
        if cfg is None:
            continue
        seen.add(name)
        if env:
            cfg["env"] = {v["name"]: "" for v in env}
        out.append({"id": name.rsplit("/", 1)[-1][:28], "name": server.get("title") or name, "desc": server.get("description", ""),
                    "author": name.split("/", 1)[0], "homepage": server.get("websiteUrl") or (server.get("repository") or {}).get("url", ""),
                    "config": cfg, "env": env, "kind": "mcp", "compat": "native", "registry": name})
        if len(out) >= limit:
            break
    return out
