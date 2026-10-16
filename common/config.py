"""多环境配置。

★ 为什么要有这一层：
   `base_url` 如果硬编码在用例里，换一个环境（本地 → CI → 预发）就要改代码。
   把它抽到配置里之后，切环境只改一个环境变量，用例代码一行都不用动。

用法：
    AUTOTEST_ENV=ci pytest
"""

import os

# ── 环境表 ──────────────────────────────────────────────────────────
# ★ 判断格：这里现在只有 local / ci，因为本地和 CI 都是起在 127.0.0.1:8000。
#   等你以后有预发/测试环境了，照这个格式加一条就行。
ENVS = {
    "local": {
        "base_url": "http://127.0.0.1:8000",
        "timeout": 5,
    },
    "ci": {
        "base_url": "http://127.0.0.1:8000",
        "timeout": 10,
    },
}

DEFAULT_ENV = "local"


def current_env() -> str:
    """当前环境名，来自环境变量 AUTOTEST_ENV，默认 local。"""
    return os.getenv("AUTOTEST_ENV", DEFAULT_ENV)


def get_config() -> dict:
    """取当前环境的配置。环境名写错时立刻报错，不要静默回退成默认值。"""
    name = current_env()
    if name not in ENVS:
        raise ValueError(
            f"未知环境 {name!r}，可选：{list(ENVS)}。"
            f"检查环境变量 AUTOTEST_ENV。"
        )
    cfg = {"env": name, **ENVS[name]}

    # ★ 允许用环境变量覆盖 base_url。
    #
    #   为什么需要这个：
    #     如果本机已经有一个常驻的 uvicorn 占着 8000，脚本再起一个会【绑不上端口】——
    #     而它的健康检查却会成功（因为**别人的**服务在应答）。
    #     结果就是：你以为在测刚启动的服务，实际上测的是那个常驻的旧服务。
    #     （这个坑我真踩过：改了代码却一直看到旧行为，排查了三次。）
    #
    #   有了这个覆盖，脚本就可以把服务起在别的空闲端口，
    #   再用 AUTOTEST_BASE_URL 告诉测试"去那儿测"，两边就不会串台。
    override = os.getenv("AUTOTEST_BASE_URL")
    if override:
        cfg["base_url"] = override.rstrip("/")
    return cfg
