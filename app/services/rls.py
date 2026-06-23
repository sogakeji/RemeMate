"""第三层防御：RLS 的请求级 GUC 注入与清除。

见 docs/design/data-isolation-security.md §GUC 注入 / §RLS 连接复用安全要求。

要点：
- 用 set_config(...) 而非 SET（SET 不接受绑定参数）。
- 第三参 is_local=true 等价 SET LOCAL，事务级。
- 未登录请求不设 GUC → current_setting 两参返回 NULL → 所有 policy fail-closed。
- teardown 把 GUC 置空，防连接池跨请求残留。
"""
from sqlalchemy import text
from flask_login import current_user

from app.extensions import db


def set_rls_user():
    """before_request：注入当前用户 ID 到事务级 GUC。"""
    if current_user.is_authenticated:
        db.session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(current_user.id)},
        )


def reset_rls_user(exc=None):
    """teardown_request：连接归还池前清除 GUC。"""
    try:
        db.session.execute(text("SELECT set_config('app.current_user_id', '', true)"))
    except Exception:
        # teardown 阶段连接可能已失效，吞掉异常避免掩盖原始错误
        db.session.rollback()
