from __future__ import annotations

MESSAGES = {
    "empty_request": "没有上传文件",
    "too_many_files": "文件超过 10 个",
    "too_many_pages": "页数超过 10",
    "file_too_large": "文件超过 8MB",
    "unsupported_type": "文件类型不支持",
    "bad_hint": "hint 不合法",
    "unreadable": "文件无法打开",
    "busy": "排队已满",
    "vision_timeout": "识别超时",
    "vision_failed": "识别失败",
}

MAX_FILES = 10
MAX_PAGES = 10
MAX_BYTES = 8 * 1024 * 1024
MAX_WAITING = 8
ALLOWED_HINTS = {"", "id_card", "diploma", "degree"}


class RequestError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def body(self) -> dict[str, str]:
        return {"error_code": self.code, "error": MESSAGES[self.code]}


class BusyError(Exception):
    def body(self) -> dict[str, str]:
        return {"error_code": "busy", "error": MESSAGES["busy"]}


class Unreadable(Exception):
    pass
