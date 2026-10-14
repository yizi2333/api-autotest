"""被测系统：账号 + 订单 的 mini 中台服务。

启动：
    uvicorn sut.app:app --port 8000 --reload
接口文档（FastAPI 自动生成，面试可以现场打开）：
    http://127.0.0.1:8000/docs

★ 为什么选「账号 + 订单」这个业务：
   目标岗位 JD 原话是「负责**账号体系、支付交易**等中台核心业务的全链路质量保障」。
   业务域对上，面试时你的项目就是「和岗位高度相关」，而不是随便找了个网站测。

═══════════════════════════════════════════════════════════════════
接口契约（★ 这是测试的依据，先看懂它再动手）
═══════════════════════════════════════════════════════════════════
GET  /health                     → 200 {"status":"ok"}
POST /api/account/register       → 201 {"id","username"}
                                   409 用户名已存在
POST /api/account/login          → 200 {"token","username"}
                                   401 用户名或密码错误
GET  /api/account/profile        → 200 {"username","balance"}     需要 token
                                   401 未认证 / token 无效
POST /api/order/create           → 201 {"order_id","item","amount","status"}  需要 token
GET  /api/order/{order_id}       → TODO(D2) 由你实现（★ 是 GET 不是 POST —— 查订单是读操作）
GET  /api/order/list             → TODO(D2) 由你实现
"""

# ★ 上面这一栏是【接口契约】，下面文件末尾那一栏是【实现要求】。
#   两处必须一致 —— 之前这里把 `GET /api/order/{order_id}` 误写成了 `POST`，
#   而底部 TODO 写的是 GET。照着顶部实现就会写成一个"用 POST 查订单"的接口，
#   语义是错的（POST 不幂等、不该用来读）。
#   ★ 教训：**同一件事写在两个地方，就一定会有一处先烂。**
#     要么只写一处，要么加一个检查。这里的检查就是 scripts/preflight_check.ps1。

import secrets
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).resolve().parent / "sut.db"

app = FastAPI(title="Account & Order SUT", version="0.1.0")


# ═══════════════════════════════════════════════════════════════════
# 数据层
# ═══════════════════════════════════════════════════════════════════

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(get_conn()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT    NOT NULL UNIQUE,
                password TEXT    NOT NULL,          -- ★ 真实系统必须存哈希，这里是靶子系统
                balance  REAL    NOT NULL DEFAULT 100.0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token    TEXT PRIMARY KEY,
                username TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT    NOT NULL,
                item     TEXT    NOT NULL,
                amount   REAL    NOT NULL,
                status   TEXT    NOT NULL DEFAULT 'created'
            );
            """
        )
        conn.commit()


init_db()


# ═══════════════════════════════════════════════════════════════════
# 请求体模型
# ★ pydantic 会自动做类型校验：少字段 / 类型不对 → FastAPI 直接返回 422
# ═══════════════════════════════════════════════════════════════════

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=64)


class LoginIn(BaseModel):
    # ★ 这里加长度校验是【产品决策】，不是随手写的：
    #   空用户名属于「请求本身不合法」→ 422；
    #   如果不在这层拦住，它会一路走到查库，返回 401 ——
    #   把「参数非法」和「认证失败」混成一类，线上排查时很难区分。
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=64)


class OrderIn(BaseModel):
    item: str = Field(min_length=1, max_length=64)
    amount: float = Field(gt=0)          # ★ 边界：amount 必须 > 0


# ═══════════════════════════════════════════════════════════════════
# 认证
# ═══════════════════════════════════════════════════════════════════

def current_user(authorization: Optional[str] = Header(default=None)) -> str:
    """从 Authorization: Bearer <token> 里解析出用户名。

    ★ 测试重点：这条依赖决定了所有「未登录 / token 无效」的异常场景。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证信息")

    token = authorization.removeprefix("Bearer ").strip()
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT username FROM sessions WHERE token = ?", (token,)
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=401, detail="token 无效或已过期")
    return row["username"]


# ═══════════════════════════════════════════════════════════════════
# 接口
# ═══════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/account/register", status_code=201)
def register(body: RegisterIn):
    with closing(get_conn()) as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (body.username,)
        ).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="用户名已存在")

        cur = conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (body.username, body.password),
        )
        conn.commit()
        return {"id": cur.lastrowid, "username": body.username}


@app.post("/api/account/login")
def login(body: LoginIn):
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT username FROM users WHERE username = ? AND password = ?",
            (body.username, body.password),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        token = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO sessions (token, username) VALUES (?, ?)",
            (token, row["username"]),
        )
        conn.commit()
        return {"token": token, "username": row["username"]}


@app.get("/api/account/profile")
def profile(user: str = Depends(current_user)):
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT username, balance FROM users WHERE username = ?", (user,)
        ).fetchone()
    return {"username": row["username"], "balance": row["balance"]}


# ── TODO(D2)：订单模块，你来写 ──────────────────────────────────────
#
# 目标契约（照着这个实现，测试才有依据）：
@app.get("/api/order/{order_id}")
def get_order(order_id: int, user: str = Depends(current_user)):
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT id, username, item, amount, status FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if row["username"] != user:
        raise HTTPException(status_code=403, detail="无权访问该订单")
    return {
        "order_id": row["id"],
        "item": row["item"],
        "amount": row["amount"],
        "status": row["status"],
    }

# ① POST /api/order/create                       需要 token，status_code=201
#    成功 → {"order_id": 1, "item": "...", "amount": 9.9, "status": "created"}
#    ★ 要做的两件事：往 orders 表插一条；同时把 users.balance 扣掉 amount
#    余额不足 → 400 {"detail": "余额不足"}
#    （amount <= 0 已经由 OrderIn 的 Field(gt=0) 自动挡成 422，不用你写）·                                              
#
# ② GET /api/order/{order_id}                    需要 token
#    是本人的订单 → 200 {"order_id","item","amount","status"}
#    订单不存在   → 404
#    ★ 是【别人的】订单 → 403    ← 这是重点：水平越权场景，
#                                  也是测开面试最爱问的「接口测试要覆盖哪些异常场景」
#
# ③ GET /api/order/list                          需要 token
#    只返回【当前用户】的订单，且支持 ?status=created 过滤
#
# ★ 判断格：
#   写完之后自己想 —— 这三个接口里，哪个最容易被开发写出漏洞？为什么？
#   提示：想想「谁有权限看这条数据」这件事，服务端是靠什么判断的。
