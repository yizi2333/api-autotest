"""账号相关接口定义。

★ 这一层的职责只有一件事：**把接口签名说清楚**。
  它不做断言、不做判断，就是「怎么调这个接口」。
"""

from common.http_client import ApiResponse, HttpClient


class AccountApi:
    BASE = "/api/account"

    def __init__(self, client: HttpClient):
        self.client = client

    def register(self, username: str, password: str) -> ApiResponse:
        return self.client.post(
            f"{self.BASE}/register",
            json={"username": username, "password": password},
        )

    def login(self, username: str, password: str) -> ApiResponse:
        return self.client.post(
            f"{self.BASE}/login",
            json={"username": username, "password": password},
        )

    def profile(self) -> ApiResponse:
        return self.client.get(f"{self.BASE}/profile")

    # ── TODO(D4)：你来补 ────────────────────────────────────────────
    # 1. 如果被测系统有「修改密码」接口，加一个 change_password(old, new)
    # 2. 如果被测系统有「充值/余额」接口，加一个 recharge(amount)
    #
    # ★ 判断格：想清楚这个接口的**必填参数**和**可选参数**分别是什么，
    #   可选参数一定要给默认值（这样调用方不用每次都传）。
