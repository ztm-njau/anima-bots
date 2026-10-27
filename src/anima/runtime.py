"""Boot one bot: memory, model, brain, life loop, adapters, and the local web server."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import signal
import socket
import sys

from loguru import logger

from anima.adapters.base import Adapter
from anima.config import Bot, load_bot
from anima.core.brain import Brain
from anima.core.life import Life
from anima.core.memory import Memory
from anima.llm import make_provider
from anima.llm.registry import ProviderStore

WEB_PLATFORMS = {"playground", "wechat"}


class AlreadyRunning(RuntimeError):
    """Another process is already this bot, or holds her web port."""


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def setup_logging(bot: Bot, verbose: bool = False) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<dim>{time:HH:mm:ss}</dim> <level>{level: <7}</level> {message}")
    log_dir = bot.data_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(log_dir / "anima.log", level="DEBUG", rotation="10 MB", retention=5, encoding="utf-8")


class Runtime:
    def __init__(self, bot_key: str, *, platforms: list[str] | None = None, fast: bool = False,
                 demo: bool = False, port: int | None = None, console: bool = False, verbose: bool = False):
        self.bot = load_bot(bot_key)
        self.platform_filter = platforms
        self.fast = fast
        self.demo = demo
        self.port = port
        self.console = console
        self.verbose = verbose
        self.adapters: dict[str, Adapter] = {}
        self.brain: Brain
        self.life: Life
        self.memory: Memory
        self.store: ProviderStore
        self._stop = asyncio.Event()

    def enabled_platforms(self) -> list[str]:
        if self.platform_filter is not None:
            return self.platform_filter
        return [name for name, pc in self.bot.config.platforms.items() if pc.enabled]

    def build_adapters(self) -> dict[str, Adapter]:
        cfg = self.bot.config
        adapters: dict[str, Adapter] = {}
        for name in self.enabled_platforms():
            pc = cfg.platform(name).extras()
            if name == "playground":
                from anima.adapters.playground import PlaygroundAdapter

                adapters[name] = PlaygroundAdapter()
            elif name == "qq":
                from anima.adapters.onebot import OneBotAdapter

                adapters[name] = OneBotAdapter(pc, "qq")
            elif name == "bilibili":
                from anima.adapters.bilibili import BilibiliAdapter

                adapters[name] = BilibiliAdapter(pc, self.bot.secrets_dir)
            elif name == "wechat":
                if pc.get("mode") == "onebot_bridge":
                    from anima.adapters.onebot import OneBotAdapter

                    adapters[name] = OneBotAdapter(pc, "wechat")
                else:
                    from anima.adapters.wechat import WeChatMPAdapter

                    adapters[name] = WeChatMPAdapter(pc)
            elif name == "douyin":
                from anima.adapters.douyin import DouyinAdapter

                adapters[name] = DouyinAdapter(pc, self.bot.data_dir)
            else:
                logger.warning("Unknown platform {!r} in bot.toml", name)
        if self.console:
            from anima.adapters.console import ConsoleAdapter

            adapters["console"] = ConsoleAdapter()
        return adapters

    async def setup(self) -> None:
        if not self.console:
            setup_logging(self.bot, self.verbose)
        self.memory = await Memory(self.bot.data_dir / "memory.db").open()
        self.store = ProviderStore()
        self.brain = Brain(self.bot, self.memory, make_provider(self.bot, force_fake=self.demo, store=self.store))
        if self.fast:
            self.brain.humanizer.scale = 0.0
        await self.brain.start()
        self.life = Life(self.brain)
        self.adapters = self.build_adapters()
        for adapter in self.adapters.values():
            self.brain.attach(adapter)
        from anima.plugins import PluginManager

        self.plugins = PluginManager(self.brain)
        self.brain.plugins = self.plugins

    def rebuild_llm(self) -> None:
        """Swap the brain's model in place after the provider panel changes something."""
        self.store.load()
        self.brain.llm = make_provider(self.bot, force_fake=self.demo, store=self.store)
        llm = self.brain.llm
        self.brain.trace.emit("llm", provider=llm.label, model=llm.model, note=getattr(llm, "note", ""))
        logger.info("Brain now runs on {} · {}", llm.label, llm.model)

    def claim(self) -> None:
        """One process per bot: two would share one memory file and answer every QQ message twice."""
        self._lock = (self.bot.data_dir / "anima.lock").open("w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunning(f"{self.bot.config.identity.display_name} 已经在另一个 anima 进程里运行了，先关掉那个再启动") from exc
        if WEB_PLATFORMS & set(self.enabled_platforms()):
            port = self.port or int(self.bot.config.platform("playground").extras().get("port", 8765))
            if port_in_use(port):
                raise AlreadyRunning(f"端口 {port} 已被占用（多半是另一个 anima play/run 还开着）。"
                                     f"关掉它，或换端口：--port {port + 1}")

    async def run(self) -> None:
        self.claim()
        await self.setup()
        tasks: list[asyncio.Task] = []
        for name, adapter in self.adapters.items():
            try:
                await adapter.start(self.brain)
            except Exception:
                logger.exception("Adapter {} failed to start", name)
        tasks.append(asyncio.create_task(self.life.run()))
        tasks.append(asyncio.create_task(self.plugins.start()))

        server = None
        if WEB_PLATFORMS & set(self.adapters):
            import uvicorn

            from anima.web import create_app

            port = self.port or int(self.bot.config.platform("playground").extras().get("port", 8765))
            server = uvicorn.Server(uvicorn.Config(create_app(self), host="127.0.0.1", port=port, log_level="warning"))
            tasks.append(asyncio.create_task(server.serve()))
            if "playground" in self.adapters:
                logger.info("Playground: http://127.0.0.1:{}", port)

        name = self.bot.config.identity.display_name
        logger.info("{} is up on: {} (model: {} {})", name, ", ".join(self.adapters) or "nothing",
                    self.brain.llm.name, self.brain.llm.model)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._stop.set)

        if self.console:
            await self.adapters["console"].repl(self)  # type: ignore[attr-defined]
        else:
            await self._stop.wait()

        logger.info("Shutting down…")
        if server:
            server.should_exit = True
        for adapter in self.adapters.values():
            with contextlib.suppress(Exception):
                await adapter.stop()
        with contextlib.suppress(Exception):
            await self.plugins.stop()
        await self.brain.stop()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.memory.close()
