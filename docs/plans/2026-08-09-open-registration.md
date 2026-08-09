# 低流量开放注册短计划

> 日期：2026-08-09  
> 状态：Approved；实施范围已获人工批准，但不授权部署或开启生产注册。  
> 依据：2026-08-09 grilling 决策、`docs/arch/auth-flow.md`、`docs/design/data-isolation-security.md`、`docs/BACKLOG.md`。

## 目标

在保留 Flask-Login、PostgreSQL 整数主键和现有 RLS 模型的前提下，增加完整但默认关闭的邮箱注册、邮箱验证和密码重置流程。首版优先缩短正常用户路径，同时把用户数据隔离和账号完整 provisioning 作为硬门槛。

用户最短路径：

1. 注册页只填写邮箱。
2. 用户点击 24 小时内单次有效的验证链接。
3. 系统原子创建完整账号并自动登录。
4. 用户设置至少 8 个字符的个人密码；完成前只能访问设密和登出。
5. 显示名暂用邮箱前缀，时区、学习语言等沿用现有默认值，之后可在产品内修改。

## 已确认边界

- `OPEN_REGISTRATION_ENABLED` 默认关闭；关闭时隐藏入口并拒绝新的注册申请。
- 已经发出的验证链接不受后来关闸影响，在 24 小时有效期内仍可创建账号。
- 关闭注册不影响已完成注册的用户登录和使用。
- 注册、重发验证和忘记密码对外使用统一响应，不公开邮箱是否已存在；现有用户只在邮件中收到登录/重置指引。
- 密码重置链接 1 小时、单次有效；完成后自动登录，但不新增服务端会话版本，也不撤销其他设备的旧 cookie。
- 无 CAPTCHA。邮件限频默认可配置为：单邮箱 3 次/分钟且 5 次/小时、单 IP 20 次/小时、全局 200 封/天。
- 新注册用户直接沿用现有各功能 AI 额度；本计划不增加全局系统-key 预算保险丝，也不宣称系统 AI 总成本有硬上限。
- 首次开启后直接持续开放，不做百分比灰度或秘密 URL 准入。

## 模块设计

### 1. `account_access` 深模块

新增一个账号访问模块，作为注册、验证、强制设密和密码重置的唯一业务入口。路由只负责表单、CSRF、响应和登录 cookie，不直接操作 token、邮件、限频或 provisioning。

建议的小接口：

```python
request_registration(email, client_key) -> RequestReceipt
verify_registration(raw_token) -> ActivatedAccount
set_initial_password(user_id, password) -> None
request_password_reset(email, client_key) -> RequestReceipt
reset_password(raw_token, password) -> UserId
```

接口承诺统一封装：邮箱规范化、统一外部响应、token 单次消费、过期判断、并发幂等、限频、邮件投递和失败回滚。集成测试以该接口及真实 HTTP 结果为测试面，不越过接口断言内部步骤。

### 2. 邮件投递 seam

Resend 是 true external dependency。在账号访问模块内部定义最小邮件投递 port，只暴露“发送验证邮件”和“发送密码重置/现有账号指引”；生产使用 Resend adapter，测试使用记录型 fake adapter。

不把 Resend SDK、HTTP 状态码或模板变量暴露给路由。实施前只需按 Resend 官方文档确认发送接口、超时、幂等和错误响应；优先复用现有 `requests`，除非官方 SDK 能明显缩小接口和错误处理面。

### 3. provisioning seam

继续复用 `app/services/provisioning.py`，不在注册路由复制 `users + user_settings + user_quota` 写入逻辑。扩展 provisioning，使验证成功能在一个事务内创建：

- `User`；
- `UserSettings`；
- `UserQuota`，且 `quota_reset_at` 非空；
- 不可变外部 UUID；
- `password_setup_required=True`。

验证前不创建正式用户。验证成功时写入不可猜测的内部密码 hash；用户设密前，普通密码登录不可用。

### 4. 匿名认证控制面

新增持久化 challenge 记录，至少区分 `registration` 与 `password_reset`，保存 token digest、规范化邮箱或目标用户、过期时间、消费时间和限频所需元数据。原始 token 只出现在邮件 URL 中，不落库。

这些记录在未登录请求中必须可访问，因此不能套用依赖 `app.current_user_id` 的用户数据 RLS policy。它们属于匿名认证控制面，只允许账号访问模块读写，不承载业务数据。并发消费必须通过数据库条件更新或行锁保证单次有效。

## 数据变化

对现有 `users` 表增加：

- `public_id UUID`：不可变、唯一；迁移为全部现有用户回填，新用户创建时生成；内部 FK、Flask-Login session 和 RLS GUC 继续使用整数 `id`。
- `password_setup_required BOOLEAN NOT NULL DEFAULT FALSE`：现有用户回填 `FALSE`，邮件验证创建的新用户初始为 `TRUE`。

新增匿名认证 challenge/邮件发送记录表及必要索引。迁移必须手写审查，不接受 Alembic autogenerate 顺带删除既有函数索引、复合外键或其他 metadata 漂移。

## 路由与门禁

建议新增：

- `GET/POST /register`
- `GET /verify-email/<token>`
- `GET/POST /set-password`
- `GET/POST /forgot-password`
- `GET/POST /reset-password/<token>`

全局请求门禁在已登录但 `password_setup_required=True` 时，仅允许设密和登出；其他业务路由、用户数据和 AI 调用全部重定向到设密页。完成设密后清除该状态并进入正常产品。

`OPEN_REGISTRATION_ENABLED=False` 时：

- Landing/Login 不显示注册入口；
- `/register` 不接受新的注册申请；
- 已发验证链接仍可验证并建号；
- 忘记密码保持可用；
- 已注册用户不受影响。

## 配置与运行保障

新增配置至少包括：

- `OPEN_REGISTRATION_ENABLED`，缺失或非法时按关闭处理；
- `RESEND_API_KEY`、发件地址和公开站点 URL；
- 验证/重置有效期；
- 邮箱、IP、全局邮件限频值。

当注册开启时，生产 `flask doctor --strict` 必须检查 Resend 配置、发件地址和 `PUBLIC_BASE_URL`。IP 限频只能使用经过明确信任的反向代理客户端地址；未确认代理 hops 前不得直接信任任意 `X-Forwarded-For`。

邮件发送失败不得创建正式用户或消费验证资格，并向用户返回可重试的通用提示。限频状态必须持久化到 PostgreSQL，不能依赖单进程内存计数。

## 实施切片

### OR1：身份与 provisioning 地基

- 增加 `public_id`、`password_setup_required` 与 challenge 数据模型/迁移。
- 为现有用户回填 UUID，保持整数 PK、Flask-Login 和 RLS 不变。
- 扩展 provisioning，覆盖完整原子建号和并发同邮箱冲突。
- 只交付地基，不新增公开入口。

验收：迁移往返与单一 head 正常；现有用户可继续登录；新建账号永远同时拥有 settings、quota、reset_at 和 UUID；跨用户 RLS 回归通过。

### OR2：账号访问模块与邮件 adapter

- 实现 challenge 生命周期、统一响应、透明限频和 Resend port。
- 使用 fake adapter 完成注册、现有邮箱、过期、重发、并发消费和邮件失败测试。
- 实现 1 小时密码重置；不改变现有登录锁定语义。

验收：token 只存 digest且单次有效；同一验证 token 并发只能建一个账号；限频组合和全局上限均有 PostgreSQL 集成测试。

### OR3：注册 UI、自动登录与强制设密

- 增加注册、验证、设密、忘记密码和重置页面及中英文文案。
- 接入默认关闭的前后端注册开关。
- 验证成功后自动登录；设密前封闭所有业务页面和 AI 路径。
- 注册页仅收邮箱，其他资料使用默认值。

验收：关闭态无入口且不能新申请；旧验证链接仍可激活；设密前无法访问用户数据；设密或重置后可正常使用；现有用户流程无回归。

### OR4：发布保障与持续开放

- 将新增配置加入部署文档与 `doctor --strict`。
- 在非生产环境用 Resend 测试域名完成真实投递冒烟。
- 运行认证/RLS/provisioning/额度定向测试后执行 `pytest -q`。
- 获得单独发布批准后部署，但保持注册开关关闭；完成生产迁移、strict doctor、HTTPS、日志和数据计数检查后再明确开启。

开启后持续观察注册成功率、Resend 失败、限频命中、注册 5xx 和新用户 AI 使用。出现数据越权、半初始化账号、邮件链路持续失败或注册持续 5xx 时，关闭新的注册申请；按已确认语义，已发验证链接仍可能在 24 小时内继续建号。

## 不在本计划内

- OAuth、magic link 登录、JWT 或替换 Flask-Login；
- CAPTCHA、邀请码、准入名单或百分比灰度；
- 服务端会话表、密码重置后强制注销其他设备；
- 新的 AI 全局预算、token 硬门禁或现有额度 TOCTOU 修复；
- 自动备份、Bitwarden 迁机、SQLAlchemy metadata 全量对齐或 CI migration 改造；
- 开放注册之外的 Landing、设置页或账号系统重设计。

## 已裁定的发布边界

2026-08-09 人工批准本计划并明确裁定：

1. 本计划取代 Backlog 中“开放注册前必须新增 token 硬约束”的要求；首版接受现有各功能额度不是系统 AI 总成本的硬保护。
2. 自动备份/异机副本与 Bitwarden 迁机评估继续作为独立运维改进，但不阻塞生产注册开关开启。

SQLAlchemy metadata 对齐和 CI migration 改造仍不混入本功能；OR4 继续要求在目标环境人工执行迁移检查、`flask doctor --strict`、HTTPS、日志和数据保持验证。计划批准授权进入 OR1–OR4 开发，不等于部署或开启生产注册；后二者仍需单独批准。
