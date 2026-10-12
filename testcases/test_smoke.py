"""冒烟用例 —— 核心链路能不能跑通。

★ 冒烟测试是什么：版本准入前对主流程的最小验证。
  它只回答一个问题：「这个版本能不能测？」—— 挂了就不用往下测了。
  所以它必须快、必须稳、必须只覆盖主干。

跑法：
    pytest -m smoke
"""

import uuid

import pytest


@pytest.mark.smoke
def test_health(client):
    """服务活着。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.smoke
def test_register_then_login(account_api):
    """注册 → 登录 是账号体系的主干链路。

    ★ 这条用例**自己造一个唯一用户**，而不是复用 test_user fixture ——
      因为 test_user 已经被 logged_in_user 拿去注册过了，再注册一次必然 409。
      「两条用例抢同一个账号」是新手最常踩的坑，而且症状很迷惑（单独跑是绿的）。
    """
    user = {"username": f"smoke_{uuid.uuid4().hex[:8]}", "password": "Pw_123456"}

    reg = account_api.register(user["username"], user["password"])
    assert reg.status_code == 201, f"注册失败：{reg.status_code} {reg.text[:200]}"
    assert reg.json()["username"] == user["username"]

    login = account_api.login(user["username"], user["password"])
    assert login.status_code == 200, f"登录失败：{login.status_code} {login.text[:200]}"

    body = login.json()
    assert "token" in body and body["token"], "登录成功但没返回 token"
    assert body["username"] == user["username"]


@pytest.mark.smoke
def test_profile_with_token(logged_in_user, account_api):
    """带上 token 能拿到自己的资料。

    ★ 注意这里用了 logged_in_user 这个 fixture：
      它内部已经完成了「注册 + 登录 + 挂 token」三步。
      用例本身只关心「拿资料」这一件事 —— 前置条件被 fixture 收走了。
    """
    resp = account_api.profile()

    assert resp.status_code == 200, f"查资料失败：{resp.status_code} {resp.text[:200]}"
    body = resp.json()
    assert body["username"] == logged_in_user["username"]
    assert "balance" in body


@pytest.mark.smoke
@pytest.mark.negative
def test_profile_without_token(anonymous_client):
    """★ 异常场景：不带 token 访问受保护接口，必须被拒绝。

    这条用例的价值在于 —— 如果服务端「忘记加认证」，
    它会返回 200 和别人的数据。这种缺陷用「正常流用例」永远测不出来。
    """
    resp = anonymous_client.get("/api/account/profile")

    assert resp.status_code == 401, (
        f"未认证却拿到了 {resp.status_code} —— 认证可能失效了。"
        f"响应：{resp.text[:200]}"
    )
