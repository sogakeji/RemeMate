# RemeMate Bark 定时复习提醒

这两个 systemd 单元负责每 2 小时运行一次 RemeMate 的 Bark 复习提醒：

- `rememate-bark.timer`：在偶数小时整点 `00:00`、`02:00`、…、`22:00` 触发，主机离线时由 `Persistent=true` 补跑。
- `rememate-bark.service`：以 `ubuntu` 用户运行 `/srv/rememate` 下的 `.venv`，并通过 runner 自带的 flock 防止重叠执行。

推送筛选、dry-run、Bark URL 校验、按用户隔离和幂等均由 `dispatch.runner` 与现有 `send_review_reminders` 负责。幂等记录写入已有的 `push_log`，不创建 `.dispatch_state.json` 或其他状态文件。

## 前置条件

确认生产代码和虚拟环境位于：

```text
/srv/rememate
/srv/rememate/.venv/bin/python
/srv/rememate/.env
```

`/srv/rememate/.env` 至少要提供 dispatch runner 所需的 `DISPATCH_DATABASE_URL`；如果要在 Bark 中生成点击复习链接，还要配置 `SECRET_KEY` 和 `PUBLIC_BASE_URL`。数据库连接应使用 `rememate_dispatch` BYPASSRLS 角色。

## 更新代码并安装或更新单元

先按负责人批准的方式把目标版本更新到 `/srv/rememate`。如果该目录使用 Git 部署，可执行：

```bash
cd /srv/rememate
git pull --ff-only
```

确认代码更新完成后，安装版本化的 unit 文件：

```bash
cd /srv/rememate
sudo install -m 0644 deploy/systemd/rememate-bark.timer /etc/systemd/system/rememate-bark.timer
sudo install -m 0644 deploy/systemd/rememate-bark.service /etc/systemd/system/rememate-bark.service
sudo systemd-analyze verify /etc/systemd/system/rememate-bark.timer /etc/systemd/system/rememate-bark.service
sudo systemctl daemon-reload
sudo systemctl enable --now rememate-bark.timer
```

安装后只启用 timer；它会按时启动 oneshot service。不要再同时启用另一套 Bark 定时器，否则会产生不必要的并发尝试；已有 `push_log` 幂等会防止同一用户、单词和本地日期重复写入。

## 验证环境变量注入

先确认 `ubuntu` 用户可以成功读取 `.env`，再让 systemd 重新加载 unit。不要把下面的变量值或 `systemctl show` 输出粘贴到公开日志：

```bash
sudo -u ubuntu bash -lc '
  set -a
  . /srv/rememate/.env
  set +a
  test -n "$DISPATCH_DATABASE_URL"
  test -n "$SECRET_KEY"
  test -n "$PUBLIC_BASE_URL"
'
sudo systemctl daemon-reload
sudo systemctl show rememate-bark.service -p Environment --no-pager
```

`.env` 能被 bash source 成功，只说明文件内容可读；上面的 `systemctl show` 用于确认 service 的 `EnvironmentFile=/srv/rememate/.env` 已生效，timer 启动的 service 才能读到这三个变量。

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
  .venv/bin/python -u -m dispatch.runner bark --dry-run --flock-lock /run/rememate/bark.lock
'
```

CLI 手动执行和 timer 不要并发运行；两者都使用 `/run/rememate/bark.lock`。抢不到锁时 runner 输出 `already running` 并以 0 退出。

需要验证真实执行时，手动启动一次 service，然后查看统计和日志：

```bash
sudo systemctl start rememate-bark.service
sudo systemctl status rememate-bark.service --no-pager
journalctl -u rememate-bark.service -n 50 --no-pager
```

第一次 live 执行前，如果确认当前 `push_log` 为 0 行，请注意它会向所有符合条件且有到期词的活跃用户真实推送（默认每用户最多 1 个词），然后为每个成功推送写入幂等记录。正常输出包含类似：

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
       WHERE push_type = \$\$review_reminder\$\$
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
