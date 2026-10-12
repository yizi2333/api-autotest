"""日志封装。

★ 为什么测试框架也要认真打日志：
   用例失败时，报告里只有一句 `assert 401 == 200`。
   但「请求发了什么、响应回了什么、耗时多少」全在日志里 —— 那才是定位问题的依据。
"""

import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "report" / "logs"

_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str = "autotest") -> logging.Logger:
    """取一个同时输出到控制台和文件的 logger。

    重复调用同名 logger 不会重复加 handler（否则日志会翻倍）。
    """
    logger = logging.getLogger(name)
    if logger.handlers:          # ★ 已经配过就直接返回，避免 handler 叠加
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(_FORMAT, _DATEFMT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_DIR / "autotest.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
