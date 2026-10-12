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
        """把请求和响应原文落盘到 report/artifacts/<tag>.txt。失败留存用。"""
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACT_DIR / f"{tag}.txt"
        lines = [
            "=========== REQUEST ===========",
            f"{self.request_dump['method']} {self.request_dump['url']}",
            *[f"{k}: {v}" for k, v in self.request_dump["headers"].items()],
            "",
            self.request_dump["body"] or "",
            "=========== RESPONSE ==========",
            f"HTTP {self.status_code}  ({self.elapsed_ms:.1f} ms, {self.body_bytes} bytes)",
            *[f"{k}: {v}" for k, v in self.headers.items()],
            "",
            self.text,
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
