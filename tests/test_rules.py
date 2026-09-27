from __future__ import annotations

from certrecog.rules import (
    classify_document,
    document_from_row,
    items_from_model,
    normalize_cn_date,
    normalize_id_no,
)

ID18 = "110101199001011234"


def test_normalize_id_no_accepts_18_and_15() -> None:
    assert normalize_id_no(ID18) == ID18
    assert normalize_id_no("110101-19900101-1234") == ID18
    assert normalize_id_no("110101900101123") == "110101900101123"


def test_normalize_id_no_rejects_dates_and_short_numbers() -> None:
    assert normalize_id_no("1980年9月15日") == ""
    assert normalize_id_no("19800915") == ""
    assert normalize_id_no("12345") == ""


def test_degree_wins_over_diploma() -> None:
    assert classify_document("学士学位证书普通高等学校毕业证书", "") == "degree"
    assert classify_document("普通高等学校毕业证书", "") == "diploma"
    assert classify_document("毕业日期", ID18) == "id_card"
    assert classify_document("毕业", "") == "unknown"


def test_same_number_is_not_both_id_and_cert() -> None:
    item = document_from_row(
        {
            "name": "张三",
            "cert_title": "普通高等学校毕业证书",
            "cert_no": ID18,
            "id_no": ID18,
        },
        filename="a.png",
        page=1,
        hint="",
    )
    assert item is not None
    assert item["doc_type"] == "diploma"
    assert item["cert_no"] == ""
    assert item["id_no"] == ID18


def test_id_card_drops_cert_no() -> None:
    item = document_from_row(
        {"name": "张三", "id_no": ID18, "cert_no": "ABC123"},
        filename="id.png",
        page=1,
        hint="diploma",
    )
    assert item is not None
    assert item["doc_type"] == "id_card"
    assert item["cert_no"] == ""
    assert item["hint"] == "diploma"


def test_chinese_date_and_off_by_one_year() -> None:
    assert normalize_cn_date("二〇〇一年七月") == "2001年07月01日"
    item = document_from_row(
        {
            "name": "王建坤",
            "cert_title": "学士学位证书",
            "cert_no": "10006120010501471",
            "enter_date": "一九九七年九月",
            "graduate_date": "二〇〇〇年七月",
            "xuezhi": "四年制",
        },
        filename="xw.png",
        page=2,
        hint="",
    )
    assert item is not None
    assert item["doc_type"] == "degree"
    assert item["page"] == 2
    assert item["enter_date"] == "1997年09月01日"
    assert item["graduate_date"] == "2001年07月01日"
    assert item["cert_no"] == "10006120010501471"


def test_empty_model_page_is_empty_list_and_garbage_is_none() -> None:
    assert items_from_model('{"documents":[]}', filename="a.png", page=1, hint="") == []
    assert items_from_model('{"documents":[{}]}', filename="a.png", page=1, hint="") == []
    assert items_from_model("不是 json", filename="a.png", page=1, hint="") is None
    assert items_from_model('{"ok": true}', filename="a.png", page=1, hint="") is None


def test_study_range_keeps_graduate_day() -> None:
    item = document_from_row(
        {
            "name": "王建坤",
            "cert_title": "学士学位证书",
            "enter_date": "1997年9月至2001年7月",
            "graduate_date": "2001年07月01日",
        },
        filename="xw.png",
        page=1,
        hint="",
    )
    assert item is not None
    assert item["enter_date"] == "1997年09月01日"
    assert item["graduate_date"] == "2001年07月01日"

    replaced = document_from_row(
        {
            "cert_title": "学士学位证书",
            "enter_date": "自1997年9月至2001年7月",
            "graduate_date": "2000年07月01日",
        },
        filename="xw.png",
        page=1,
        hint="",
    )
    assert replaced is not None
    assert replaced["enter_date"] == "1997年09月01日"
    assert replaced["graduate_date"] == "2001年07月01日"


def test_phantom_id_card_dropped_when_degree_present() -> None:
    raw = """
    {"documents":[
      {"name":"王建坤","cert_title":"居民身份证","university":"北京航空航天大学","major":"外语系","level":"本科","xuezhi":"四年制","enter_date":"1997年9月至2001年7月","graduate_date":"2001年07月01日"},
      {"name":"王建坤","cert_title":"学士学位证书","university":"北京航空航天大学","major":"外语系","level":"本科","xuezhi":"四年制","enter_date":"1997年9月至2001年7月","graduate_date":"2001年07月01日"}
    ]}
    """
    items = items_from_model(raw, filename="xw.png", page=1, hint="")
    assert items is not None
    assert len(items) == 1
    assert items[0]["doc_type"] == "degree"
    assert items[0]["cert_title"] == "学士学位证书"
    assert items[0]["enter_date"] == "1997年09月01日"
    assert items[0]["graduate_date"] == "2001年07月01日"


def test_real_id_card_stays_beside_degree() -> None:
    raw = """
    {"documents":[
      {"name":"张三","id_no":"110101199001011234","cert_title":"居民身份证"},
      {"name":"张三","cert_title":"学士学位证书"}
    ]}
    """
    items = items_from_model(raw, filename="both.png", page=1, hint="")
    assert items is not None
    assert [item["doc_type"] for item in items] == ["id_card", "degree"]


def test_lone_phantom_id_card_is_kept() -> None:
    raw = '{"documents":[{"name":"王建坤","cert_title":"居民身份证"}]}'
    items = items_from_model(raw, filename="xw.png", page=1, hint="")
    assert items is not None
    assert len(items) == 1
    assert items[0]["doc_type"] == "unknown"
    assert items[0]["cert_title"] == "居民身份证"


def test_duplicate_degrees_collapse_different_names_stay() -> None:
    raw = """
    {"documents":[
      {"name":"王建坤","cert_title":"学士学位证书","university":"北京航空航天大学","major":"英语","enter_date":"1997年9月","graduate_date":"2001年7月1日"},
      {"name":"王建坤","cert_title":"学士学位证书","cert_no":"100064011297","university":"北京航空航天大学","major":"英语","enter_date":"1997年9月","graduate_date":"2001年7月1日"},
      {"name":"李四","cert_title":"学士学位证书","university":"北京航空航天大学","major":"英语","enter_date":"1997年9月","graduate_date":"2001年7月1日"}
    ]}
    """
    items = items_from_model(raw, filename="xw.png", page=1, hint="")
    assert items is not None
    assert [item["name"] for item in items] == ["王建坤", "李四"]
    assert items[0]["cert_no"] == "100064011297"
    assert items[0]["doc_type"] == "degree"


def test_same_cert_no_keeps_degree_different_numbers_stay() -> None:
    same = """
    {"documents":[
      {"name":"王建坤","cert_title":"毕业证书","cert_no":"100064011297","university":"北京航空航天大学","major":"外语系","enter_date":"1997年9月","graduate_date":"2001年7月1日"},
      {"name":"王建坤","cert_title":"学位证书","cert_no":"100064011297","university":"北京航空航天大学","major":"外语系","level":"本科","xuezhi":"四年制","enter_date":"1997年9月","graduate_date":"2001年7月1日"}
    ]}
    """
    items = items_from_model(same, filename="xw.png", page=1, hint="")
    assert items is not None
    assert len(items) == 1
    assert items[0]["doc_type"] == "degree"
    assert items[0]["cert_title"] == "学位证书"
    assert items[0]["cert_no"] == "100064011297"
    assert items[0]["xuezhi"] == "四年制"

    separate = """
    {"documents":[
      {"name":"王建坤","cert_title":"普通高等学校毕业证书","cert_no":"10001","university":"北京航空航天大学"},
      {"name":"王建坤","cert_title":"学士学位证书","cert_no":"10002","university":"北京航空航天大学"}
    ]}
    """
    both = items_from_model(separate, filename="both.png", page=1, hint="")
    assert both is not None
    assert [item["doc_type"] for item in both] == ["diploma", "degree"]


def test_one_page_can_hold_two_documents() -> None:
    raw = """
    {"documents":[
      {"name":"张三","id_no":"110101199001011234","cert_type":"id_card"},
      {"name":"张三","cert_title":"学士学位证书","cert_no":"10006120010501471","cert_type":"degree"}
    ]}
    """
    items = items_from_model(raw, filename="both.png", page=1, hint="")
    assert items is not None
    assert [item["doc_type"] for item in items] == ["id_card", "degree"]
    assert items[0]["page"] == items[1]["page"] == 1
