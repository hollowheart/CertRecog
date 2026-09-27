# CertRecog

本机证件识别服务。只监听 `127.0.0.1`，识别身份证、学历证书和学位证书。

```powershell
cd D:\Work\CertRecog
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
# 在 .env 里填写 LLM_API_KEY
.\.venv\Scripts\python -m certrecog
```

缺 `LLM_API_KEY` 时进程拒绝启动。默认地址是 `http://127.0.0.1:8090`。没有鉴权，只接受本机调用。

设置 `CERTRECOG_DEBUG_DIR` 后，每一页的图片和 `result.json` 会写到该目录。日志不记录姓名、证号和图片。

## 其他服务如何调用

先确认服务活着：

```powershell
curl http://127.0.0.1:8090/health
```

正常返回 `{"ok": true}`。

识别用 `POST /recognize`，正文是 `multipart/form-data`。字段名是重复的 `file`。一次可以带多张 jpeg、png、webp、gif、bmp、tiff 或 pdf。可选字段 `hint` 不传就行；如果传，个数必须和文件一样，按顺序对齐，取值只能是 `id_card`、`diploma`、`degree` 或空字符串。`hint` 只是提示，最终类型以图上的字和硬规则为准。

```powershell
curl -X POST http://127.0.0.1:8090/recognize `
  -F "file=@C:\tmp\id.png" `
  -F "file=@C:\tmp\degree.pdf" `
  -F "hint=id_card" `
  -F "hint="
```

Python 调用：

```python
import httpx

with open(r"C:\tmp\id.png", "rb") as id_card, open(r"C:\tmp\degree.pdf", "rb") as degree:
    response = httpx.post(
        "http://127.0.0.1:8090/recognize",
        files=[
            ("file", ("id.png", id_card, "image/png")),
            ("file", ("degree.pdf", degree, "application/pdf")),
        ],
        data=[("hint", "id_card"), ("hint", "")],
        timeout=1200,
    )
response.raise_for_status()
items = response.json()["items"]
```

成功时 HTTP 状态是 200，正文是 `{"items":[...]}`。一页里有几本证就有几条。每条字段相同，没有的是空字符串：

- `doc_type`：`id_card`、`diploma`、`degree` 或 `unknown`。这一页识别失败时为空。
- `hint`、`filename`、`page`（从 1 开始）
- `name`、`id_no`、`cert_no`、`cert_title`
- `university`、`major`、`level`、`xuezhi`、`enter_date`、`graduate_date`
- `error`、`error_code`：成功时为空。某一页模型超时是 `vision_timeout`，调用失败是 `vision_failed`。其它页仍会返回。

一次最多 10 个文件、合计 10 页、单文件 8MB。不合法返回 400，正文是 `{"error_code":"...","error":"中文说明"}`。`error_code` 可能是 `empty_request`、`too_many_files`、`too_many_pages`、`file_too_large`、`unsupported_type`、`bad_hint`、`unreadable`。

同时只处理一个识别请求，后面最多再排 8 个。再多就返回 429，`error_code` 为 `busy`。一页最长约 120 秒，所以调用方的超时要留够，上面示例用的是 1200 秒。
