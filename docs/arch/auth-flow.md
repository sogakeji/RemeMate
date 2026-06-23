# Auth 流程设计

> 记录日期：2026-06-22
> 状态：P1 实现

---

## 总体原则

- Session-based auth，Flask-Login 管理，不上 JWT
- P1 邀请制：无公开注册，管理员 CLI 建账号
- 密码 hash：Werkzeug `generate_password_hash` / `check_password_hash`
- 所有需要登录的路由加 `@login_required`
- Session Pad guest 通过独立 `guest_token` 鉴权，不走 Flask-Login

---

## 登录流程

```
GET /login → 渲染登录表单（CSRF token 嵌入）
    ↓
POST /login
    ├── 验证 CSRF token
    ├── 查 users WHERE email = ? AND is_active = True
    ├── check_password_hash(user.password_hash, form.password)
    ├── 失败 → 渲染表单 + 错误提示（不区分"用户不存在"和"密码错误"）
    └── 成功 → login_user(user, remember=False) → redirect(next or '/')
```

**安全细节**：
- 登录失败不区分原因，防止用户枚举
- `next` 参数必须验证是同域相对路径，防止开放重定向
- 连续失败 N 次（建议 5 次）→ 锁定账号 15 分钟（`users.locked_until` 字段）

---

## 登出流程

```
GET /logout → logout_user() → redirect('/login')
```

Session 由 Flask 的 signed cookie 管理，logout_user() 清除 session。

---

## @login_required 装饰器

Flask-Login 内置，未登录访问 → redirect `/login?next=<当前路径>`。

```python
login_manager.login_view = "auth.login"
login_manager.login_message = "请先登录"
```

所有蓝图的业务路由默认加 `@login_required`，公开页面（/login、/square 只读、session guest 页）显式豁免。

---

## Session Pad Guest 鉴权

Guest 不走 Flask-Login，走独立 token 机制：

```
用户打开 /sessions/<room_token>
    ├── 已登录 → 直接进入，role=guest
    └── 未登录 → 显示"输入昵称加入"表单
                → POST /sessions/<room_token>/join
                → 生成 guest_token（uuid4），存 session_participants
                → 写入 response cookie：guest_token=<uuid>（httponly, samesite=lax）
                → 进入会话页，后续 Socket.IO 事件携带 guest_token 验证身份
```

Guest token 随 session_room 过期（7天），不可跨房间复用。

---

## CLI 建账号

P1 不开放公开注册，管理员用 CLI 创建账号：

```bash
flask create-user --email user@example.com --name "Alice" [--admin]
```

执行后：
1. 生成随机初始密码并打印到终端（一次性，不存储明文）
2. **同一事务**写入 `users` + `user_settings` + `user_quota` 三张表（缺任一张，用户首次用 AI 必崩，见下警告）
3. 用户首次登录后可在 /settings 修改密码

> **★ 关键：provisioning 必须一次建全（回归 review A3）**
> 只插 `User` 一行的话：
> - `UserQuota.query.get(user_id)` 返回 `None` → quota.py 下一行 `AttributeError` → **任何新用户第一次点 AI = 500**。
> - `UserSettings` 缺失 → dispatch 的四个 notify 开关读不到，settings 页报错。
> - `quota_reset_at` 不初始化（`None`）→ `_maybe_reset` 永远跳过重置 → 当天烧满额度后**永久锁死 AI**。
> 所以 create_user 必须在同一事务建全三张表，且 `quota_reset_at` 初始化为下一个本地午夜。

```python
@app.cli.command("create-user")
@click.option("--email", required=True)
@click.option("--name", required=True)
@click.option("--admin", is_flag=True, default=False)
@click.option("--tz", default="Asia/Shanghai")
def create_user(email, name, admin, tz):
    import secrets
    from app.services.quota import _next_midnight_utc
    password = secrets.token_urlsafe(12)

    user = User(
        email=email,
        display_name=name,
        password_hash=generate_password_hash(password),
        role="admin" if admin else "user",
        is_active=True,
        timezone=tz,
    )
    db.session.add(user)
    db.session.flush()   # 拿到 user.id，三张表同事务

    settings = UserSettings(
        user_id=user.id,
        # 四个通知开关默认值（与 dispatch-multiuser.md 对齐）
        notify_review_reminder=True,
        notify_daily_summary=True,
        notify_intake_done=True,
        notify_partner_activity=False,
    )
    quota = UserQuota(
        user_id=user.id,
        daily_base_limit=50_000,
        tokens_used_today=0,
        bonus_tokens_today=0,
        quota_reset_at=_next_midnight_utc(tz),   # ★ 必须初始化，否则永不重置
    )
    db.session.add_all([settings, quota])
    db.session.commit()
    click.echo(f"用户已创建：{email}  初始密码：{password}")
```

> 同样地，未来开放注册（P2）的注册路由也必须复用这套「三表一事务」provisioning，建议抽成 `services/provisioning.py:create_user_with_defaults()` 供 CLI 和注册路由共用。

> **★ CLI 必须走 BYPASSRLS 连接**：FORCE RLS 后，CLI 没有请求上下文、GUC 未设，对 `user_settings`/`user_quota` 的 INSERT 会被 RLS 的 WITH CHECK 拒绝。`create-user` 等 CLI 命令统一用 `rememate_dispatch`（BYPASSRLS）engine，不走 app 的 `db.session`。详见 [data-isolation-security.md](../design/data-isolation-security.md) §CLI 必须绕过 RLS。上面的 `db.session` 仅示意三表一事务的写入顺序，实际连接用 BYPASSRLS engine。

其他 CLI 命令：
```bash
flask reset-password --email user@example.com   # 重置密码，打印新密码
flask deactivate-user --email user@example.com  # 停用账号
flask reset-quota --email user@example.com      # 重置今日 token 额度
```

---

## User 模型关键字段

```python
class User(db.Model, UserMixin):
    id              = db.Column(db.Integer, primary_key=True)
    email           = db.Column(db.String(255), unique=True, nullable=False)
    password_hash   = db.Column(db.String(255), nullable=False)
    display_name    = db.Column(db.String(100), nullable=False)
    role            = db.Column(db.String(20), default="user")  # user / admin
    is_active       = db.Column(db.Boolean, default=True)
    locked_until    = db.Column(db.DateTime, nullable=True)
    login_attempts  = db.Column(db.Integer, default=0)
    timezone        = db.Column(db.String(50), default="Asia/Shanghai")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

---

## P2 扩展预留

- 开放注册（邀请码或自由）：加 `invitations` 表，注册路由解除封锁
- 邮箱验证：`users.email_verified` 字段 + 发验证邮件流程
- OAuth（Google/GitHub）：Flask-Dance，P2 视需求添加
