from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from certrecog.config import Settings
from certrecog.errors import MAX_BYTES, BusyError, RequestError
from certrecog.gate import Gate
from certrecog.service import (
    Incoming,
    Vision,
    log_result,
    prepare,
    recognize_pages,
)

logger = logging.getLogger("certrecog")


def create_app(vision: Vision, settings: Settings, gate: Gate | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.vision = vision
    app.state.settings = settings
    app.state.gate = gate or Gate()

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/recognize")
    async def recognize(request: Request) -> JSONResponse:
        started = time.perf_counter()
        try:
            files, hints = await _read_request(request)
            pages = prepare(files, hints)
        except RequestError as exc:
            logger.info("reject error_code=%s", exc.code)
            return JSONResponse(status_code=400, content=exc.body())
        try:
            items = await app.state.gate.run(
                lambda: recognize_pages(
                    pages,
                    app.state.vision,
                    timeout_s=app.state.settings.page_timeout_s,
                )
            )
        except BusyError as exc:
            logger.info("reject error_code=busy")
            return JSONResponse(status_code=429, content=exc.body())
        elapsed = time.perf_counter() - started
        log_result(len(pages), elapsed, items)
        _write_debug(app.state.settings.debug_dir, pages, items)
        return JSONResponse(status_code=200, content={"items": items})

    return app


async def _read_request(request: Request) -> tuple[list[Incoming], list[str]]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        raise RequestError("empty_request")
    try:
        form = await request.form()
    except Exception as exc:
        raise RequestError("empty_request") from exc
    raw_files = form.getlist("file")
    if not raw_files:
        raise RequestError("empty_request")
    files: list[Incoming] = []
    for part in raw_files:
        if not isinstance(part, UploadFile):
            raise RequestError("unsupported_type")
        data = await _read_limited(part)
        files.append(Incoming(filename=part.filename or "file", data=data))
    hints = [str(value) for value in form.getlist("hint")]
    return files, hints


async def _read_limited(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_BYTES:
            raise RequestError("file_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def _write_debug(debug_dir: Path | None, pages: list, items: list[dict]) -> None:
    if debug_dir is None:
        return
    folder = debug_dir / uuid.uuid4().hex
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for index, page in enumerate(pages, start=1):
            (folder / f"p{index}.png").write_bytes(page.png)
        (folder / "result.json").write_text(
            json.dumps({"items": items}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logger.info("debug write failed")
