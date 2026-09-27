from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from certrecog.errors import MESSAGES

_ID18 = re.compile(
    r"^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dX]$"
)
_ID15 = re.compile(
    r"^[1-9]\d{5}\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}$"
)
_DATE_CANON = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$")
_DATE_YM = re.compile(r"^(\d{4})年(\d{1,2})月$")
_DATE_YMD_SEP = re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$")
_DATE_YMD8 = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_DIGIT_LIKE = {
    "零": "0",
    "〇": "0",
    "○": "0",
    "Ｏ": "0",
    "O": "0",
    "o": "0",
    "一": "1",
    "二": "2",
    "两": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}

BUSINESS_FIELDS = (
    "name",
    "id_no",
    "cert_no",
    "cert_title",
    "university",
    "major",
    "level",
    "xuezhi",
    "enter_date",
    "graduate_date",
)


def normalize_id_no(value: str) -> str:
    """只接受 18 位（末位可为 X）或旧版 15 位身份证号。出生日期、证书编号等直接丢掉。"""
    text = re.sub(r"[\s\-]", "", (value or "")).upper()
    if _ID18.fullmatch(text) or _ID15.fullmatch(text):
        return text
    return ""


def _prep_date(value: str) -> str:
    text = (
        (value or "")
        .strip()
        .replace("号", "日")
        .replace(" ", "")
        .replace("\u3000", "")
        .replace("公元", "")
    )
    return text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def normalize_cn_date(value: str) -> str:
    """把入学/毕业日期收成 1997年09月01日。缺日则日为 01。无法解析则原样返回。"""
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = _parse_cn_date(_prep_date(raw))
    return parsed or raw


def _fmt_cn_date(year: int, month: int, day: int) -> str | None:
    try:
        date(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}年{month:02d}月{day:02d}日"


def _digit_like(ch: str) -> str | None:
    if ch.isdigit():
        return ch
    return _DIGIT_LIKE.get(ch)


def _cn_small_int(text: str) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    text = text.replace("廿", "二十")
    mapped = "".join(_digit_like(c) or c for c in text)
    if mapped.isdigit():
        return int(mapped)
    if mapped == "十":
        return 10
    if mapped.startswith("十") and mapped[1:].isdigit():
        return 10 + int(mapped[1:])
    if "十" in mapped:
        left, right = mapped.split("十", 1)
        tens = int(left) if left.isdigit() else 1
        ones = int(right) if right.isdigit() else 0
        return tens * 10 + ones
    return None


def _parse_cn_date(text: str) -> str | None:
    match = _DATE_CANON.fullmatch(text)
    if match:
        return _fmt_cn_date(int(match[1]), int(match[2]), int(match[3]))
    match = _DATE_YM.fullmatch(text)
    if match:
        return _fmt_cn_date(int(match[1]), int(match[2]), 1)
    match = _DATE_YMD_SEP.fullmatch(text)
    if match:
        return _fmt_cn_date(int(match[1]), int(match[2]), int(match[3]))
    match = _DATE_YMD8.fullmatch(text)
    if match:
        return _fmt_cn_date(int(match[1]), int(match[2]), int(match[3]))

    rest = text
    year_digits: list[str] = []
    for ch in rest:
        digit = _digit_like(ch)
        if digit is None:
            break
        year_digits.append(digit)
    if len(year_digits) != 4 or rest[4:5] != "年":
        return None
    year = int("".join(year_digits))
    rest = rest[5:]
    if "月" not in rest:
        return None
    month_s, rest = rest.split("月", 1)
    month = _cn_small_int(month_s)
    if not month:
        return None
    day = 1
    if rest:
        rest = rest.removesuffix("日")
        if rest:
            parsed_day = _cn_small_int(rest)
            if not parsed_day:
                return None
            day = parsed_day
    return _fmt_cn_date(year, month, day)


def _date_year(value: str) -> int | None:
    text = normalize_cn_date(value)
    match = re.match(r"^(\d{4})年", text)
    return int(match.group(1)) if match else None


def _parse_xuezhi_years(value: str) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    match = re.search(r"([一二两三四五六七八九十0-9]+)年", text)
    if match:
        years = _cn_small_int(match.group(1))
        if years and 1 <= years <= 8:
            return years
    match = re.search(r"([1-8])", text)
    if match:
        return int(match.group(1))
    return None


def _years_in_cert_no(cert_no: str) -> list[int]:
    found: list[int] = []
    for match in re.finditer(r"(?:19|20)\d{2}", cert_no or ""):
        year = int(match.group(0))
        if 1980 <= year <= 2035:
            found.append(year)
    return found


def _replace_date_year(value: str, year: int) -> str:
    text = normalize_cn_date(value)
    match = _DATE_CANON.fullmatch(text)
    if match:
        return _fmt_cn_date(year, int(match[2]), int(match[3])) or text
    return _fmt_cn_date(year, 7, 1) or f"{year:04d}年07月01日"


def _canon_year_month(value: str) -> tuple[int, int] | None:
    match = _DATE_CANON.fullmatch(value)
    if not match:
        return None
    return int(match[1]), int(match[2])


def _has_explicit_day(value: str) -> bool:
    text = _prep_date(value)
    if "日" in text:
        return True
    return bool(_DATE_YMD_SEP.fullmatch(text) or _DATE_YMD8.fullmatch(text))


def split_study_range(enter: str, graduate: str) -> tuple[str, str]:
    """「自1997年9月至2001年7月」拆成入学、毕业。毕业已有日且年月相同则保留该日。"""
    raw = (enter or "").strip()
    if "至" not in raw:
        return enter, graduate
    body = raw[1:] if raw.startswith("自") else raw
    left, _, right = body.partition("至")
    left_n = _parse_cn_date(_prep_date(left))
    right_n = _parse_cn_date(_prep_date(right))
    if left_n is None or right_n is None:
        return enter, graduate
    graduate_raw = (graduate or "").strip()
    graduate_n = _parse_cn_date(_prep_date(graduate_raw)) if graduate_raw else None
    if (
        graduate_n
        and _has_explicit_day(graduate_raw)
        and _canon_year_month(graduate_n) == _canon_year_month(right_n)
    ):
        return left_n, graduate_n
    return left_n, right_n


def reconcile_dates(
    enter: str, graduate: str, xuezhi: str, cert_no: str
) -> tuple[str, str]:
    """入学+学制、证书编号里的年份，用来纠正把「二〇〇一」认成 2000 这类错误。"""
    enter_n = normalize_cn_date(enter)
    graduate_n = normalize_cn_date(graduate)
    enter_y = _date_year(enter_n)
    grad_y = _date_year(graduate_n)
    expected = None
    xz = _parse_xuezhi_years(xuezhi)
    if enter_y and xz:
        expected = enter_y + xz
    cert_years = _years_in_cert_no(cert_no)
    if expected is None and len(cert_years) == 1:
        expected = cert_years[0]
    if expected is None or not graduate_n or grad_y == expected:
        return enter_n, graduate_n
    cert_agrees = expected in cert_years
    off_by_one = grad_y is not None and abs(grad_y - expected) == 1
    if cert_agrees or off_by_one:
        graduate_n = _replace_date_year(graduate_n, expected)
    return enter_n, graduate_n


def classify_document(text: str, id_no: str) -> str:
    """同一条文本里出现「学位」就是学位，优先于「毕业证书」。"""
    if "学位" in text:
        return "degree"
    if "毕业证书" in text:
        return "diploma"
    if id_no:
        return "id_card"
    return "unknown"


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _level(row: dict[str, Any]) -> str:
    level = _first(row, "level", "层次", "cc")
    if level:
        return level
    raw = _first(row, "degree")
    if raw and raw.lower() not in {"graduation", "degree", "xl", "xw", "diploma"}:
        return raw
    return ""


def _row_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in row.values():
        if isinstance(value, str):
            parts.append(value)
    return "".join(parts)


def _id_no_from_row(row: dict[str, Any]) -> str:
    for key in ("id_no", "sfzh", "idNo"):
        got = normalize_id_no(_first(row, key))
        if got:
            return got
    return ""


def make_item(
    *,
    filename: str,
    page: int,
    hint: str,
    doc_type: str = "",
    error_code: str = "",
    **fields: str,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "doc_type": doc_type,
        "hint": hint,
        "filename": filename,
        "page": page,
        "name": "",
        "id_no": "",
        "cert_no": "",
        "cert_title": "",
        "university": "",
        "major": "",
        "level": "",
        "xuezhi": "",
        "enter_date": "",
        "graduate_date": "",
        "error": MESSAGES.get(error_code, ""),
        "error_code": error_code,
    }
    for key in BUSINESS_FIELDS:
        if key in fields:
            item[key] = fields[key]
    return item


def document_from_row(
    row: dict[str, Any], *, filename: str, page: int, hint: str
) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    name = _first(row, "name", "xm")
    cert_no = _first(row, "cert_no", "zsbh")
    id_no = _id_no_from_row(row)
    cert_title = _first(row, "cert_title", "title")
    university = _first(row, "university", "school", "xxmc")
    major = _first(row, "major", "zymc")
    level = _level(row)
    xuezhi = _first(row, "xuezhi", "duration")
    enter = _first(row, "enter_date", "enterDate", "rxsj")
    graduate = _first(row, "graduate_date", "graduateDate", "bysj")
    doc_type = classify_document(_row_text(row), id_no)
    if doc_type not in {"diploma", "degree"} or (
        id_no and normalize_id_no(cert_no) == id_no
    ):
        cert_no = ""
    enter, graduate = split_study_range(enter, graduate)
    enter, graduate = reconcile_dates(enter, graduate, xuezhi, cert_no)
    payload = {
        "name": name,
        "id_no": id_no,
        "cert_no": cert_no,
        "cert_title": cert_title,
        "university": university,
        "major": major,
        "level": level,
        "xuezhi": xuezhi,
        "enter_date": enter,
        "graduate_date": graduate,
    }
    if doc_type == "unknown" and not any(payload.values()):
        return None
    return make_item(
        filename=filename, page=page, hint=hint, doc_type=doc_type, **payload
    )


def parse_model_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def items_from_model(
    text: str, *, filename: str, page: int, hint: str
) -> list[dict[str, Any]] | None:
    """None 表示模型输出无法解析。空列表表示这一页没有证件。"""
    data = parse_model_object(text)
    if data is None:
        return None
    rows = data.get("documents")
    if rows is None:
        rows = data.get("people")
    if not isinstance(rows, list):
        return None
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = document_from_row(row, filename=filename, page=page, hint=hint)
        if item is not None:
            items.append(item)
    return collapse_same_cert_no(dedupe_same_documents(drop_phantom_ids(items)))


def _filled_count(item: dict[str, Any]) -> int:
    return sum(bool(item.get(key)) for key in BUSINESS_FIELDS)


def _phantom_id(item: dict[str, Any]) -> bool:
    title = str(item.get("cert_title") or "")
    return not item.get("id_no") and "身份证" in title


def drop_phantom_ids(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一页已有毕业证或学位证时，丢掉没有身份证号、标题却写着身份证的那条。"""
    has_edu = any(
        item.get("doc_type") in {"diploma", "degree"} and not _phantom_id(item)
        for item in items
    )
    if not has_edu:
        return items
    return [item for item in items if not _phantom_id(item)]


_TYPE_RANK = {"degree": 2, "diploma": 1}


def _cert_rank(item: dict[str, Any]) -> tuple[int, int]:
    return (_TYPE_RANK.get(str(item.get("doc_type") or ""), 0), _filled_count(item))


def _absorb_empty(winner: dict[str, Any], loser: dict[str, Any]) -> dict[str, Any]:
    merged = dict(winner)
    for key in BUSINESS_FIELDS:
        if not merged.get(key) and loser.get(key):
            merged[key] = loser[key]
    return merged


def collapse_same_cert_no(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一页上证书编号相同的是同一本证。学位优先于毕业证书，空字段从另一条补上。"""
    kept: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for item in items:
        cert_no = str(item.get("cert_no") or "")
        if not cert_no:
            kept.append(item)
            continue
        slot = index.get(cert_no)
        if slot is None:
            index[cert_no] = len(kept)
            kept.append(item)
            continue
        prev = kept[slot]
        if _cert_rank(item) > _cert_rank(prev):
            kept[slot] = _absorb_empty(item, prev)
        else:
            kept[slot] = _absorb_empty(prev, item)
    return kept


def dedupe_same_documents(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一页、同一类型，姓名学校专业和日期都相同则只留字段更多的一条。"""
    kept: list[dict[str, Any]] = []
    index: dict[tuple[str, ...], int] = {}
    for item in items:
        key = (
            str(item.get("doc_type") or ""),
            str(item.get("name") or ""),
            str(item.get("university") or ""),
            str(item.get("major") or ""),
            str(item.get("enter_date") or ""),
            str(item.get("graduate_date") or ""),
        )
        slot = index.get(key)
        if slot is None:
            index[key] = len(kept)
            kept.append(item)
            continue
        if _filled_count(item) > _filled_count(kept[slot]):
            kept[slot] = item
    return kept
