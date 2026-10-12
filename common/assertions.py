"""断言层 —— 把「怎么判断对错」集中到一处。

★ 为什么值得单独一层：

  如果每个用例都手写 `assert resp.status_code == 200`，会有三个后果：
    ① 错误信息全靠猜 —— 挂了只看到 `assert 500 == 200`，看不到响应体
    ② 判断标准不统一 —— 有人断言状态码，有人断言 body，同一个接口两套标准
    ③ 改判断标准要改 N 处

  集中到这里之后：用例只写「期望什么」，不写「怎么比」。
  挂了的时候，报错信息里自动带上响应原文。

★ 这一层的设计原则（来自我记录的 12 个「静默失效」）：
  **断言不能只校验「请求是否成功」，必须同时校验「数据是否符合预期」。**
  返回 200 但数据是空的、错的、别人的 —— 这种缺陷正常流用例永远测不出来。
"""

import json

from jsonschema import ValidationError, validate


def assert_status(resp, expected: int):
    """断言状态码，失败时把响应体一起打出来。

    ★ 打样：注意失败信息里带了什么 —— 状态码、期望值、响应体。
      一个不会调试的断言，等于没有断言。
    """
    assert resp.status_code == expected, (
        f"状态码不符：期望 {expected}，实际 {resp.status_code}\n"
        f"  请求：{resp.request_dump['method']} {resp.request_dump['url']}\n"
        f"  响应：{resp.text[:300]}"
    )


def assert_json_field(resp, field: str, expected):
    """断言 JSON 响应里某个字段的值。"""
    body = resp.json()
    assert field in body, f"响应里没有字段 {field!r}，实际字段：{list(body)}"
    assert body[field] == expected, (
        f"字段 {field!r} 不符：期望 {expected!r}，实际 {body[field]!r}"
    )


def assert_schema(resp, schema: dict):
    """用 JSON Schema 校验响应结构。

    ★ 比逐字段断言好在哪：
      接口新增字段时不会误报（Schema 允许额外字段），
      但字段类型变了、必填字段没了 —— 立刻抓到。
      这是「结构契约」级别的断言，不是「值」级别的。
    """
    try:
        validate(instance=resp.json(), schema=schema)
    except ValidationError as exc:
        raise AssertionError(
            f"响应结构不符合约定：{exc.message}\n"
            f"  出错位置：{list(exc.absolute_path)}\n"
            f"  实际响应：{json.dumps(resp.json(), ensure_ascii=False)[:300]}"
        ) from exc


def assert_response_time(resp, max_ms: float):
    """断言响应时间。

    ★ 判断格：这个断言的阈值该定多少？定太紧会变成 flaky 用例
      （CI 机器慢的时候随机红），定太松又没有意义。
      想一想：为什么性能断言一般用 P95/P99，而不是单次响应时间？
    """
    assert resp.elapsed_ms <= max_ms, (
        f"响应超时：{resp.elapsed_ms:.1f} ms > {max_ms} ms"
    )


# ── TODO(D6)：你来补 ────────────────────────────────────────────────
#
# 1. assert_db(sql, expected)
#    查数据库，断言落库结果符合预期。
#    ★ 为什么接口测试还要查库：接口返回 200 只说明「服务说它成功了」，
#      数据到底写没写进去、写对没有，只有查库才知道。
#      提示：用 sqlite3 连 sut/sut.db，注意 row_factory。
#
# 2. assert_no_sensitive_leak(resp, words)
#    断言响应里不包含敏感信息（密码、token 明文、内部路径、堆栈）。
#    ★ 这是安全视角的断言 —— 一般测开不会写，你有安全背景，这是你的差异化。
#      JD 职责 2 写的是「从可测性、稳定性、容灾性视角前置识别风险」，
#      这类断言就是「前置识别」的落地。
#
# 3. 想一想：上面这些断言里，哪几个属于「值断言」，哪几个属于「结构断言」？
#    什么场景该用哪种？
