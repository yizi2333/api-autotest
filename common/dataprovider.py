"""数据驱动：把用例数据从代码里拿出来。

★ 为什么值得单独一层：
   如果登录的 10 个异常场景写成 10 个函数，改一个密码就要改 10 处。
   放到 YAML 里之后，「加一个场景」= 加 5 行 YAML，代码一行不动。
   面试问「数据驱动的好处」，这就是你的答案 —— 不是背的，是你真这么写的。
"""

from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_cases(key: str) -> list[dict]:
    """读取 data/cases.yaml 里的某一组用例数据。"""
    path = DATA_DIR / "cases.yaml"
    with path.open(encoding="utf-8") as fh:
        all_data = yaml.safe_load(fh)

    if key not in all_data:
        raise KeyError(f"cases.yaml 里没有 {key!r}，现有分组：{list(all_data)}")
    return all_data[key]


def substitute(raw: str, **values) -> str:
    """把数据里的 {占位符} 换成运行时变量。

    例：substitute("qa_{suffix}", suffix="a1b2c3d4") -> "qa_a1b2c3d4"

    ★ 为什么需要它：固定用户名第二次跑就会「已存在」，
      用例变得不可重复执行。用随机后缀就解决了。
    """
    return raw.format(**values) if isinstance(raw, str) else raw
