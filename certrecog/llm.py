from __future__ import annotations

import base64

from openai import OpenAI

from certrecog.config import Settings

SYSTEM = """你从证件图片中识别证件。只输出 JSON，不要其它文字：
{"documents":[{"name":"","cert_no":"","id_no":"","cert_type":"","cert_title":"","university":"","major":"","level":"","xuezhi":"","enter_date":"","graduate_date":""}]}
每次只给你一张图（一页）。这一页上有几本不同的证就返回几条，不要把不同的证合并。
毕业证、学位证上印的照片、姓名、出生年月属于这本证，不要另起一条居民身份证。只有图上真有居民身份证（标题和身份证号都在）才单独一条。
学位证书正文里的「毕业」「业已毕业」仍属于这一本学位证，不要再另起一条毕业证书。只有图上另外有一本标题为「毕业证书」的证件时才返回 diploma。
没有证件则 documents 为空数组。
cert_no 为证书编号，必须抄图上的「证书编号」，没有则留空。id_no 仅为图上印出的 18 位（或旧版 15 位）身份证号码。
毕业证书、学位证书通常没有身份证号：此时 id_no 必须留空，不要把出生日期、证书编号、学号填进去。
cert_title：图上证件标题原文。
cert_type：
- diploma：仅当图上出现相连的四个字「毕业证书」。
- degree：图上出现「学位」。同时有「学位」和「毕业证书」时填 degree。
- id_card：居民身份证。
- 无法判断则 cert_type 和 cert_title 留空。
university/major/level/xuezhi/enter_date/graduate_date 为学校、专业、层次、学制、入学、毕业日期。
major 只写专业名，不写院系。例如「外语系英语专业」的 major 是「英语」。
「自A至B」要拆开：enter_date 写 A，graduate_date 写 B，不要把整段写进入学日期。
日期尽量按证书原文抄写，可保留汉字数字（如一九九七年九月、二〇〇一年七月），不要自行改成阿拉伯数字。
尤其注意「一」和「〇」：二〇〇一年不是二〇〇〇年。1997年入学、四年制则毕业是 2001 年，不要写成 2000 年。
无法识别的字段留空。"""


def user_text(hint: str) -> str:
    text = (
        "请识别这一页上的全部证件。一页有几本不同的证就返回几条。"
        "毕业证、学位证上的照片、姓名、出生年月属于这本证，不要另起一条居民身份证。"
        "学位证正文里的「毕业」不要再拆成另一本毕业证书。"
        "没有证件则 documents 为空数组。出生日期不是身份证号。"
        "证书编号写入 cert_no。专业只写专业名，不写院系。"
        "「自A至B」拆成入学和毕业两个日期。"
    )
    if hint:
        return (
            text
            + f"\n调用方提示类型可能是 {hint}，仅供参考，以图上的字为准。"
        )
    return text


class LlmVision:
    def __init__(self, settings: Settings) -> None:
        self._model = settings.llm_vision_model
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_api_host,
            timeout=120.0,
        )

    def complete(self, system: str, user: str, png: bytes) -> str:
        b64 = base64.b64encode(png).decode("ascii")
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                },
            ],
        )
        return (resp.choices[0].message.content or "").strip()
