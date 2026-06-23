"""第三层防御：RLS 的 GUC 注入。

见 docs/design/data-isolation-security.md。

为什么用 after_begin 事件而不是 before_request 设一次：
set_config(..., is_local=true) 是事务级，COMMIT 后即失效。一个请求里多次 commit
（造句保存后渲染 ORM 触发 refresh、复习评分后再查下一张牌）时，后续事务会丢 GUC →
RLS fail-closed 看不到自己的行（review A1e）。改为监听每个事务的 after_begin，保证
每个事务一开始就带上 GUC，多 commit 也始终有效。

为什么 uid 缓存在 g 而不是在事件里读 current_user：
在 after_begin 里访问 current_user 会触发 Flask-Login 去 db.session 加载用户，而此刻
session 正在 provisioning 连接 → 重入报错。故在 before_request 先把 uid 存进 g
（那里加载用户是安全的），事件里只读 g、绝不碰 session。
"""
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from flask import g, has_request_context
from flask_login import current_user

from app.extensions import db


def set_request_rls_user():
    """before_request：缓存 uid 到 g，并把 GUC 设到「当前已开事务」上。

    访问 current_user 会触发用户加载，从而开启一个事务——那个事务的 after_begin 在
    g.rls_uid 尚未设置时已跑过（拿到 None）。所以这里算出 uid 后，必须立即对当前
    session 再设一次 GUC，覆盖这个已开事务；后续 commit 产生的新事务由 after_begin 兜住。
    """
    uid = current_user.id if current_user.is_authenticated else None
    g.rls_uid = uid
    if uid is not None:
        db.session.execute(
            text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(uid)}
        )


@event.listens_for(Session, "after_begin")
def _set_rls_on_begin(session, transaction, connection):
    """每个事务开始即注入 GUC（多 commit 安全）。只读 g，不触 session/current_user。"""
    if not has_request_context():
        return
    uid = g.get("rls_uid")
    if uid is None:
        return
    # uid 来自 current_user.id，必为整数；int() 强校验后内联，无注入面。
    connection.exec_driver_sql(
        f"SELECT set_config('app.current_user_id', '{int(uid)}', true)"
    )
