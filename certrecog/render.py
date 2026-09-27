from __future__ import annotations

import io

import pymupdf
from PIL import Image

from certrecog.errors import Unreadable

Kind = str
_RASTER = {"jpeg", "png", "webp", "bmp"}
_DPI_SCALE = 150 / 72


def sniff(data: bytes) -> Kind | None:
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"BM"):
        return "bmp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def count_pages(kind: Kind, data: bytes) -> int:
    if kind == "pdf":
        return _vector_count(data, "pdf")
    if kind == "tiff":
        return _vector_count(data, "tiff")
    if kind == "gif" or kind in _RASTER:
        _open_pillow(data)
        return 1
    raise Unreadable()


def render_pages(kind: Kind, data: bytes) -> list[bytes]:
    if kind == "pdf":
        return _vector_pngs(data, "pdf")
    if kind == "tiff":
        return _vector_pngs(data, "tiff")
    image = _open_pillow(data)
    if kind == "gif":
        image.seek(0)
    return [_png_bytes(image)]


def _vector_count(data: bytes, filetype: str) -> int:
    doc = _open_vector(data, filetype)
    try:
        count = doc.page_count
    finally:
        doc.close()
    if count < 1:
        raise Unreadable()
    return count


def _vector_pngs(data: bytes, filetype: str) -> list[bytes]:
    doc = _open_vector(data, filetype)
    matrix = pymupdf.Matrix(_DPI_SCALE, _DPI_SCALE)
    pages: list[bytes] = []
    try:
        if doc.page_count < 1:
            raise Unreadable()
        for index in range(doc.page_count):
            pix = doc[index].get_pixmap(matrix=matrix, alpha=False)
            pages.append(pix.tobytes("png"))
    finally:
        doc.close()
    return pages


def _open_vector(data: bytes, filetype: str) -> pymupdf.Document:
    try:
        doc = pymupdf.open(stream=data, filetype=filetype)
    except Exception as exc:
        raise Unreadable() from exc
    return doc


def _open_pillow(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise Unreadable() from exc
    return image


def _png_bytes(image: Image.Image) -> bytes:
    frame = image.convert("RGB")
    buf = io.BytesIO()
    frame.save(buf, format="PNG")
    return buf.getvalue()
