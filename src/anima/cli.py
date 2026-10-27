"""``anima``: run, talk to, log in, and look after your bots."""

from __future__ import annotations

import asyncio
import json
import os
import plistlib
import re
import secrets
import shutil
import socket
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from anima.config import REPO_ROOT, env, list_bots, load_bot

app = typer.Typer(help="Anima: a soul engine for human-like social bots.", no_args_is_help=True, add_completion=False)
napcat_app = typer.Typer(help="Run NapCat (QQ ↔ OneBot) in Docker.", no_args_is_help=True)
service_app = typer.Typer(help="Keep a bot running in the background with launchd.", no_args_is_help=True)
providers_app = typer.Typer(help="Model providers (same as the 模型提供商 panel).", no_args_is_help=True)
app.add_typer(napcat_app, name="napcat")
app.add_typer(service_app, name="service")
magpie_app = typer.Typer(help="Run the magpie model gateway (github.com/yetone/magpie) in Docker.", no_args_is_help=True)
app.add_typer(providers_app, name="providers")
app.add_typer(magpie_app, name="magpie")
persona_app = typer.Typer(help="Personas: list, choose the default, export and import packs.", no_args_is_help=True)
plugin_app = typer.Typer(help="Plugins (Anima and AstrBot) for a persona.", no_args_is_help=True)
app.add_typer(persona_app, name="persona")
app.add_typer(plugin_app, name="plugin")
console = Console()

NAPCAT_DIR = REPO_ROOT / "infra" / "napcat"
MAGPIE_DIR = REPO_ROOT / "infra" / "magpie"
MAGPIE_CONTAINER = "anima-magpie"
MAGPIE_GATEWAY = "http://127.0.0.1:3425/v1"
ENV_FILE = REPO_ROOT / ".env"
BOT_HELP = "人设（bots/ 下的文件夹名），默认是上次选的那个"


def _bot(bot: str | None) -> str:
    from anima.config import default_bot

    return bot or default_bot()


def _run(coro) -> None:
    from anima.runtime import AlreadyRunning

    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        pass
    except AlreadyRunning as exc:
        console.print(f"[red]{escape(str(exc))}[/]")
        raise typer.Exit(1) from exc


# ------------------------------------------------------------------ talking & running


@app.command()
def play(bot: str = typer.Argument(None, help=BOT_HELP), port: int = typer.Option(None, help="默认读 bot.toml"),
         fast: bool = typer.Option(False, help="跳过真人节奏，立即回复"),
         demo: bool = typer.Option(False, help="不调用模型，用预设台词")) -> None:
    """Open the local playground (web UI). No platform account needed."""
    bot = _bot(bot)
    from anima.runtime import Runtime

    _run(Runtime(bot, platforms=["playground"], fast=fast, demo=demo, port=port).run())


@app.command()
def chat(bot: str = typer.Argument(None, help=BOT_HELP), fast: bool = typer.Option(False, help="立即回复"),
         demo: bool = typer.Option(False, help="不调用模型")) -> None:
    """Chat with a bot in this terminal."""
    bot = _bot(bot)
    from anima.runtime import Runtime

    _run(Runtime(bot, platforms=[], console=True, fast=fast, demo=demo).run())


@app.command()
def run(bot: str = typer.Argument(None, help=BOT_HELP),
        only: str = typer.Option(None, help="只启动这些平台，逗号分隔，比如 qq,bilibili"),
        port: int = typer.Option(None, help="网页端口，默认读 bot.toml"),
        verbose: bool = typer.Option(False, "-v", help="调试日志")) -> None:
    """Run a bot on every platform enabled in its bot.toml."""
    bot = _bot(bot)
    from anima.runtime import Runtime

    platforms = [p.strip() for p in only.split(",")] if only else None
    _run(Runtime(bot, platforms=platforms, verbose=verbose, port=port).run())


@app.command()
def login(platform: str = typer.Argument(..., help="bilibili | douyin"), bot: str = typer.Option(None, help=BOT_HELP)) -> None:
    """Log a bot into a platform by scanning a QR code (use a dedicated account)."""
    bot = _bot(bot)
    b = load_bot(bot)
    if platform == "bilibili":
        from anima.adapters.bilibili import qr_login

        path = asyncio.run(qr_login(b.secrets_dir))
        console.print(f"[green]已保存登录凭据[/] → {path}")
    elif platform == "douyin":
        from anima.adapters.douyin import interactive_login

        ok = asyncio.run(interactive_login(b.data_dir))
        console.print("[green]抖音登录完成[/]" if ok else "[red]超时，没有检测到登录[/]")
    elif platform == "qq":
        console.print("QQ 通过 NapCat 登录：[bold]uv run anima napcat up[/]，然后打开 WebUI 扫码。")
    else:
        raise typer.BadParameter("支持 bilibili、douyin（QQ 用 anima napcat）")


@app.command()
def new(name: str = typer.Argument(..., help="新人设的文件夹名，比如 luna"),
        display: str = typer.Option(None, "--name", help="她的名字，默认同文件夹名")) -> None:
    """Create a new persona (only bot.toml + persona.md; the rest comes from bots/_template)."""
    from anima import personas

    try:
        key = personas.create({"key": name, "name": display or name})
    except (ValueError, FileExistsError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]创建好了[/] → bots/{key}/  先写 persona.md，然后 [bold]uv run anima play {key}[/]\n"
                  "也可以在管理后台的「人设」页填表、用一句话让模型起草，或者导入 SillyTavern 角色卡。")


@app.command()
def memory(bot: str = typer.Argument(None, help=BOT_HELP), who: str = typer.Option(None, help="按名字查一个人")) -> None:
    """See who a bot knows and what it remembers about them."""
    bot = _bot(bot)
    from anima.core.memory import Memory

    async def show() -> None:
        b = load_bot(bot)
        mem = await Memory(b.data_dir / "memory.db").open()
        rows = await mem.conn.execute_fetchall(
            "SELECT * FROM users WHERE name LIKE ? ORDER BY msg_count DESC LIMIT 40", (f"%{who or ''}%",))
        table = Table("平台", "名字", "她叫TA", "好感", "消息", "记得的事")
        for r in rows:
            facts = await mem.facts(r["key"], 6)
            table.add_row(r["platform"], r["name"], r["nickname"] or "", f"{r['affinity']:.2f}", str(r["msg_count"]),
                          "；".join(f.content for f in facts))
        console.print(table)
        selfs = await mem.facts("self", 20)
        if selfs:
            console.print("[bold]她说过的关于自己的事：[/]" + "；".join(f.content for f in selfs))
        await mem.close()

    asyncio.run(show())


@app.command()
def diary(bot: str = typer.Argument(None, help=BOT_HELP), days: int = 7) -> None:
    """Read a bot's diary."""
    bot = _bot(bot)
    from anima.core.memory import Memory

    async def show() -> None:
        b = load_bot(bot)
        mem = await Memory(b.data_dir / "memory.db").open()
        for entry in reversed(await mem.journal_list("diary", days)):
            console.rule(entry["date"])
            console.print(entry["content"])
        await mem.close()

    asyncio.run(show())


@app.command("eval")
def eval_(bot: str = typer.Argument(None, help=BOT_HELP),
          provider: str = typer.Option(None, help="提供商 id（默认用当前生效的路由）"),
          model: str = typer.Option(None, help="模型 id"),
          only: str = typer.Option(None, help="只跑这些场景，逗号分隔，比如 human,injection")) -> None:
    """考考她: run the persona exam against a provider and save a report."""
    bot = _bot(bot)
    from anima import evals
    from anima.llm import build_target, make_provider
    from anima.llm.registry import ProviderStore, Target

    b = load_bot(bot)
    store = ProviderStore()
    if provider:
        llm, why = build_target(store, Target(provider, model or ""), b.config.llm)
        if llm is None:
            raise typer.BadParameter(why)
    else:
        llm = make_provider(b, store=store)
    if getattr(llm, "demo", False):
        console.print(f"[yellow]当前是演示模式（{getattr(llm, 'note', '')}），考的是预设台词[/]")
    scenarios = [s for s in evals.SCENARIOS if not only or s.id in only.split(",")]
    title = f"{llm.label} · {llm.model}"
    console.print(f"考考{b.config.identity.display_name}：{title}，{len(scenarios)} 个场景…")
    results = asyncio.run(evals.run(b, llm, scenarios))
    table = Table("场景", "", "她说", "没通过", "耗时")
    for r in results:
        failed = "；".join(name for name, ok in r.checks if not ok) or r.error
        table.add_row(r.scenario.title, "[green]✓[/]" if r.passed else "[red]✗[/]",
                      escape(" / ".join(r.bubbles))[:80], escape(failed), f"{r.latency_ms}ms")
    console.print(table)
    s = evals.summary(results)
    path = evals.save_report(b, results, title)
    console.print(f"通过 {s['passed']}/{s['scenarios']}，检查项 {s['checks_passed']}/{s['checks']}，"
                  f"平均 {s['avg_latency_ms']} ms，花费 {s['cost']} {s['currency']}\n报告：{path}")


# ------------------------------------------------------------------ health


def _port_open(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


@app.command()
def doctor(bot: str = typer.Argument(None, help=BOT_HELP)) -> None:
    """Check everything a bot needs, with a hint for each missing piece."""
    bot = _bot(bot)
    b = load_bot(bot)
    cfg = b.config
    table = Table("", "检查项", "说明", show_lines=False)

    def row(ok: bool | None, item: str, note: str) -> None:
        table.add_row({True: "[green]✓[/]", False: "[red]✗[/]", None: "[dim]–[/]"}[ok], escape(item), escape(note))

    row(True, "Bot", f"{cfg.identity.display_name}（{bot}），{len(list_bots())} 个 bot：{', '.join(list_bots())}")
    row(ENV_FILE.exists(), ".env", "存在" if ENV_FILE.exists() else "没有 .env：cp .env.example .env")
    from anima.llm import make_provider

    brain_llm = make_provider(b)
    if getattr(brain_llm, "demo", False):
        row(False, "模型", f"{getattr(brain_llm, 'note', '')}：打开 http://127.0.0.1:8765/providers 接入，或 uv run anima providers add deepseek")
    else:
        row(True, "模型", f"{brain_llm.label} · {brain_llm.model}（{getattr(brain_llm, 'source', '')}）")
    row(shutil.which("ffmpeg") is not None, "ffmpeg", "语音处理" if shutil.which("ffmpeg") else "brew install ffmpeg")

    platforms = {n for n, pc in cfg.platforms.items() if pc.enabled}
    qq = cfg.platform("qq").extras()
    docker = shutil.which("docker") is not None
    napcat_up = False
    if docker:
        out = subprocess.run(["docker", "ps", "--filter", "name=anima-napcat", "--format", "{{.Status}}"],
                             capture_output=True, text=True)
        napcat_up = out.returncode == 0 and bool(out.stdout.strip())
    onebot_open = _port_open("127.0.0.1", 3001)
    row(napcat_up if "qq" in platforms else None, "QQ · NapCat 容器",
        "运行中" if napcat_up else "uv run anima napcat init && uv run anima napcat up")
    row(onebot_open if "qq" in platforms else None, "QQ · OneBot 端口 3001",
        "可连接" if onebot_open else "NapCat 没启动或还没扫码登录")
    row(bool(qq.get("groups")) if "qq" in platforms else None, "QQ · 允许发言的群",
        ", ".join(map(str, qq.get("groups", []))) or "bot.toml 里 [platforms.qq] groups 为空：只回私聊")

    bili_cred = (b.data_dir / "secrets" / "bilibili.json").exists()
    row(bili_cred if "bilibili" in platforms else None, "B站登录", "已保存" if bili_cred else "uv run anima login bilibili")
    dy_profile = (b.data_dir / "browser" / "douyin").exists()
    row(dy_profile if "douyin" in platforms else None, "抖音登录", "浏览器资料已保存" if dy_profile else "uv run anima login douyin")
    wx = cfg.platform("wechat").extras()
    if wx.get("mode", "official_account") == "official_account":
        row(bool(env(wx.get("token_env", "WECHAT_MP_TOKEN"))) if "wechat" in platforms else None, "微信公众号",
            "需要公网地址：cloudflared tunnel --url http://127.0.0.1:8765")
    plist = Path.home() / "Library/LaunchAgents" / f"ai.anima.{bot}.plist"
    row(plist.exists() or None, "后台常驻", "已安装 launchd 服务" if plist.exists() else f"可选：uv run anima service install {bot}")
    row(None, "启用的平台", ", ".join(sorted(platforms)) or "无")
    console.print(table)


# ------------------------------------------------------------------ NapCat


def _env_set(key: str, value: str) -> None:
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")] + [f"{key}={value}"]
    ENV_FILE.write_text("\n".join(lines) + "\n")
    ENV_FILE.chmod(0o600)


def _compose(*args: str) -> int:
    cmd = ["docker", "compose", "-f", str(NAPCAT_DIR / "compose.yaml"), "--env-file", str(ENV_FILE), *args]
    return subprocess.call(cmd, cwd=NAPCAT_DIR, env={**os.environ, "NAPCAT_UID": str(os.getuid()), "NAPCAT_GID": str(os.getgid())})


@napcat_app.command("init")
def napcat_init() -> None:
    """Create NapCat's data folders, tokens, and a OneBot config with a forward WebSocket."""
    runtime = NAPCAT_DIR / "runtime"
    for sub in ("qq", "config", "plugins"):
        (runtime / sub).mkdir(parents=True, exist_ok=True)
    token = env("ONEBOT_TOKEN") or secrets.token_urlsafe(24)
    webui = env("NAPCAT_WEBUI_TOKEN") or secrets.token_urlsafe(12)
    _env_set("ONEBOT_TOKEN", token)
    _env_set("NAPCAT_WEBUI_TOKEN", webui)
    config = json.loads((NAPCAT_DIR / "onebot11.template.json").read_text())
    config["network"]["websocketServers"][0]["token"] = token
    (runtime / "config" / "onebot11.json").write_text(json.dumps(config, indent=2, ensure_ascii=False))
    console.print("[green]NapCat 准备好了。[/] 下一步：[bold]uv run anima napcat up[/]")


@napcat_app.command("up")
def napcat_up() -> None:
    """Start NapCat, then scan the QR code in its WebUI with the bot's QQ account."""
    if not (NAPCAT_DIR / "runtime" / "config" / "onebot11.json").exists():
        napcat_init()
    if _compose("up", "-d") == 0:
        console.print(f"WebUI：[bold]http://127.0.0.1:6100/webui?token={env('NAPCAT_WEBUI_TOKEN')}[/]\n"
                      "用给她准备的 QQ 小号扫码登录；也可以 [bold]uv run anima napcat qr[/] 直接打开二维码。")


@napcat_app.command("down")
def napcat_down() -> None:
    """Stop NapCat (login data is kept)."""
    _compose("down")


@napcat_app.command("logs")
def napcat_logs(follow: bool = typer.Option(True, "-f/--no-follow")) -> None:
    """Show NapCat logs."""
    _compose("logs", "--tail", "200", *(["-f"] if follow else []))


@napcat_app.command("qr")
def napcat_qr() -> None:
    """Copy NapCat's login QR code out of the container and open it."""
    out = REPO_ROOT / "data" / "napcat-qrcode.png"
    out.parent.mkdir(exist_ok=True)
    if subprocess.call(["docker", "cp", "anima-napcat:/app/napcat/cache/qrcode.png", str(out)]) == 0:
        subprocess.call(["open", str(out)])
    else:
        console.print("[red]还没有二维码[/]：NapCat 启动中，或已经登录过了（看 uv run anima napcat logs）")


# ------------------------------------------------------------------ providers


@providers_app.command("list")
def providers_list(bot: str = typer.Option(None, help=BOT_HELP)) -> None:
    """Connected providers and what the bot uses right now."""
    bot = _bot(bot)
    from anima.llm.registry import ProviderStore, load_routing

    store = ProviderStore()
    table = Table("id", "名字", "地址", "key", "模型", "上次测试")
    for entry in store.all():
        info = store.public(entry)
        test = entry.last_test or {}
        table.add_row(entry.id, entry.name, entry.base_url, info["key_hint"] or ("不需要" if not info["needs_key"] else "—"),
                      ", ".join(entry.models[:4]), (f"✓ {test.get('latency_ms')}ms" if test.get("ok") else "✗") if test else "")
    console.print(table)
    r = load_routing(load_bot(bot))
    side = f"{r.side.provider}:{r.side.model}" if r.side else "同聊天"
    console.print(f"{bot} 正在用（来自 {r.source}）：聊天 {r.main.provider}:{r.main.model} · 后台 {side}"
                  + (f" · 备用 {', '.join(f'{b.provider}:{b.model}' for b in r.backups)}" if r.backups else ""))


@providers_app.command("add")
def providers_add(preset_id: str = typer.Argument(..., help="deepseek、kimi、zhipu、qwen、ollama…"),
                  key_env: str = typer.Option(None, help="从这个环境变量读 key，而不是保存 key 本身"),
                  base_url: str = typer.Option(None), model: list[str] = typer.Option(None, help="可重复")) -> None:
    """Connect a provider. Without --key-env, asks for the key (hidden input)."""
    import getpass

    from anima.llm.catalog import PRESET_BY_ID
    from anima.llm.registry import ProviderStore

    preset_obj = PRESET_BY_ID.get(preset_id)
    if not preset_obj:
        raise typer.BadParameter(f"可选：{', '.join(PRESET_BY_ID)}")
    data: dict = {"preset": preset_id}
    if key_env:
        data["api_key_env"] = key_env
    elif preset_obj.needs_key:
        data["api_key"] = getpass.getpass(f"{preset_obj.name} API key（输入不显示，直接回车跳过）: ").strip()
    if base_url:
        data["base_url"] = base_url
    if model:
        data["models"] = list(model)
    entry = ProviderStore().upsert(data)
    console.print(f"[green]已接入[/] {entry.name}（id: {entry.id}）。测试：[bold]uv run anima providers test {entry.id}[/]")


@providers_app.command("test")
def providers_test(provider_id: str, model: str = typer.Option(None), bot: str = typer.Option(None, help=BOT_HELP)) -> None:
    """Send a tiny request and report latency."""
    bot = _bot(bot)
    import time as _time

    from anima.llm import build_target
    from anima.llm.base import LLMError
    from anima.llm.registry import ProviderStore, Target

    store = ProviderStore()
    llm, why = build_target(store, Target(provider_id, model or ""), load_bot(bot).config.llm)
    if llm is None:
        raise typer.BadParameter(why)
    started = _time.perf_counter()
    try:
        result = asyncio.run(llm.complete("这是一次连通性测试。", "只回复两个字：在呢", max_tokens=32))
    except LLMError as exc:
        store.record_test(provider_id, {"ok": False, "error": str(exc), "model": llm.model})
        console.print(f"[red]✗ {exc}[/]")
        raise typer.Exit(1) from exc
    ms = int((_time.perf_counter() - started) * 1000)
    store.record_test(provider_id, {"ok": True, "latency_ms": ms, "reply": result.text[:40], "model": result.model})
    console.print(f"[green]✓[/] {result.model} · {ms} ms · 「{result.text.strip()[:40]}」")


@providers_app.command("use")
def providers_use(provider_id: str, model: str = typer.Option(None), side: str = typer.Option(None, help="后台用 provider:model"),
                  backup: str = typer.Option(None, help="备用 provider:model"), bot: str = typer.Option(None, help=BOT_HELP)) -> None:
    """Point a bot's brain at a provider (applies on the next start; the panel switches live)."""
    bot = _bot(bot)
    from anima.llm.registry import ProviderStore, Routing, Target, save_routing

    store = ProviderStore()
    entry = store.entry_for(provider_id)
    if entry is None:
        raise typer.BadParameter(f"不认识 {provider_id}")
    chosen = model or (entry.preset_obj.default_model if entry.preset_obj else "") or (entry.models[0] if entry.models else "")
    routing = Routing(Target(provider_id, chosen), Target.parse(side), [t for t in [Target.parse(backup)] if t])
    save_routing(load_bot(bot), routing)
    console.print(f"[green]{bot} 以后用[/] {entry.name} · {chosen}")


# ------------------------------------------------------------------ magpie


def _magpie_compose(*args: str) -> int:
    return subprocess.call(["docker", "compose", "-f", str(MAGPIE_DIR / "compose.yaml"), "--env-file", str(ENV_FILE), *args],
                           cwd=MAGPIE_DIR)


def _magpie(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "exec", MAGPIE_CONTAINER, "magpie", *args], capture_output=True, text=True)


def _gateway_models(key: str) -> list[str] | None:
    """Model ids the gateway serves with this key, or None if the key isn't accepted."""
    import httpx

    try:
        resp = httpx.get(f"{MAGPIE_GATEWAY}/models", headers={"Authorization": f"Bearer {key}"}, timeout=5)
    except httpx.HTTPError:
        return None
    return [m["id"] for m in resp.json().get("data", [])] if resp.status_code == 200 else None


def _magpie_web_key() -> str:
    from anima.llm.registry import env_lookup

    return env_lookup("MAGPIE_WEB_KEY")


@magpie_app.command("init")
def magpie_init() -> None:
    """Create the web-console key in .env (once)."""
    if not _magpie_web_key():
        _env_set("MAGPIE_WEB_KEY", secrets.token_hex(16))
    console.print("[green]magpie 准备好了。[/] 下一步：[bold]uv run anima magpie up[/]")


@magpie_app.command("up")
def magpie_up() -> None:
    """Start the gateway, then connect Anima to it with its own gateway key."""
    import time

    if not _magpie_web_key():
        magpie_init()
    if _magpie_compose("up", "-d") != 0:
        raise typer.Exit(1)
    for _ in range(60):
        status = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", MAGPIE_CONTAINER],
                                capture_output=True, text=True).stdout.strip()
        if status == "healthy":
            break
        time.sleep(1)
    magpie_connect()


@magpie_app.command("connect")
def magpie_connect() -> None:
    """Give Anima a gateway key (made inside magpie, saved in data/providers.json, never printed)."""
    from anima.llm.registry import ProviderStore

    store = ProviderStore()
    entry = store.get("magpie")
    key = store.resolve_key(entry)[0] if entry else ""
    models = _gateway_models(key) if key else None
    if models is None:
        out = _magpie("gateway-key", "add", "Anima")
        found = re.search(r"sk-magpie-[A-Za-z0-9_-]+", out.stdout + out.stderr)
        if not found:
            console.print(f"[red]没拿到网关密钥[/]：{escape((out.stderr or out.stdout).strip()[:300])}")
            raise typer.Exit(1)
        key = found.group()
        models = _gateway_models(key)
        if models is None:
            console.print("[red]新密钥被网关拒绝了[/]，看看 uv run anima magpie logs")
            raise typer.Exit(1)
    entry = store.upsert({"id": entry.id if entry else None, "preset": "magpie", "base_url": MAGPIE_GATEWAY,
                          "api_key": key, "models": models})
    ds = [m for m in models if m.split("/", 1)[0] in ("deepseek", "deepseek-ai")]
    console.print("[green]已接上 magpie[/]"
                  f"（网关里有 {len(models)} 个模型）。" + (
        f"DeepSeek 可用：{', '.join(ds)}，她没有自己的 DeepSeek key 时会自动走这里。" if ds else
        "magpie 里还没有 DeepSeek：[bold]uv run anima magpie open[/] 打开管理页添加。"))


@magpie_app.command("open")
def magpie_open() -> None:
    """Open magpie's web console (add providers and keys there)."""
    key = _magpie_web_key()
    if not key:
        raise typer.BadParameter("先运行 uv run anima magpie up")
    subprocess.call(["open", f"http://127.0.0.1:3430/?k={key}"])  # the key stays in the URL bar, not in this terminal


@magpie_app.command("status")
def magpie_status() -> None:
    """Container state, providers inside magpie, and what Anima sees."""
    from anima.llm.registry import ProviderStore

    state = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}} {{.State.Health.Status}}", MAGPIE_CONTAINER],
                           capture_output=True, text=True).stdout.strip() or "没有运行"
    console.print(f"容器：{state}")
    console.print(escape(_magpie("providers").stdout.strip() or "（读不到 provider 列表）"))
    entry = ProviderStore().get("magpie")
    models = _gateway_models(ProviderStore.resolve_key(entry)[0]) if entry else None
    console.print("Anima：" + (f"已接上，{len(models)} 个模型" if models is not None else "还没接上（uv run anima magpie connect）"))


@magpie_app.command("down")
def magpie_down() -> None:
    """Stop the gateway (providers and keys are kept)."""
    _magpie_compose("down")


@magpie_app.command("logs")
def magpie_logs(follow: bool = typer.Option(False, "-f/--no-follow")) -> None:
    """Show the gateway's log."""
    _magpie_compose("logs", "--tail", "200", *(["-f"] if follow else []))


@magpie_app.command("update")
def magpie_update() -> None:
    """Pull the newest magpie image and restart on it."""
    if _magpie_compose("pull") == 0:
        _magpie_compose("up", "-d")


# ------------------------------------------------------------------ launchd


def _label(bot: str) -> str:
    return f"ai.anima.{bot}"


def _plist_path(bot: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_label(bot)}.plist"


@service_app.command("install")
def service_install(bot: str = typer.Argument(None, help=BOT_HELP)) -> None:
    """Start the bot at login and restart it if it ever stops."""
    bot = _bot(bot)
    b = load_bot(bot)
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    logs = b.data_dir / "logs"
    logs.mkdir(exist_ok=True)
    plist = {
        "Label": _label(bot),
        "ProgramArguments": [uv, "run", "--project", str(REPO_ROOT), "anima", "run", bot],
        "WorkingDirectory": str(REPO_ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(logs / "service.out.log"),
        "StandardErrorPath": str(logs / "service.err.log"),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + str(Path.home() / ".local/bin")},
    }
    path = _plist_path(bot)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        plistlib.dump(plist, fh)
    subprocess.call(["launchctl", "bootout", f"gui/{os.getuid()}/{_label(bot)}"], stderr=subprocess.DEVNULL)
    subprocess.call(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)])
    console.print(f"[green]已安装[/] {path}\n日志：{logs}")


@service_app.command("uninstall")
def service_uninstall(bot: str = typer.Argument(None, help=BOT_HELP)) -> None:
    """Stop the background service and remove it."""
    bot = _bot(bot)
    subprocess.call(["launchctl", "bootout", f"gui/{os.getuid()}/{_label(bot)}"])
    _plist_path(bot).unlink(missing_ok=True)
    console.print("[green]已移除[/]")


@service_app.command("status")
def service_status(bot: str = typer.Argument(None, help=BOT_HELP)) -> None:
    """Is the background service running?"""
    bot = _bot(bot)
    out = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{_label(bot)}"], capture_output=True, text=True)
    if out.returncode != 0:
        console.print("没有安装后台服务")
        return
    state = next((ln.strip() for ln in out.stdout.splitlines() if ln.strip().startswith("state =")), "state = ?")
    pid = next((ln.strip() for ln in out.stdout.splitlines() if ln.strip().startswith("pid =")), "")
    console.print(f"{_label(bot)}: {state} {pid}")


if __name__ == "__main__":
    app()


# ------------------------------------------------------------------ personas & plugins


@persona_app.command("list")
def persona_list() -> None:
    """Every persona under bots/."""
    from anima import personas
    from anima.config import default_bot

    table = Table()
    for col in ("", "文件夹", "名字", "介绍"):
        table.add_column(col)
    chosen = default_bot()
    for p in personas.list_personas():
        table.add_row("★" if p["key"] == chosen else "", p["key"], p["name"], escape(p.get("tagline", ""))[:50])
    console.print(table)


@persona_app.command("use")
def persona_use(key: str) -> None:
    """Make a persona the default for `anima play` / `anima run` (a running one switches in the console)."""
    from anima.config import list_bots, set_default_bot

    if key not in list_bots():
        raise typer.BadParameter(f"没有人设 {key}")
    set_default_bot(key)
    console.print(f"[green]默认人设：{key}[/]")


@persona_app.command("export")
def persona_export(key: str, out: Path = typer.Option(None, help="输出文件，默认 <key>.anima.zip")) -> None:
    """Pack a persona (text and art only) into a .zip."""
    from anima import personas

    target = out or Path(f"{key}.anima.zip")
    target.write_bytes(personas.export_pack(key))
    console.print(f"[green]导出好了[/] → {target}")


@persona_app.command("import")
def persona_import(file: Path) -> None:
    """Import a persona pack (.zip) or a SillyTavern character card (.png / .json)."""
    from anima import personas
    from anima.core.cards import create_bot_from_card

    data = file.read_bytes()
    key = personas.import_pack(data) if data[:2] == b"PK" else create_bot_from_card(data).name
    console.print(f"[green]导入好了[/] → bots/{key}/")


@plugin_app.command("list")
def plugin_list(bot: str = typer.Option(None, help=BOT_HELP)) -> None:
    """Plugins found in plugins/ and data/plugins/, and which this persona uses."""
    from anima.plugin_host import discover

    enabled = set(load_bot(_bot(bot)).config.plugins)
    table = Table()
    for col in ("", "id", "名字", "类型", "来源", "说明"):
        table.add_column(col)
    for pid, info in discover().items():
        table.add_row("✓" if pid in enabled else "", pid, info.name, info.kind, info.source, escape(info.description)[:40])
    console.print(table)


def _toggle_plugin(bot: str, pid: str, on: bool) -> None:
    import tomlkit

    path = load_bot(bot).dir / "bot.toml"
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    doc["plugins"] = [p for p in (doc.get("plugins") or []) if p != pid] + ([pid] if on else [])
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


@plugin_app.command("enable")
def plugin_enable(pid: str, bot: str = typer.Option(None, help=BOT_HELP)) -> None:
    """Turn a plugin on for a persona (applies on the next start; the console does it live)."""
    from anima.plugin_host import discover

    if pid not in discover():
        raise typer.BadParameter(f"没有插件 {pid}；先 anima plugin install <地址>")
    _toggle_plugin(_bot(bot), pid, True)
    console.print(f"[green]{pid} 已启用[/]")


@plugin_app.command("disable")
def plugin_disable(pid: str, bot: str = typer.Option(None, help=BOT_HELP)) -> None:
    """Turn a plugin off for a persona."""
    _toggle_plugin(_bot(bot), pid, False)
    console.print(f"{pid} 已停用")


@plugin_app.command("install")
def plugin_install(source: str) -> None:
    """Install a plugin from a GitHub repository or zip link (Anima or AstrBot format). It runs on this computer."""
    from anima.plugin_host import install_from

    info = asyncio.run(install_from(source))
    console.print(f"[green]装好了[/] {info.name}（{info.kind}，id：{info.id}）→ data/plugins/{info.id}\n"
                  f"启用：[bold]uv run anima plugin enable {info.id}[/]")

