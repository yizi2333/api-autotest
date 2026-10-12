"""pytest 全局 fixture —— 把各层「接起来」的地方。

★ fixture 是什么：
   一个函数，pytest 会在用例需要它时自动调用，把返回值注入进来。
   用例只要在参数里写上名字，就能拿到它 —— 不需要自己 import 和构造。
   好处：前置条件（起会话、登录、造数据）只写一次，所有用例共享。

★ scope 是什么：
   `scope="session"` = 整个测试会话只执行一次（用它跑一次登录，所有用例共享 token）
   `scope="function"`（默认） = 每条用例都执行一次（用它保证用例之间数据互不污染）
"""

import uuid

import pytest

from api.account_api import AccountApi
from common.config import get_config
from common.http_client import HttpClient
from common.logger import get_logger


@pytest.fixture(scope="session", autouse=True)
def clean_db():
    """★ 测试数据治理：本次运行开始前清空数据库。

    为什么必须有它：
      上一次跑留下的用户/订单，会让这一次的用例莫名其妙地失败（典型症状是注册返回 409）。
      「用例可重复执行」是自动化测试的**底线要求** ——
      一旦用例要靠"上次没跑过"才能通过，它就不再是资产，而是负担。

    ★ 判断格：这个做法有个前提 —— 测试环境的数据**可以随便删**。
      如果被测的是一套共用测试环境，你就不能清库，只能靠「随机数据 + 用完清理」
      （data/cases.yaml 里的 {suffix} 就是干这个的）。
      面试被问「测试数据怎么隔离」，把这两种情况都说出来。
    """
    import sqlite3

    from sut.app import DB_PATH  # ★ 注意：这里确实耦合了被测系统，属于有意的取舍

    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            conn.executescript(
                "DELETE FROM sessions; DELETE FROM orders; DELETE FROM users;"
            )
            conn.commit()
    yield


@pytest.fixture(scope="session")
def cfg():
    return get_config()


@pytest.fixture(scope="session")
def log():
    return get_logger("autotest")


@pytest.fixture(scope="session")
def client(cfg, log):
    """全局 HTTP 客户端。整个会话共用一个，复用连接。"""
    c = HttpClient(cfg["base_url"], cfg["timeout"], log)
    yield c
    c.close()


@pytest.fixture(scope="session")
def account_api(client):
    return AccountApi(client)


@pytest.fixture(scope="session")
def test_user():
    """造一个本次运行唯一的用户名。

    ★ 为什么不用固定的 "alice"：
      第二次跑用例时 alice 已经存在了，注册接口会返回 409，用例就红了 ——
      这就是典型的「用例不可重复执行」。加个随机后缀就解决了。
    """
    suffix = uuid.uuid4().hex[:8]
    return {"username": f"qa_{suffix}", "password": "Pw_123456"}


@pytest.fixture(scope="session")
def logged_in_user(client, account_api, test_user, log):
    """注册并登录一个新用户，把 token 挂到 client 上，返回用户信息。

    ★ 这就是「参数关联」的落地：login 返回的 token 自动进了后续所有请求的头。
    """
    account_api.register(test_user["username"], test_user["password"])
    resp = account_api.login(test_user["username"], test_user["password"])
    assert resp.status_code == 200, f"前置登录失败：{resp.status_code} {resp.text[:200]}"

    token = resp.json()["token"]
    client.set_token(token)
    log.info("测试用户 %s 登录成功", test_user["username"])
    return {**test_user, "token": token}


@pytest.fixture
def anonymous_client(cfg):
    """一个不带任何认证信息的干净客户端，用于「未登录访问」这类异常用例。"""
    c = HttpClient(cfg["base_url"], cfg["timeout"])
    yield c
    c.close()
