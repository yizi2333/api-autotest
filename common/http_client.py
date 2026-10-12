"""HTTP 客户端封装 —— 框架的底座。

★ 这一层要解决的三个问题：

  1. **复用连接、保持登录态**
     用 `requests.Session()` 而不是每次 `requests.get()`。
     Session 会复用 TCP 连接（省握手），也会自动携带上次拿到的 cookie。

  2. **让失败可复现**
     每次请求把「方法、URL、请求头、请求体、状态码、响应体、耗时」都记下来。
     用例红了的时候，你不需要重跑就能知道发生了什么。

  3. **不要把断言写在客户端里**
     这里**不**调 `raise_for_status()` —— 因为「返回 401」对某些用例恰恰是**期望结果**。
     判断对错是断言层的事，客户端只负责如实转述。
"""

import json
import time
from pathlib import Path

import requests

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "report" / "artifacts"

# ★ 留存时要脱敏的请求/响应头。
#   为什么必须做：CI 里 `upload-artifact` 上传的正是 `report/` ——
#   如果不脱敏，token / cookie 会跟着 artifact 一起被上传并在网页上可下载。
#   本项目里那只是个一次性测试 token，但**"把凭证写进可下载产物"这个模式本身是错的**。
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"}


def _mask(value: str) -> str:
    """保留一小段前缀便于比对，其余打码。

    留前缀是有意的：排错时你往往需要确认"是不是同一个 token"，
    而不是需要 token 的完整值。
    """
    if len(value) <= 16:
        return "***已脱敏***"
    return f"{value[:8]}…***已脱敏***"


def _mask_header(name: str, value: str) -> str:
    """按头名决定要不要脱敏。非敏感头原样返回。"""
    if name.lower() not in SENSITIVE_HEADERS:
        return value
    # `Authorization: Bearer xxx` —— 保留方案名，只打码凭证部分，
    # 这样读留存时还能一眼看出用的是什么认证方式。
    if name.lower() == "authorization" and " " in value:
        scheme, _, credential = value.partition(" ")
        return f"{scheme} {_mask(credential)}"
    return _mask(value)


# ★★ 体内容里的敏感字段名。
#
#   教训：脱敏必须覆盖「值可能出现的**所有位置**」——
#   我第一版只脱敏了【请求头】，看到输出里写着「✅ 已脱敏」就以为安全了。
#   结果：密码明文躺在**请求体**里，token 明文躺在**响应体**里，两个都没管。
#
#   **修了一半比没修更危险 —— 因为它给你一种"已经安全了"的错觉。**
SENSITIVE_BODY_KEYS = {
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "id_token",
    "secret", "apikey", "api_key",
    "session", "sessionid", "session_id",
}


def _redact_node(node):
    """递归把字典/列表里敏感字段的值打码（原地修改）。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and key.lower() in SENSITIVE_BODY_KEYS:
                node[key] = _mask(value)
            else:
                _redact_node(value)
    elif isinstance(node, list):
        for item in node:
            _redact_node(item)


def _redact_body(text: str) -> str:
    """把 JSON 体里的敏感字段打码；不是 JSON 就原样返回。

    ★ 为什么只处理 JSON：JSON 有字段名，能可靠识别哪些是敏感值。
      表单编码 / 二进制体没有统一结构，硬做容易既漏又误伤 ——
      那种情况下的正确做法是**干脆不留存体内容**，而不是猜。
    """
    if not text:
        return text
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return text
    try:
        data = json.loads(stripped)
    except ValueError:
        return text          # 不是合法 JSON，原样返回（不做猜测式替换）
    _redact_node(data)
    return json.dumps(data, ensure_ascii=False)


class ApiResponse:
    """对 `requests.Response` 的轻量包装，额外带上耗时和请求快照。"""

    def __init__(self, raw: requests.Response, elapsed_ms: float, request_dump: dict):
        self.raw = raw
        self.status_code = raw.status_code
        self.headers = raw.headers
        self.elapsed_ms = elapsed_ms
        self.request_dump = request_dump      # 本次请求的快照，失败时写盘用

    @property
    def text(self) -> str:
        return self.raw.text

    @property
    def body_bytes(self) -> int:
        """响应体字节数。

        ★ 注意：不要用响应头的 Content-Length 代替它 ——
          开了 gzip 之后 Content-Length 是压缩后的长度，
          拿它和另一个「没开 gzip」的响应比大小是无效比较。
        """
        return len(self.raw.content)

    def json(self):
        """解析 JSON；解析失败时把原文一起抛出来，方便定位。"""
        try:
            return self.raw.json()
        except ValueError as exc:
            raise AssertionError(
                f"响应不是合法 JSON。状态码={self.status_code} 原文前 200 字：{self.text[:200]!r}"
            ) from exc

    def save(self, tag: str) -> Path:
        """把请求和响应原文落盘到 report/artifacts/<tag>.txt。失败留存用。

        ★ 这个方法在写完之后【一次都没被调用过】，直到我把它接进
          失败自动留存才第一次真正跑起来 —— 然后立刻崩了：
              TypeError: sequence item 9: expected str instance, bytes found

          原因：`requests` 在用 `json=` 发请求时，把请求体存成 **bytes**，
          而 `"\\n".join(...)` 要求全是 str。
          ★ 教训：**没被触发过的代码 = 没写过的代码。**
            它看着对、语法也对、`py_compile` 也过 —— 但一跑就崩。
        """
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACT_DIR / f"{tag}.txt"

        # 请求体可能是 bytes / str / None，统一转成可读文本
        body = self.request_dump.get("body")
        if isinstance(body, (bytes, bytearray)):
            try:
                body = body.decode("utf-8")
            except UnicodeDecodeError:
                body = repr(body)          # 二进制体就存 repr，别让它把整个留存搞崩
        elif body is None:
            body = ""
        # ★ 请求体里也会有敏感值（登录请求的 password 就在这）
        body = _redact_body(body)

        lines = [
            "=========== REQUEST ===========",
            f"{self.request_dump['method']} {self.request_dump['url']}",
            *[f"{k}: {_mask_header(k, str(v))}" for k, v in self.request_dump["headers"].items()],
            "",
            body,
            "=========== RESPONSE ==========",
            f"HTTP {self.status_code}  ({self.elapsed_ms:.1f} ms, {self.body_bytes} bytes)",
            *[f"{k}: {_mask_header(k, str(v))}" for k, v in self.headers.items()],
            "",
            # ★ 响应体里也会有敏感值（登录响应里的 token 就在这）
            _redact_body(self.text),
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def __repr__(self) -> str:
        return f"<ApiResponse {self.status_code} {self.elapsed_ms:.1f}ms {self.body_bytes}B>"


class HttpClient:
    """所有接口调用的唯一出口。"""

    def __init__(self, base_url: str, timeout: float = 5, logger=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.log = logger
        self.session = requests.Session()
        # ★ 最近一次响应。用例失败时，conftest 里的 hook 会把它的原文落盘 ——
        #   这就是「失败自动留存」的落点。没有这个引用，save() 永远没机会被调用。
        self.last_response: "ApiResponse | None" = None

    # ── 认证 ────────────────────────────────────────────────────────
    def set_token(self, token: str) -> None:
        """把 token 挂到 Session 上，之后所有请求自动带 Authorization 头。

        ★ 这就是「参数关联」：登录接口拿到的 token，自动传给后续所有接口。
          不要在每个用例里手动传 token —— 那是重复劳动，也容易漏。
        """
        self.session.headers["Authorization"] = f"Bearer {token}"

    def clear_token(self) -> None:
        """清掉认证信息，用于「未登录访问」这类异常用例。"""
        self.session.headers.pop("Authorization", None)

    # ── 核心请求 ────────────────────────────────────────────────────
    def request(self, method: str, path: str, *, headers=None, **kwargs) -> ApiResponse:
        url = self.base_url + path
        started = time.perf_counter()
        raw = self.session.request(
            method.upper(), url, headers=headers, timeout=self.timeout, **kwargs
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        request_dump = {
            "method": method.upper(),
            "url": url,
            "headers": dict(raw.request.headers),
            "body": raw.request.body,
        }
        resp = ApiResponse(raw, elapsed_ms, request_dump)
        self.last_response = resp          # ★ 供失败留存使用（见 conftest.py 的 hook）

        if self.log:
            self.log.info(
                "%s %s -> %s (%.1f ms, %s B)",
                method.upper(), path, resp.status_code, elapsed_ms, resp.body_bytes,
            )
        return resp

    def get(self, path: str, **kwargs) -> ApiResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> ApiResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> ApiResponse:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> ApiResponse:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        self.session.close()
