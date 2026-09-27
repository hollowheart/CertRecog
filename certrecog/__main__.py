from __future__ import annotations

import logging
import sys

import uvicorn

from certrecog.app import create_app
from certrecog.config import HOST, load_settings
from certrecog.llm import LlmVision


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings()
    if not settings.llm_api_key:
        print("缺少 LLM_API_KEY，拒绝启动", file=sys.stderr)
        raise SystemExit(1)
    uvicorn.run(
        create_app(LlmVision(settings), settings),
        host=HOST,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
