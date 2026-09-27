from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from certrecog.errors import (
    ALLOWED_HINTS,
    MAX_BYTES,
    MAX_FILES,
    MAX_PAGES,
    RequestError,
    Unreadable,
)
from certrecog.llm import SYSTEM, user_text
from certrecog.render import count_pages, render_pages, sniff
from certrecog.rules import items_from_model, make_item

logger = logging.getLogger("certrecog")


class Vision(Protocol):
    def complete(self, system: str, user: str, png: bytes) -> str: ...


@dataclass(frozen=True)
class Incoming:
    filename: str
    data: bytes


@dataclass(frozen=True)
class Page:
    filename: str
    page: int
    hint: str
    png: bytes


def check_hints(hints: list[str], file_count: int) -> list[str]:
    if not hints:
        return [""] * file_count
    if len(hints) != file_count:
        raise RequestError("bad_hint")
    cleaned: list[str] = []
    for hint in hints:
        text = hint.strip()
        if text not in ALLOWED_HINTS:
            raise RequestError("bad_hint")
        cleaned.append(text)
    return cleaned


def prepare(files: list[Incoming], hints: list[str]) -> list[Page]:
    if not files:
        raise RequestError("empty_request")
    if len(files) > MAX_FILES:
        raise RequestError("too_many_files")
    for item in files:
        if len(item.data) > MAX_BYTES:
            raise RequestError("file_too_large")
    kinds: list[str] = []
    for item in files:
        kind = sniff(item.data)
        if kind is None:
            raise RequestError("unsupported_type")
        kinds.append(kind)
    hints = check_hints(hints, len(files))
    counts: list[int] = []
    for item, kind in zip(files, kinds):
        try:
            counts.append(count_pages(kind, item.data))
        except Unreadable as exc:
            raise RequestError("unreadable") from exc
    if sum(counts) > MAX_PAGES:
        raise RequestError("too_many_pages")
    pages: list[Page] = []
    for item, kind, hint in zip(files, kinds, hints):
        try:
            pngs = render_pages(kind, item.data)
        except Unreadable as exc:
            raise RequestError("unreadable") from exc
        for index, png in enumerate(pngs, start=1):
            pages.append(
                Page(filename=item.filename or "file", page=index, hint=hint, png=png)
            )
    if len(pages) > MAX_PAGES:
        raise RequestError("too_many_pages")
    return pages


async def recognize_pages(
    pages: list[Page],
    vision: Vision,
    *,
    timeout_s: float,
) -> list[dict]:
    items: list[dict] = []
    for page in pages:
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(
                    vision.complete, SYSTEM, user_text(page.hint), page.png
                ),
                timeout=timeout_s,
            )
        except TimeoutError:
            logger.info("vision_timeout")
            items.append(_error_item(page, "vision_timeout"))
            continue
        except Exception as exc:
            logger.info("vision_failed %s", type(exc).__name__)
            items.append(_error_item(page, "vision_failed"))
            continue
        parsed = items_from_model(
            raw, filename=page.filename, page=page.page, hint=page.hint
        )
        if parsed is None:
            logger.info("vision_failed ParseError")
            items.append(_error_item(page, "vision_failed"))
            continue
        items.extend(parsed)
    return items


def _error_item(page: Page, code: str) -> dict:
    return make_item(
        filename=page.filename,
        page=page.page,
        hint=page.hint,
        error_code=code,
    )


def log_result(page_count: int, elapsed: float, items: list[dict]) -> None:
    types = [str(item.get("doc_type") or "") for item in items if item.get("doc_type")]
    codes = [
        str(item.get("error_code") or "") for item in items if item.get("error_code")
    ]
    logger.info(
        "recognize pages=%s elapsed=%.3fs types=%s errors=%s",
        page_count,
        elapsed,
        ",".join(types),
        ",".join(codes),
    )
