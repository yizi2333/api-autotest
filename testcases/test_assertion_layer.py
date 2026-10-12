"""断言层用法打样 —— 演示 `common/assertions.py` 怎么用。

★ 对比着看：同样是测「登录成功」，两种写法差在哪。

  ❌ 裸断言
      assert resp.status_code == 200
      assert "token" in resp.json()

  ✅ 用断言层
      assert_status(resp, 200)
      assert_schema(resp, LOGIN_OK_SCHEMA)

  后者挂了的时候，报错信息里自动带上「请求方法 + URL + 响应原文」，
  你不用重跑就能定位。而且判断标准统一，不会有人测状态码、有人测 body。
"""

import pytest

from common.assertions import (
    assert_json_field,
    assert_response_time,
    assert_schema,
    assert_status,
)

LOGIN_OK_SCHEMA = {
    "type": "object",
    "required": ["token", "username"],
    "properties": {
        "token": {"type": "string", "minLength": 1},
        "username": {"type": "string"},
    },
}


@pytest.mark.smoke
def test_login_uses_assertion_layer(account_api, test_user):
    """用断言层重写一遍「注册 → 登录」。"""
    account_api.register(test_user["username"], test_user["password"])
    resp = account_api.login(test_user["username"], test_user["password"])

    assert_status(resp, 200)
    assert_schema(resp, LOGIN_OK_SCHEMA)          # 结构断言：字段都在、类型对
    assert_json_field(resp, "username", test_user["username"])   # 值断言


@pytest.mark.smoke
def test_profile_response_time(account_api, logged_in_user):
    """响应时间断言。

    ★ 阈值定的是 2000ms —— 本地服务正常在 20ms 以内，留了 100 倍余量。
      为什么不卡到 100ms？因为 CI 机器负载不可控，卡太紧会变成
      「随机变红」的 flaky 用例，反而让人开始无视红色。
      阈值的作用是「抓到数量级异常」，不是「精确测量」。
    """
    resp = account_api.profile()

    assert_status(resp, 200)
    assert_response_time(resp, max_ms=2000)


# ── TODO(D6)：你来补 ────────────────────────────────────────────────
#
# 1. 用 assert_schema 给「注册成功」的响应也加一条结构断言。
#    先想清楚：注册成功该返回哪些字段？（去 sut/app.py 看 @app.post 那段）
#
# 2. 写一条「负面断言」用例：登录失败时，响应里**不应该**出现 token 字段。
#    ★ 这类断言叫「不应该发生什么」—— 它比正面断言更能发现安全缺陷。
#      提示：assert_schema 只能断言"有什么"，不能断言"没什么"，
#            所以这条你要自己写 assert "token" not in resp.json()，
#            并想清楚为什么这种断言值得单独写。
