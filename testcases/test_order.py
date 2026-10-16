"""订单接口用例。

★ 这一篇和 test_account.py 有个重要区别，先看明白再抄：

    test_account.py  —— 【全部】数据驱动（形状相同，只有数据不同）
    test_order.py    —— 【前三条】数据驱动，第四条单独写（形状不同）

  为什么？因为数据驱动的前提是「同一段代码，换一组数据」。
  ORDER-004 需要两个账号交叉验证，换数据换不出来 —— 硬套会写出一堆 if。

  ★ 判断规则：
      「形状相同、数据不同」→ 数据驱动
      「形状不同」          → 各写各的
"""

import uuid

import pytest

from common.dataprovider import load_cases
from common.http_client import HttpClient


@pytest.mark.negative
@pytest.mark.parametrize(
    "case",
    load_cases("order_negative"),
    ids=lambda c: c["case_id"],          # 报告里显示 ORDER-001 而不是 case0
)
def test_order_create_negative(account_api, client, anonymous_client, logged_in_user, case):
    """创建订单的异常场景（数据驱动，覆盖 ORDER-001 ~ 003）。

    ★ 为什么参数里同时要 client 和 anonymous_client：

        client            —— logged_in_user 已经登录，它的 Session 上挂着 token
        anonymous_client  —— 干净的客户端，**不带任何认证信息**

      数据里的 `auth` 字段决定用哪个：
        auth: none      → 用 anonymous_client（也就是"没登录"）
        auth: required  → 用 client（已登录）

      ★ 这个设计的意义：**"要不要带 token"这件事本身也是测试数据的一部分。**
        如果写死用 client，就永远测不出"未登录"这一条。
    """
    http = anonymous_client if case["auth"] == "none" else client

    resp = http.post(
        "/api/order/create",
        json={"item": case["item"], "amount": case["amount"]},
    )

    assert resp.status_code == case["expect_status"], (
        f"[{case['case_id']}] {case['title']}\n"
        f"  期望 {case['expect_status']}，实际 {resp.status_code}\n"
        f"  响应：{resp.text[:200]}"
    )


# ═══════════════════════════════════════════════════════════════════
# ORDER-004：水平越权  ★ 这一段你来写
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.negative
def test_order_idor_cross_user(account_api, client, cfg, logged_in_user):
    """A 下单后，B 拿着自己的 token 去查 A 的订单，期望 403。

    ★ 这个测试的重点是【归属判断】：
      订单属于谁，只有谁能查。即使知道 order_id，也不能越权。
    """
    # 第一步：A（logged_in_user）下一单，拿到 order_id
    resp = client.post("/api/order/create", json={"item": "A的订单", "amount": 1})
    order_id = resp.json()["order_id"]

    # 第二步：造一个 B 并登录
    b_name = "idor_b_" + uuid.uuid4().hex[:8]
    account_api.register(b_name, "Pw_123456")
    b_token = account_api.login(b_name, "Pw_123456").json()["token"]

    # 第三步：造一个【B 自己的客户端】，把 B 的 token 挂上去
    b_client = HttpClient(cfg["base_url"], cfg["timeout"])
    b_client.set_token(b_token)

    try:
        # 第四步：B 去查 A 的订单
        resp = b_client.get(f"/api/order/{order_id}")

        # 第五步：断言
        assert resp.status_code == 403, (
            f"[ORDER-004] B 越权访问 A 的订单，期望 403，实际 {resp.status_code}\n"
            f"响应：{resp.text[:200]}"
        )
        # 再加一条断言：响应体里【不能】出现 A 的订单内容
        assert "A的订单" not in resp.text, (
            "[ORDER-004] 响应体中不应包含 A 的订单内容"
        )
    finally:
        b_client.close()
#
# 为什么它不能数据驱动：需要【两个账号】——
#
#   A：注册 → 登录 → 下一单            → 拿到 order_id
#   B：注册 → 登录
#   B 拿着自己的 token 去查 A 的那个 order_id
#   期望：403（而不是 200）
#
# ── 你现在手上的材料 ────────────────────────────────────────────
#
#   logged_in_user   就是"A"。它已经注册+登录，token 挂在 client 上
#   account_api      .register(username, password) / .login(username, password)
#   cfg              配置字典，cfg["base_url"] 是服务地址
#   HttpClient       见 conftest.py 顶部 import —— 造一个"B 的客户端"要用它
#
# ── 骨架（照这个填）──────────────────────────────────────────────
#
# @pytest.mark.negative
# def test_order_idor_cross_user(account_api, client, cfg, logged_in_user):
#     # 第一步：A（logged_in_user）下一单，拿到 order_id
#     #   resp = client.post("/api/order/create", json={"item": "A的订单", "amount": 1})
#     #   order_id = resp.json()["order_id"]
#     #
#     # 第二步：造一个 B 并登录
#     #   b_name = "idor_b_" + uuid.uuid4().hex[:8]
#     #   account_api.register(b_name, "Pw_123456")
#     #   b_token = account_api.login(b_name, "Pw_123456").json()["token"]
#     #
#     # 第三步：造一个【B 自己的客户端】，把 B 的 token 挂上去
#     #   b_client = HttpClient(cfg["base_url"], cfg["timeout"])
#     #   b_client.set_token(b_token)
#     #
#     # 第四步：B 去查 A 的订单
#     #   resp = b_client.get(f"/api/order/{order_id}")
#     #
#     # 第五步：断言
#     #   assert resp.status_code == 403, ...
#     #   ★ 再加一条断言：响应体里【不能】出现 A 的订单内容
#     #     （状态码对了不代表没泄漏数据）
#     #
#     # 别忘了 b_client.close()
#
# ── ★ 写完后回答自己一个问题 ───────────────────────────────────
#
#   如果服务端【没做】归属判断，这个测试会拿到什么？
#   （去 sut/app.py 把 if row["username"] != user 那两行注释掉试一次，
#     看看测试是不是真的会红 —— 这叫"验证你的测试确实能抓到问题"）
