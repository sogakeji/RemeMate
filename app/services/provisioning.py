"""账号 provisioning：建账号必须一次建全 User + UserSettings + UserQuota。

★ 必须走 BYPASSRLS 连接（DISPATCH_DATABASE_URL）：
FORCE RLS 下，CLI/无请求上下文时 GUC 未设，对 user_settings/user_quota 的 INSERT
会被 RLS 的 WITH CHECK 拒绝。所以 provisioning 不走 app 的 db.session，而是用
dispatch（BYPASSRLS）角色的独立连接。见 docs/design/data-isolation-security.md。

CLI 与未来的注册路由都复用本模块（auth-flow.md 的「三表一事务」要求）。
"""
import re
import secrets

from flask import current_app
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from app.models.user import User, UserSettings, UserQuota
from app.models.word import WordList
from app.services.timeutil import next_midnight_utc
from app.services import words as words_svc

DEFAULT_DAILY_LIMIT = 50_000


def _bypass_session() -> Session:
    """BYPASSRLS 角色的一次性 Session（CLI 一次性使用，用完 dispose）。"""
    engine = create_engine(current_app.config["DISPATCH_DATABASE_URL"])
    return Session(engine)


class UserExistsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _clean_language_codes(codes):
    seen, cleaned = set(), []
    for code in codes or []:
        code = (code or "").strip()
        if code not in words_svc._LANGUAGE_NAMES:
            raise ValueError(f"未知语言 code：{code!r}")
        if code not in seen:
            seen.add(code)
            cleaned.append(code)
    return cleaned


def _create_user_with_defaults_in_session(
        session, email, display_name, *, admin=False,
        timezone="Asia/Shanghai", password=None, learning_languages=None,
        feedback_language="zh", password_setup_required=False):
    """在调用方 Session/事务内完整建号，返回 User，不提交或关闭 Session。"""
    email = normalize_email(email)        # 邮箱大小写无关（M5）
    if not _EMAIL_RE.match(email):
        raise ValueError("邮箱格式不正确")
    password = password or secrets.token_urlsafe(12)
    learning = _clean_language_codes(learning_languages)
    if feedback_language not in words_svc._FEEDBACK_LANGUAGE_NAMES:
        raise ValueError(f"未知反馈语言 code：{feedback_language!r}")
    if session.query(User).filter_by(email=email).first():
        raise UserExistsError(email)

    user = User(
        email=email,
        display_name=display_name,
        password_hash=generate_password_hash(password),
        role="admin" if admin else "user",
        is_active=True,
        password_setup_required=password_setup_required,
        login_attempts=0,
        timezone=timezone,
        current_language=learning[0] if learning else None,
        learning_languages=",".join(learning) if learning else None,
    )
    session.add(user)
    session.flush()  # 拿 user.id

    session.add(UserSettings(
        user_id=user.id,
        feedback_language=feedback_language,
        notify_review_reminder=True,
        notify_daily_summary=True,
        notify_intake_done=True,
        notify_partner_activity=False,
    ))
    for code in learning:
        session.add(WordList(
            user_id=user.id,
            name=words_svc._language_name(code),
            language_code=code,
        ))
    session.add(UserQuota(
        user_id=user.id,
        daily_base_limit=DEFAULT_DAILY_LIMIT,
        tokens_used_today=0,
        bonus_tokens_today=0,
        quota_reset_at=next_midnight_utc(timezone),  # 必须初始化，禁留 None
    ))
    session.flush()
    return user


def create_user_with_defaults(email, display_name, *, admin=False,
                              timezone="Asia/Shanghai", password=None,
                              learning_languages=None,
                              feedback_language="zh"):
    """一事务建 User + UserSettings + UserQuota，返回 (user_id, 明文初始密码)。"""
    email = normalize_email(email)
    if not _EMAIL_RE.match(email):
        raise ValueError("邮箱格式不正确")
    password = password or secrets.token_urlsafe(12)
    session = _bypass_session()
    engine = session.bind
    try:
        try:
            user = _create_user_with_defaults_in_session(
                session, email, display_name, admin=admin, timezone=timezone,
                password=password, learning_languages=learning_languages,
                feedback_language=feedback_language,
            )
            session.commit()
        except IntegrityError:
            # 只把回滚后确认已存在的规范化邮箱视为并发重名。
            session.rollback()
            if session.query(User).filter_by(email=email).first() is not None:
                raise UserExistsError(email) from None
            raise
        return user.id, password
    finally:
        session.close()
        engine.dispose()


def _get_user_or_raise(session, email) -> User:
    user = session.query(User).filter_by(email=normalize_email(email)).first()
    if user is None:
        raise UserNotFoundError(email)
    return user


def reset_password(email, password=None):
    """重置密码，返回新明文密码。"""
    password = password or secrets.token_urlsafe(12)
    session = _bypass_session()
    engine = session.bind
    try:
        user = _get_user_or_raise(session, email)
        user.password_hash = generate_password_hash(password)
        user.login_attempts = 0
        user.locked_until = None
        session.commit()
        return password
    finally:
        session.close()
        engine.dispose()


def deactivate_user(email):
    session = _bypass_session()
    engine = session.bind
    try:
        user = _get_user_or_raise(session, email)
        user.is_active = False
        session.commit()
    finally:
        session.close()
        engine.dispose()


def reset_quota(email):
    """把今日额度清零并重置重置点。"""
    session = _bypass_session()
    engine = session.bind
    try:
        user = _get_user_or_raise(session, email)
        quota = session.get(UserQuota, user.id)
        if quota is None:
            quota = UserQuota(user_id=user.id, daily_base_limit=DEFAULT_DAILY_LIMIT)
            session.add(quota)
        quota.tokens_used_today = 0
        quota.bonus_tokens_today = 0
        quota.corrections_today = 0
        quota.imports_today = 0
        quota.quota_reset_at = next_midnight_utc(user.timezone)
        session.commit()
    finally:
        session.close()
        engine.dispose()
