from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"
DEFAULT_PORT = 8090
DEFAULT_LLM_HOST = (
    "https://llm-zkldt896zm36j3ro.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
)
DEFAULT_VISION_MODEL = "qwen-vl-plus"
PAGE_TIMEOUT_S = 120.0

_dotenv_loaded = False


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _port() -> int:
    raw = _env("CERTRECOG_PORT")
    if not raw:
        return DEFAULT_PORT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PORT
    if 1 <= value <= 65535:
        return value
    return DEFAULT_PORT


def _debug_dir() -> Path | None:
    raw = _env("CERTRECOG_DEBUG_DIR")
    if not raw:
        return None
    return Path(raw)


@dataclass(frozen=True)
class Settings:
    llm_api_key: str
    llm_api_host: str
    llm_vision_model: str
    port: int
    debug_dir: Path | None
    page_timeout_s: float = PAGE_TIMEOUT_S


def load_settings() -> Settings:
    global _dotenv_loaded
    if not _dotenv_loaded:
        load_dotenv(ROOT / ".env")
        _dotenv_loaded = True
    return Settings(
        llm_api_key=_env("LLM_API_KEY"),
        llm_api_host=_env("LLM_API_HOST", DEFAULT_LLM_HOST).rstrip("/"),
        llm_vision_model=_env("LLM_VISION_MODEL", DEFAULT_VISION_MODEL),
        port=_port(),
        debug_dir=_debug_dir(),
    )
