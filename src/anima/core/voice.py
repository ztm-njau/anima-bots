"""Her voice: short voice notes via Microsoft Edge neural TTS (free, no key)."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from loguru import logger

DEFAULT_VOICE = "zh-CN-XiaoyiNeural"  # lively young female voice


async def synthesize(text: str, out_dir: Path, voice: str = DEFAULT_VOICE, rate: str = "+6%", pitch: str = "+8Hz") -> Path | None:
    try:
        import edge_tts
    except ImportError:
        logger.warning("edge-tts not installed; voice notes disabled")
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()[:16]
    path = out_dir / f"{digest}.mp3"
    if not path.exists():
        try:
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(path))
        except Exception as exc:
            logger.warning("TTS failed: {}", exc)
            return None
    return path


def as_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()
