# RemeMate Bark 定时复习提醒

这两个 systemd 单元负责每 15 分钟运行一次 RemeMate 的 Bark 复习提醒：

- `rememate-bark.timer`：在每小时的 `:00`、`:15`、`:30`、`:45` 触发，主机离线时由 `Persistent=true` 补跑。
- `rememate-bark.service`：以 `ubuntu` 用户运行 `/srv/rememate` 下的 `.venv`，并用 `flock` 防止重叠执行。

推送筛选、dry-run、Bark URL 校验、按用户隔离和幂等均由 `dispatch.runner` 与现有 `send_review_reminders` 负责。幂等记录写入已有的 `push_log`，不创建 `.dispatch_state.json` 或其他状态文件。

## 前置条件

确认生产代码和虚拟环境位于：

```text
/srv/rememate
/srv/rememate/.venv/bin/python
/srv/rememate/.env
```

`/srv/rememate/.env` 至少要提供 dispatch runner 所需的 `DISPATCH_DATABASE_URL`；如果要在 Bark 中生成点击复习链接，还要配置 `SECRET_KEY` 和 `PUBLIC_BASE_URL`。数据库连接应使用 `rememate_dispatch` BYPASSRLS 角色。

## 安装或更新单元

在代码已更新到目标版本后执行：

```bash
cd /srv/rememate
sudo install -m 0644 deploy/systemd/rememate-bark.timer /etc/systemd/system/rememate-bark.timer
sudo install -m 0644 deploy/systemd/rememate-bark.service /etc/systemd/system/rememate-bark.service
sudo systemd-analyze verify /etc/systemd/system/rememate-bark.timer /etc/systemd/system/rememate-bark.service
sudo systemctl daemon-reload
sudo systemctl enable --now rememate-bark.timer
```

安装后只启用 timer；它会按时启动 oneshot service。不要再同时启用另一套 Bark 定时器，否则会产生不必要的并发尝试；已有 `push_log` 幂等会防止同一用户、单词和本地日期重复写入。

## 验证

先检查 timer 是否已启用以及下一次触发时间：

```bash
systemctl list-timers rememate-bark.timer
systemctl status rememate-bark.timer --no-pager
```

可以先手动执行 dry-run。该命令只统计，不发送 Bark，也不写 `push_log`：

```bash
sudo -u ubuntu bash -lc '
  set -a
  . /srv/rememate/.env
  set +a
  cd /srv/rememate
  .venv/bin/python -m dispatch.runner bark --dry-run
'
```

需要验证真实执行时，手动启动一次 service，然后查看统计和日志：

```bash
sudo systemctl start rememate-bark.service
sudo systemctl status rememate-bark.service --no-pager
journalctl -u rememate-bark.service -n 50 --no-pager
```

正常输出包含类似：

```text
bark reminders: users=1 sent=1 duplicates=0 no_due=0 failed=0
```

确认数据库记录时，使用 dispatch 连接检查当天的 review key：

```bash
sudo -u ubuntu bash -lc '
  set -a
  . /srv/rememate/.env
  set +a
  psql "$DISPATCH_DATABASE_URL" -c \
    "SELECT user_id, idempotency_key, push_type, created_at
       FROM push_log
      WHERE push_type = ''review_reminder''
      ORDER BY created_at DESC
      LIMIT 20"
'
```

同一用户、同一单词、同一用户本地日期再次触发时，统计中的 `duplicates` 会增加，Bark 不会再次发送。

## 停用或重新启用

停用定时推送但保留 unit 文件：

```bash
sudo systemctl disable --now rememate-bark.timer
```

如需停止当前已经手动启动的 oneshot：

```bash
sudo systemctl stop rememate-bark.service
```

重新启用：

```bash
sudo systemctl enable --now rememate-bark.timer
```
