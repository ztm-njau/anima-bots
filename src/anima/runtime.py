"""Boot one bot: memory, model, brain, life loop, adapters, and the local web server."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys

from loguru import logger

from anima.adapters.base import Adapter
from anima.config import Bot, load_bot
from anima.core.brain import Brain
from anima.core.life import Life
from anima.core.memory import Memory
from anima.llm import make_provider

WEB_PLATFORMS = {"playground", "wechat"}


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
        self.brain = Brain(self.bot, self.memory, make_provider(self.bot, force_fake=self.demo))
        if self.fast:
            self.brain.humanizer.scale = 0.0
        await self.brain.start()
        self.life = Life(self.brain)
        self.adapters = self.build_adapters()
        for adapter in self.adapters.values():
            self.brain.attach(adapter)

    async def run(self) -> None:
        await self.setup()
        tasks: list[asyncio.Task] = []
        for name, adapter in self.adapters.items():
            try:
                await adapter.start(self.brain)
            except Exception:
                logger.exception("Adapter {} failed to start", name)
        tasks.append(asyncio.create_task(self.life.run()))

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
        await self.brain.stop()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.memory.close()
