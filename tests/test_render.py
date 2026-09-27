from __future__ import annotations

import io

import pymupdf
from PIL import Image

from certrecog.errors import Unreadable
from certrecog.render import count_pages, render_pages, sniff


def test_png_is_one_page() -> None:
    data = _png()
    assert sniff(data) == "png"
    assert count_pages("png", data) == 1
    pages = render_pages("png", data)
    assert len(pages) == 1
    assert sniff(pages[0]) == "png"


def test_gif_uses_first_frame_only() -> None:
    data = _gif(frames=3)
    assert sniff(data) == "gif"
    assert count_pages("gif", data) == 1
    assert len(render_pages("gif", data)) == 1


def test_tiff_counts_every_frame() -> None:
    data = _tiff(frames=2)
    assert sniff(data) == "tiff"
    assert count_pages("tiff", data) == 2
    assert len(render_pages("tiff", data)) == 2


def test_truncated_jpeg_is_unreadable() -> None:
    try:
        count_pages("jpeg", b"\xff\xd8\xff\x00broken")
    except Unreadable:
        return
    raise AssertionError("expected Unreadable")


def test_pdf_page_count() -> None:
    data = _pdf(3)
    assert sniff(data) == "pdf"
    assert count_pages("pdf", data) == 3


def _png() -> bytes:
    image = Image.new("RGB", (4, 4), "white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _gif(frames: int) -> bytes:
    images = [Image.new("RGB", (4, 4), color) for color in ("red", "green", "blue")]
    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:frames],
        duration=50,
        loop=0,
    )
    return buf.getvalue()


def _tiff(frames: int) -> bytes:
    images = [Image.new("RGB", (4, 4), "white") for _ in range(frames)]
    buf = io.BytesIO()
    images[0].save(buf, format="TIFF", save_all=True, append_images=images[1:])
    return buf.getvalue()


def _pdf(pages: int) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=120, height=120)
    data = doc.tobytes()
    doc.close()
    return data
