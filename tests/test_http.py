from __future__ import annotations

import asyncio
import io
import json
import logging
import threading

import httpx
import pymupdf
import pytest
from PIL import Image
from starlette.testclient import TestClient

from certrecog.app import create_app
from certrecog.config import HOST, Settings
from certrecog.errors import MAX_BYTES
from certrecog.gate import Gate
from certrecog.service import Vision

ID18 = "110101199001011234"
NAME = "张三特例名"


def test_health_and_empty_request() -> None:
    asyncio.run(_health_and_empty())


def test_rejects_bad_uploads_before_vision() -> None:
    asyncio.run(_rejects_bad_uploads())


def test_recognizes_page_and_keeps_going_after_timeout() -> None:
    asyncio.run(_recognizes_and_timeout())


def test_queue_returns_429_and_health_stays_open() -> None:
    asyncio.run(_queue_busy())


def test_debug_dir_writes_pages_without_logging_pii(tmp_path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="certrecog")
    asyncio.run(_debug(tmp_path, caplog))


def test_main_binds_localhost_and_refuses_missing_key(monkeypatch) -> None:
    from certrecog.__main__ import main

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        "certrecog.__main__.load_settings",
        lambda: Settings(
            llm_api_key="",
            llm_api_host="http://127.0.0.1",
            llm_vision_model="qwen-vl-plus",
            port=8090,
            debug_dir=None,
        ),
    )
    with pytest.raises(SystemExit):
        main()

    captured: dict[str, object] = {}

    def fake_run(app, host, port, log_level) -> None:
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("certrecog.__main__.uvicorn.run", fake_run)
    monkeypatch.setattr(
        "certrecog.__main__.load_settings",
        lambda: Settings(
            llm_api_key="k",
            llm_api_host="http://127.0.0.1",
            llm_vision_model="qwen-vl-plus",
            port=8091,
            debug_dir=None,
        ),
    )
    main()
    assert captured["host"] == HOST == "127.0.0.1"
    assert captured["port"] == 8091


async def _health_and_empty() -> None:
    vision = ScriptedVision(['{"documents":[]}'])
    app = create_app(vision, _settings())
    async with _client(app) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"ok": True}
        empty = await client.post("/recognize")
        assert empty.status_code == 400
        assert empty.json()["error_code"] == "empty_request"
    assert vision.calls == 0


async def _rejects_bad_uploads() -> None:
    vision = ScriptedVision([])
    app = create_app(vision, _settings())
    png = _png()
    async with _client(app) as client:
        bad_type = await client.post(
            "/recognize", files=[("file", ("a.txt", b"hello", "text/plain"))]
        )
        assert bad_type.json()["error_code"] == "unsupported_type"

        huge = b"x" * (MAX_BYTES + 1)
        too_big = await client.post(
            "/recognize", files=[("file", ("a.png", huge, "image/png"))]
        )
        assert too_big.json()["error_code"] == "file_too_large"

        broken = await client.post(
            "/recognize",
            files=[("file", ("a.jpg", b"\xff\xd8\xff\x00broken", "image/jpeg"))],
        )
        assert broken.json()["error_code"] == "unreadable"

        too_many = await client.post(
            "/recognize",
            files=[("file", (f"{i}.png", png, "image/png")) for i in range(11)],
        )
        assert too_many.json()["error_code"] == "too_many_files"

        pages = await client.post(
            "/recognize",
            files=[
                ("file", ("a.pdf", _pdf(6), "application/pdf")),
                ("file", ("b.pdf", _pdf(5), "application/pdf")),
            ],
        )
        assert pages.json()["error_code"] == "too_many_pages"

        hint = await client.post(
            "/recognize",
            data={"hint": "passport"},
            files=[("file", ("a.png", png, "image/png"))],
        )
        assert hint.json()["error_code"] == "bad_hint"

        mismatch = await client.post(
            "/recognize",
            data={"hint": "diploma"},
            files=[
                ("file", ("a.png", png, "image/png")),
                ("file", ("b.png", png, "image/png")),
            ],
        )
        assert mismatch.json()["error_code"] == "bad_hint"
        assert vision.calls == 0


async def _recognizes_and_timeout() -> None:
    degree = {
        "name": NAME,
        "cert_title": "学士学位证书",
        "cert_no": "10006120010501471",
        "enter_date": "一九九七年九月",
        "graduate_date": "二〇〇〇年七月",
        "xuezhi": "四年",
    }
    vision = ScriptedVision(
        [
            json.dumps(
                {
                    "documents": [
                        {"name": NAME, "id_no": ID18},
                        degree,
                    ]
                },
                ensure_ascii=False,
            ),
            "SLEEP",
            json.dumps({"documents": [degree]}, ensure_ascii=False),
        ]
    )
    app = create_app(vision, _settings(page_timeout_s=0.05))
    async with _client(app) as client:
        ok = await client.post(
            "/recognize",
            data={"hint": "diploma"},
            files=[("file", ("both.png", _png(), "image/png"))],
        )
        body = ok.json()
        assert ok.status_code == 200
        assert [item["doc_type"] for item in body["items"]] == ["id_card", "degree"]
        assert body["items"][1]["hint"] == "diploma"
        assert body["items"][1]["graduate_date"] == "2001年07月01日"
        assert "仅供参考" in vision.users[0]

        timed = await client.post(
            "/recognize",
            files=[("file", ("two.pdf", _pdf(2), "application/pdf"))],
        )
        items = timed.json()["items"]
        assert timed.status_code == 200
        assert items[0]["error_code"] == "vision_timeout"
        assert items[0]["doc_type"] == ""
        assert items[0]["page"] == 1
        assert items[1]["doc_type"] == "degree"
        assert items[1]["page"] == 2


async def _queue_busy() -> None:
    vision = BlockingVision()
    gate = Gate(max_waiting=8)
    app = create_app(vision, _settings(), gate)
    png = _png()

    async def post(client: httpx.AsyncClient) -> httpx.Response:
        return await client.post(
            "/recognize", files=[("file", ("a.png", png, "image/png"))]
        )

    async with _client(app) as client:
        first = asyncio.create_task(post(client))
        await _wait(vision.entered)
        waiters = [asyncio.create_task(post(client)) for _ in range(8)]
        await _wait_value(lambda: gate.waiting == 8)
        health = await client.get("/health")
        rejected = await post(client)
        assert health.status_code == 200
        assert rejected.status_code == 429
        assert rejected.json()["error_code"] == "busy"
        vision.release.set()
        first_resp = await first
        waited = await asyncio.gather(*waiters)
    assert first_resp.status_code == 200
    assert all(resp.status_code == 200 for resp in waited)


async def _debug(tmp_path, caplog) -> None:
    vision = ScriptedVision(
        [
            json.dumps(
                {"documents": [{"name": NAME, "id_no": ID18}]},
                ensure_ascii=False,
            )
        ]
    )
    app = create_app(vision, _settings(debug_dir=tmp_path))
    async with _client(app) as client:
        resp = await client.post(
            "/recognize",
            files=[("file", ("id.png", _png(), "image/png"))],
        )
    assert resp.status_code == 200
    assert ID18 not in caplog.text
    assert NAME not in caplog.text
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    result = json.loads((written[0] / "result.json").read_text(encoding="utf-8"))
    assert result["items"][0]["id_no"] == ID18
    assert (written[0] / "p1.png").is_file()


def _settings(**changes) -> Settings:
    base = Settings(
        llm_api_key="test",
        llm_api_host="http://127.0.0.1",
        llm_vision_model="fake",
        port=8090,
        debug_dir=None,
    )
    if not changes:
        return base
    from dataclasses import replace

    return replace(base, **changes)


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


class ScriptedVision:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.users: list[str] = []
        self.calls = 0

    def complete(self, system: str, user: str, png: bytes) -> str:
        self.calls += 1
        self.users.append(user)
        reply = self._replies.pop(0)
        if reply == "SLEEP":
            import time

            time.sleep(0.4)
            return '{"documents":[]}'
        return reply


class BlockingVision:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def complete(self, system: str, user: str, png: bytes) -> str:
        self.calls += 1
        if self.calls == 1:
            self.entered.set()
            assert self.release.wait(timeout=5)
        return '{"documents":[]}'


async def _wait(event: threading.Event) -> None:
    for _ in range(200):
        if event.is_set():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timed out")


async def _wait_value(ready) -> None:
    for _ in range(200):
        if ready():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timed out")


def _multipart(
    files: list[tuple[str, bytes]], hints: list[str]
) -> tuple[bytes, str]:
    boundary = "----certrecog"
    chunks: list[bytes] = []
    for filename, payload in files:
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode()
            + payload
            + b"\r\n"
        )
    for hint in hints:
        chunks.append(
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="hint"\r\n\r\n'
                f"{hint}\r\n"
            ).encode()
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _png() -> bytes:
    image = Image.new("RGB", (4, 4), "white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _pdf(pages: int) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=80, height=80)
    data = doc.tobytes()
    doc.close()
    return data


def test_repeated_hints_align_with_files() -> None:
    vision = ScriptedVision(['{"documents":[]}', '{"documents":[]}'])
    app = create_app(vision, _settings())
    png = _png()
    body, content_type = _multipart(
        files=[("a.png", png), ("b.png", png)],
        hints=["id_card", "degree"],
    )
    with TestClient(app) as client:
        resp = client.post(
            "/recognize",
            content=body,
            headers={"content-type": content_type},
        )
    assert resp.status_code == 200
    assert "id_card" in vision.users[0]
    assert "degree" in vision.users[1]


def test_vision_protocol_accepts_scripted() -> None:
    vision: Vision = ScriptedVision(['{"documents":[]}'])
    assert vision.complete("s", "u", b"png") == '{"documents":[]}'
