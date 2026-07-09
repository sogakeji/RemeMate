# 闭测部署最小清单

目标：小范围邀请朋友试用，不开放注册。

## 必填环境变量

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
