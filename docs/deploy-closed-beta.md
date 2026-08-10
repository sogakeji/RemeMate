# 闭测部署最小清单（默认不开放注册；按两阶段批准可开启）

目标：小范围邀请朋友试用，不开放注册。

## 基础部署环境变量

服务器 `.env` 至少要有：

```bash
FLASK_APP=wsgi:app
FLASK_ENV=production

DATABASE_URL=postgresql://rememate:...@127.0.0.1:5432/rememate
MIGRATE_DATABASE_URL=postgresql://rememate_owner:...@127.0.0.1:5432/rememate
DISPATCH_DATABASE_URL=postgresql://rememate_dispatch:...@127.0.0.1:5432/rememate
PUBLIC_BASE_URL=https://rememate.com

SECRET_KEY=...
DATA_ENCRYPTION_KEY=...

# 注册默认不开放。只有第二次人工批准后才将开关改为 true。
OPEN_REGISTRATION_ENABLED=false

# 以下邮件配置与 TTL/限频 override 仅在获批开启前配置，关闭态无需填写：
# RESEND_API_KEY=...
# AUTH_EMAIL_FROM="RemeMate <no-reply@rememate.com>"
# AUTH_MAIL_TIMEOUT_SECONDS=5
# REGISTRATION_TOKEN_TTL_SECONDS=86400
# PASSWORD_RESET_TOKEN_TTL_SECONDS=3600
# AUTH_EMAIL_PER_MINUTE_LIMIT=3
# AUTH_EMAIL_PER_HOUR_LIMIT=5
# AUTH_CLIENT_PER_HOUR_LIMIT=20
# AUTH_GLOBAL_EMAIL_PER_DAY_LIMIT=200

# LLM 二选一：
# 方案 A：DeepSeek 直连
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 方案 B：OpenAI-compatible 网关，例如 opencode go 跑 DeepSeek 模型
# OPENAI_API_KEY=...
# OPENAI_BASE_URL=http://127.0.0.1:11434/v1
# OPENAI_MODEL=deepseek-chat
```

生成密钥：

```bash
.venv/bin/python -c "import secrets;print(secrets.token_hex(32))"
.venv/bin/python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

## 注册邮件配置与上线闸门

生产部署默认必须保持 `OPEN_REGISTRATION_ENABLED=false`。关闭时，注册请求、Resend、发件人和公开站点地址不会成为 `flask doctor --strict` 的告警；需要启用注册邮件时，再单独完成配置和人工批准。

新增配置如下：

- `OPEN_REGISTRATION_ENABLED`：默认 `false`；注册入口和注册邮件流程的总开关。
- `PUBLIC_BASE_URL`：无默认值；启用时必须是无凭据、无路径/query/fragment 的 HTTPS origin。
- `RESEND_API_KEY`：无默认值；启用时必须是真实配置值，不能使用空值或占位值。
- `AUTH_EMAIL_FROM`：无默认值；启用时必须是合法邮箱，可带 display name。
- `AUTH_MAIL_TIMEOUT_SECONDS`：默认 `5` 秒；邮件 HTTP 请求超时。
- `REGISTRATION_TOKEN_TTL_SECONDS`：默认 `86400` 秒（24 小时）。
- `PASSWORD_RESET_TOKEN_TTL_SECONDS`：默认 `3600` 秒（1 小时）。
- `AUTH_EMAIL_PER_MINUTE_LIMIT`：默认 `3`，单邮箱每分钟。
- `AUTH_EMAIL_PER_HOUR_LIMIT`：默认 `5`，单邮箱每小时。
- `AUTH_CLIENT_PER_HOUR_LIMIT`：默认 `20`，单 client/IP 每小时。
- `AUTH_GLOBAL_EMAIL_PER_DAY_LIMIT`：默认 `200`，全局实际邮件每天。

只有 `OPEN_REGISTRATION_ENABLED=true` 时，`flask doctor --strict` 才要求 Resend key、合法 `AUTH_EMAIL_FROM` 和 HTTPS `PUBLIC_BASE_URL`，并分别报告三项配置 OK/WARN。doctor 只输出安全分类，不输出 key、密码、URL 凭据或 token；它不会发送网络邮件请求。

### 非生产测试域真实投递清单

真实投递只允许使用隔离的非生产测试域和独立测试账号：

1. 在 secret manager 或远端运行环境临时配置 Resend key、已验证的测试发件人和 HTTPS 测试 origin；不要把凭据写入仓库、文档或 `.env` 示例。
2. 设置 `OPEN_REGISTRATION_ENABLED=true`，先运行 `flask doctor --strict`，确认三项邮件配置为 OK。
3. 分别验证新邮箱注册验证邮件、已有邮箱的 account guidance 邮件、密码重置邮件；确认邮件链接能进入对应流程。
4. 检查应用日志和 Resend 投递日志，只核对安全的事件状态/provider message id；确认日志中没有 raw token、完整链接、API key 或密码。
5. 测试结束立即恢复 `OPEN_REGISTRATION_ENABLED=false`，再次运行 doctor；保留必要的投递状态记录，不保留 token 或凭据。

### 生产分两次人工批准

第一次批准只覆盖部署和 schema：部署代码、执行迁移、运行 `flask doctor --strict`，并明确保持 `OPEN_REGISTRATION_ENABLED=false`。此阶段不开放注册入口，也不应产生注册验证邮件。

第二次必须获得明确的独立批准，才可在 secret manager 配置 Resend key、发件人和 HTTPS public origin，并将 `OPEN_REGISTRATION_ENABLED` 改为 `true`；随后再次运行 `flask doctor --strict`，再按发布清单做小范围人工 smoke check。

关闭注册闸门只阻止新的注册请求，不会撤销已经发出的验证链接。按默认 `REGISTRATION_TOKEN_TTL_SECONDS=86400`，关闸后旧验证链接在其签发后的 24 小时内仍可能有效。

生产启动会 fail fast：`SECRET_KEY`、`DATA_ENCRYPTION_KEY`、三条数据库连接缺失时不会启动；LLM 需要 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` 至少配置一个，且不能仍是 `CHANGE_ME`。`DATA_ENCRYPTION_KEY` 必须是 Fernet key。

## 部署后自检

```bash
cd /srv/rememate
. .venv/bin/activate
flask db upgrade
flask doctor --strict
```

`doctor --strict` 会检查：

- app 数据库连接
- dispatch/provisioning 数据库连接
- migrate/owner 数据库连接
- Alembic 迁移是否到 head
- `SECRET_KEY` / `DATA_ENCRYPTION_KEY`，包括 Fernet key 格式
- 是否有至少一个 active admin
- 批改与 NSFW 所需的 LLM provider 是否配置

`doctor --strict` 有 WARN 也会失败，适合每次部署后作为放行条件。

## 创建闭测账号

管理员可以登录网页后进入顶部“管理”页创建账号。适合日常闭测运营。

网页管理页只负责创建可登录账号，不预设学习语言和母语。朋友登录后自行在设置页选择。

CLI 仍保留，适合首次创建唯一管理员账号或服务器应急操作。

普通账号：

```bash
flask create-user --email friend@example.com --name "Friend"
```

首次创建管理员账号：

```bash
flask create-user \
  --email you@example.com \
  --name "Admin" \
  --admin
```

命令会打印初始密码。通过安全渠道发给对方，首次闭测后可用：

```bash
flask reset-password --email friend@example.com
```

停用账号：

```bash
flask deactivate-user --email friend@example.com
```

重置今日额度：

```bash
flask reset-quota --email friend@example.com
```

## Review Story 保留数据清理

Review Story 是短期私有缓存，不是故事历史。ready 故事正文最多保留 7 天；失败或中断的输入快照
也在最后更新时间超过 7 天后清理。`learning_funnel_events` 不含正文，保留 180 天。

先预览，不会修改数据库：

```bash
flask cleanup-review-stories
```

输出中的 `runs` 和 `events` 是本次符合清理条件的行数。执行删除前，按本项目部署规范用 PostgreSQL
owner 备份数据库；不要使用受 FORCE RLS 限制的 app 角色做备份。

```bash
sudo -u postgres pg_dump -Fc rememate > /home/ubuntu/rememate-backups/rememate-$(date +%F-%H%M%S).dump
flask cleanup-review-stories --apply
flask cleanup-review-stories
```

最后一次 dry-run 应显示 `runs=0 events=0`。命令只使用 `DISPATCH_DATABASE_URL`，缺少后台连接时
会拒绝运行。闭测期至少每日执行一次；正式调度前仍保留人工检查，不把清理失败变成登录、复习或
写作流程的门禁。

## SessionPad 带语境候选发布检查

本版本包含顺序迁移 `a2b3c4d5e6f7` 与 `b3c4d5e6f7a8`。第二条迁移会在创建同来源活动候选唯一索引前
审计历史重复；若发现重复会明确中止，不自动合并或删除用户数据。此时停止发布、保留数据库备份并先
人工审计，不要直接 stamp 或修改迁移绕过检查。

升级后确认只有一个 migration head：

```bash
flask db upgrade
flask db current
flask db heads
flask doctor --strict
```

SessionPad 浏览器冒烟至少覆盖：

- 从自己复盘的「帮自己记」加入候选，确认进入专属单候选审核；
- 从收到的反馈包使用 AI 建议或人工填写 `term + context`，AI 不可用时仍可人工继续；
- 编辑候选语境后确认显示为用户整理；清空语境后仍可接受；
- 不点击“将语境用作例句”时，接受和入库不会自动生成最终例句；显式点击并接受时才保存例句；
- 已在同语言生词本中的词只建立关联，不新增重复词、不覆盖既有释义或例句；
- 待审核页不出现批量接受，旧通用接受、忽略和全部入库入口不能处理 SessionPad 候选；
- 分别用发送方、接收方和第三个账号确认候选、语境及采纳状态保持接收方私有；
- 在 1440px 桌面和 390px 移动端检查来源条、长语境、操作按钮及固定底部导航，无横向溢出或遮挡。

迁移包含数据库结构变化。若升级后需要回滚代码，不能只 checkout 旧提交继续运行；必须先评估
`b3c4d5e6f7a8 -> a2b3c4d5e6f7 -> f1a2b3c4d5e6` 的 downgrade 是否安全，或恢复部署前数据库备份。

## 部署后冒烟

```bash
curl -fsS http://127.0.0.1:8891/healthz
```

浏览器里走一遍：

- 管理员登录
- 创建一个普通测试账号
- 普通账号登录后选择“正在学：中文”“母语：法语”
- 加一个中文词
- 造句，确认 AI 能用法语批改/解释
- 保存并公开到广场
- 从历史或广场取消公开

## 朋友测试路径

1. 登录
2. 到设置确认“正在学：中文”、“母语：法语”
3. 加一个中文词
4. 用这个词造句，确认 AI 用法语解释
5. 保存并发布到广场
6. 在广场或历史里取消公开
7. 写一篇三行日记

## 不做的事

- 不开放注册
- 不让用户自建邀请
- 不在仓库或文档里记录真实 API key

## 快速回滚

如果部署后 `doctor --strict` 或冒烟失败：

```bash
git log --oneline -5
git checkout <上一可用提交>
flask db current
kill -HUP <gunicorn-master-pid>
curl -fsS http://127.0.0.1:8891/healthz
```

如果已经跑过新的数据库迁移，不要直接回滚代码后继续使用；先确认迁移是否需要 downgrade 或恢复备份。
