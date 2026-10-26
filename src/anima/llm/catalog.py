"""Provider presets: where each model vendor lives and how to talk to it.

Endpoints and model ids follow the vendors' own docs as mirrored by cc-switch's preset catalog
(farion1231/cc-switch), checked October 2026. Model lists are a starting point; the panel can
fetch the live list from each provider. Prices are reference prices per million tokens; edit
them in the panel if a vendor changes them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

Protocol = Literal["openai", "anthropic"]
Group = Literal["gateway", "cn", "global", "aggregator", "local", "custom"]


@dataclass
class Price:
    """Per million tokens. ``peak_multiplier`` applies inside ``peak_hours`` (Beijing time, Mon-Fri)."""

    input: float
    cached: float
    output: float
    currency: str = "CNY"
    peak_multiplier: float = 1.0
    peak_hours: list[str] = field(default_factory=list)  # e.g. ["09:00-12:00", "14:00-18:00"]
    write_multiplier: float = 1.0  # prompt-cache writes, relative to input (Claude: 1.25)

    def is_peak(self, when: datetime | None = None) -> bool:
        if self.peak_multiplier == 1.0 or not self.peak_hours:
            return False
        when = (when or datetime.now(ZoneInfo("Asia/Shanghai"))).astimezone(ZoneInfo("Asia/Shanghai"))
        if when.weekday() >= 5:
            return False
        hm = when.strftime("%H:%M")
        return any(span.split("-")[0] <= hm < span.split("-")[1] for span in self.peak_hours)

    def cost(self, fresh_input: int, cached_input: int, output: int, cache_write: int = 0,
             when: datetime | None = None) -> float:
        k = self.peak_multiplier if self.is_peak(when) else 1.0
        total = (fresh_input * self.input + cached_input * self.cached + output * self.output
                 + cache_write * self.input * self.write_multiplier)
        return total * k / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Price | None:
        if not data:
            return None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Preset:
    id: str
    name: str
    protocol: Protocol
    base_url: str
    group: Group
    color: str
    models: list[str]
    default_model: str = ""
    env_keys: list[str] = field(default_factory=list)
    key_url: str = ""
    docs_url: str = ""
    needs_key: bool = True
    vision_models: list[str] = field(default_factory=list)
    # Request extras for chat replies (temperature, provider-specific body fields).
    params: dict[str, Any] = field(default_factory=dict)
    prices: dict[str, Price] = field(default_factory=dict)  # model id -> price
    note: str = ""

    @property
    def initials(self) -> str:
        letters = [c for c in self.name if c.isalnum()]
        return "".join(letters[:2]).upper() if letters else "?"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["prices"] = {m: p.to_dict() for m, p in self.prices.items()}
        d["initials"] = self.initials
        return d


_DS_PEAK = ["09:00-12:00", "14:00-18:00"]

PRESETS: list[Preset] = [
    Preset(
        "magpie", "magpie 网关", "openai", "http://127.0.0.1:3425/v1", "gateway", "#1C1C1E",
        [], "", ["MAGPIE_GATEWAY_KEY", "MAGPIE_API_KEY"], "https://usemagpie.ai", "https://usemagpie.ai/docs/start",
        needs_key=False,
        note="yetone/magpie 的本机网关：key 留在 magpie 里，模型写作 provider/model，支持路由组、多账号自动切换和用量统计",
    ),
    Preset(
        "deepseek", "DeepSeek", "openai", "https://api.deepseek.com", "cn", "#4D6BFE",
        ["deepseek-flash", "deepseek-v4-pro"], "deepseek-flash", ["DEEPSEEK_API_KEY"],
        "https://platform.deepseek.com/api_keys", "https://api-docs.deepseek.com/zh-cn/",
        vision_models=["deepseek-flash"],
        # Thinking is on by default for these models; a chatty bot wants quick replies.
        params={"temperature": 1.3, "extra_body": {"thinking": {"type": "disabled"}}},
        prices={
            "deepseek-flash": Price(1.0, 0.02, 4.0, "CNY", 2.0, _DS_PEAK),
            "deepseek-v4-pro": Price(4.5, 0.15, 13.5, "CNY", 2.0, _DS_PEAK),
        },
        note="高峰（北京时间工作日 9-12、14-18 点）价格翻倍；晚上聊天最便宜",
    ),
    Preset(
        "kimi", "Kimi 月之暗面", "openai", "https://api.moonshot.cn/v1", "cn", "#16191E",
        ["kimi-k3.1-pro", "kimi-k3"], "kimi-k3", ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
        "https://platform.moonshot.cn/console/api-keys", "https://platform.moonshot.cn/docs",
    ),
    Preset(
        "zhipu", "智谱 GLM", "openai", "https://open.bigmodel.cn/api/paas/v4", "cn", "#0F62FE",
        ["glm-5.3", "glm-5.3-flash"], "glm-5.3-flash", ["ZHIPUAI_API_KEY", "ZHIPU_API_KEY", "GLM_API_KEY"],
        "https://open.bigmodel.cn/usercenter/apikeys", "https://docs.bigmodel.cn",
    ),
    Preset(
        "qwen", "通义千问 百炼", "openai", "https://dashscope.aliyuncs.com/compatible-mode/v1", "cn", "#624AFF",
        ["qwen3.8-max", "qwen3.8-flash"], "qwen3.8-flash", ["DASHSCOPE_API_KEY", "QWEN_API_KEY"],
        "https://bailian.console.aliyun.com/?apiKey=1", "https://help.aliyun.com/zh/model-studio/",
    ),
    Preset(
        "doubao", "豆包 火山方舟", "openai", "https://ark.cn-beijing.volces.com/api/v3", "cn", "#3370FF",
        ["doubao-seed-2-1-pro-260915"], "doubao-seed-2-1-pro-260915", ["ARK_API_KEY", "VOLCENGINE_API_KEY"],
        "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey", "https://www.volcengine.com/docs/82379",
    ),
    Preset(
        "minimax", "MiniMax", "openai", "https://api.minimax.cn/v1", "cn", "#FF6B6B",
        ["MiniMax-M3.1-Flash", "MiniMax-M3"], "MiniMax-M3.1-Flash", ["MINIMAX_API_KEY"],
        "https://platform.minimax.cn", "https://platform.minimax.cn/docs",
    ),
    Preset(
        "stepfun", "阶跃星辰", "openai", "https://api.stepfun.com/v1", "cn", "#005AFF",
        ["step-3.7-flash", "step-5-preview"], "step-3.7-flash", ["STEPFUN_API_KEY", "STEP_API_KEY"],
        "https://platform.stepfun.com/interface-key", "https://platform.stepfun.com/docs",
    ),
    Preset(
        "mimo", "小米 MiMo", "openai", "https://api.xiaomimimo.com/v1", "cn", "#FF6900",
        ["mimo-v2.6-flash", "mimo-v2.6-pro"], "mimo-v2.6-flash", ["MIMO_API_KEY", "XIAOMI_API_KEY"],
        "https://platform.xiaomimimo.com/#/console/api-keys",
    ),
    Preset(
        "siliconflow", "硅基流动", "openai", "https://api.siliconflow.cn/v1", "aggregator", "#6E29F6",
        ["deepseek-ai/DeepSeek-V4-Flash"], "deepseek-ai/DeepSeek-V4-Flash", ["SILICONFLOW_API_KEY"],
        "https://cloud.siliconflow.cn/account/ak", "https://docs.siliconflow.cn",
    ),
    Preset(
        "modelscope", "魔搭 ModelScope", "openai", "https://api-inference.modelscope.cn/v1", "aggregator", "#624AFF",
        ["deepseek-ai/DeepSeek-V4.1-Flash", "ZhipuAI/GLM-5.2"], "deepseek-ai/DeepSeek-V4.1-Flash",
        ["MODELSCOPE_API_KEY", "MODELSCOPE_TOKEN"], "https://modelscope.cn/my/myaccesstoken",
        note="每天有免费调用额度",
    ),
    Preset(
        "openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1", "aggregator", "#6366F1",
        ["anthropic/claude-opus-5.5", "deepseek/deepseek-v4.1-flash"], "deepseek/deepseek-v4.1-flash",
        ["OPENROUTER_API_KEY"], "https://openrouter.ai/keys", "https://openrouter.ai/docs",
    ),
    Preset(
        "anthropic", "Claude", "anthropic", "https://api.anthropic.com", "global", "#D97757",
        ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"], "claude-opus-5-5", ["ANTHROPIC_API_KEY"],
        "https://platform.claude.com/settings/keys", "https://platform.claude.com/docs",
        vision_models=["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
        prices={
            "claude-opus-5-5": Price(4.0, 0.20, 20.0, "USD", write_multiplier=1.25),
            "claude-sonnet-5-5": Price(2.0, 0.20, 10.0, "USD", write_multiplier=1.25),
            "claude-haiku-5-5": Price(0.10, 0.01, 0.50, "USD", write_multiplier=1.25),
        },
        note="原生接入：提示缓存、联网搜索、拒答自动兜底",
    ),
    Preset(
        "openai", "OpenAI", "openai", "https://api.openai.com/v1", "global", "#10A37F",
        ["gpt-6.1-sol", "gpt-6-astra"], "gpt-6-astra", ["OPENAI_API_KEY"], "https://platform.openai.com/api-keys",
    ),
    Preset(
        "gemini", "Gemini", "openai", "https://generativelanguage.googleapis.com/v1beta/openai", "global", "#4285F4",
        [], "", ["GEMINI_API_KEY", "GOOGLE_API_KEY"], "https://aistudio.google.com/apikey",
    ),
    Preset(
        "ollama", "Ollama", "openai", "http://127.0.0.1:11434/v1", "local", "#111111",
        [], "", needs_key=False, docs_url="https://ollama.com", note="本机运行，免费、离线",
    ),
    Preset(
        "lmstudio", "LM Studio", "openai", "http://127.0.0.1:1234/v1", "local", "#4F46E5",
        [], "", needs_key=False, docs_url="https://lmstudio.ai", note="本机运行，免费、离线",
    ),
    Preset(
        "custom", "自定义（OpenAI 兼容）", "openai", "", "custom", "#8A8F98",
        [], "", note="任何兼容 OpenAI Chat Completions 的接口：中转站、vLLM、llama.cpp……",
    ),
]

PRESET_BY_ID = {p.id: p for p in PRESETS}
GROUP_NAMES = {"gateway": "本机网关", "cn": "国内官方", "aggregator": "聚合平台", "global": "海外官方",
               "local": "本机模型", "custom": "自定义"}
GATEWAYS = {"magpie"}  # serve other vendors' models as "vendor/model"

# How gateways and aggregators spell vendors in "vendor/model" ids.
VENDOR_ALIASES = {
    "deepseek": "deepseek", "deepseek-ai": "deepseek",
    "moonshot": "kimi", "moonshotai": "kimi", "kimi": "kimi",
    "zhipu": "zhipu", "zhipuai": "zhipu", "zai": "zhipu", "zai-org": "zhipu", "z-ai": "zhipu", "glm": "zhipu",
    "qwen": "qwen", "dashscope": "qwen", "bailian": "qwen", "alibaba": "qwen",
    "doubao": "doubao", "volcengine": "doubao", "ark": "doubao",
    "minimax": "minimax", "minimaxai": "minimax", "stepfun": "stepfun", "mimo": "mimo", "xiaomi": "mimo",
    "anthropic": "anthropic", "claude": "anthropic", "openai": "openai", "gemini": "gemini", "google": "gemini",
    "ollama": "ollama", "lmstudio": "lmstudio",
}


def preset(preset_id: str) -> Preset | None:
    return PRESET_BY_ID.get(preset_id)


def vendor_of(model: str) -> tuple[Preset | None, str]:
    """``"deepseek/deepseek-flash"`` -> (the DeepSeek preset, ``"deepseek-flash"``)."""
    vendor, sep, bare = model.partition("/")
    if not sep:
        return None, model
    return PRESET_BY_ID.get(VENDOR_ALIASES.get(vendor.lower(), "")), bare
