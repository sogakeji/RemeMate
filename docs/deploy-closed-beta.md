# 闭测部署最小清单

目标：小范围邀请朋友试用，不开放注册。

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
- Alembic 迁移是否到 head
- `SECRET_KEY` / `DATA_ENCRYPTION_KEY`
- 批改与 NSFW 所需的 LLM provider 是否配置

## 创建闭测账号

普通账号：

```bash
flask create-user --email friend@example.com --name "Friend"
```

法国朋友学中文：

```bash
flask create-user \
  --email friend@example.com \
  --name "Friend" \
  --language zh \
  --feedback-language fr
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
