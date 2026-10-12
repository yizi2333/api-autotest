"""账号接口用例 —— 数据驱动版。

★ 打样说明：
  下面两组用例已经写好骨架，`cases.yaml` 里各有 4 条**已完成**的数据。
  你要做的是：把 YAML 里标了 `TODO(D5)` 的场景补进去，
  然后在下面把 assert 补完整（现在只断言了状态码，没断言响应体）。

跑法：
    pytest testcases/test_account.py -v
    pytest -m negative
"""

import pytest

from common.dataprovider import load_cases

# ★ 断言用的 JSON Schema：比逐字段断言更全面，接口加字段不会误报
LOGIN_OK_SCHEMA = {
    "type": "object",
    "required": ["token", "username"],
    "properties": {
        "token": {"type": "string", "minLength": 1},
        "username": {"type": "string"},
    },
}


@pytest.mark.negative
@pytest.mark.parametrize(
    "case",
    load_cases("register_validation"),
    ids=lambda c: c["case_id"],       # ← 报告里显示 REG-001 而不是 case0
)
def test_register_validation(account_api, case):
    """注册接口的参数校验（边界值法）。

    parametrize 会把这一条函数展开成 N 条独立用例 ——
    一条挂了不影响其他条，报告里也能一眼看出是哪个边界挂了。
    """
    resp = account_api.register(case["username"], case["password"])

    assert resp.status_code == case["expect_status"], (
        f"[{case['case_id']}] {case['title']}\n"
        f"  期望 {case['expect_status']}，实际 {resp.status_code}\n"
        f"  响应：{resp.text[:200]}"
    )


@pytest.mark.negative
@pytest.mark.parametrize(
    "case",
    load_cases("login_negative"),
    ids=lambda c: c["case_id"],
)
def test_login_negative(client, account_api, logged_in_user, case):
    """登录接口的认证异常场景。

    ★ 为什么这个用例依赖 logged_in_user：
      因为 LOGIN-002「密码错误」需要先有一个**真实存在**的用户，
      否则「密码错误」和「用户不存在」测出来都是 401，区分不开。
      这就是「测试数据前置条件」—— 想清楚它，用例才有意义。
    """
    username = case["username"].format(
        suffix=logged_in_user["username"].removeprefix("qa_"),
        valid_user=logged_in_user["username"],
    )
    resp = account_api.login(username, case["password"])

    assert resp.status_code == case["expect_status"], (
        f"[{case['case_id']}] {case['title']}\n"
        f"  期望 {case['expect_status']}，实际 {resp.status_code}\n"
        f"  响应：{resp.text[:200]}"
    )

    # ── TODO(D5)：你来补 ──────────────────────────────────────────
    # 1. 现在只断言了状态码。**状态码对了不代表结果对了** ——
    #    补一条断言：失败响应里不应该泄漏「是用户名错还是密码错」这类信息。
    #    ★ 提示：看 resp.json() 里有没有 detail 字段，它的措辞是否一致。
    # 2. 加一条用例：用 A 的 token 去访问 B 的资源（水平越权）。
    #    这需要你先在 sut/app.py 里把订单接口写完。


# ── TODO(D5)：你来写 ────────────────────────────────────────────────
# 下面这个函数是给你起的头，把 JSON Schema 断言补上并让它通过：
#
# @pytest.mark.smoke
# def test_login_response_schema(account_api, test_user):
#     """登录响应必须符合约定的结构。"""
#     account_api.register(test_user["username"], test_user["password"])
#     resp = account_api.login(test_user["username"], test_user["password"])
#
#     assert resp.status_code == 200
#     # ★ 在这里用 jsonschema.validate(instance=..., schema=LOGIN_OK_SCHEMA)
#     #   想一想：为什么用 Schema 断言，比写 5 个 assert 更好？
