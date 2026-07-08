# RemeMate HANDOFF

> 轻量交接页。历史过程已移到 `docs/PROGRESS.md`，完整旧文档见
> `docs/archive/HANDOFF.full-2026-07-08.md`。软 bug / 延后事项统一进
> `docs/BACKLOG.md`。

## 当前状态

- 日期：2026-07-08
- 当前分支：`master`
- 部署基线：54d8afc（当前 HEAD 以 git log -1 --oneline 为准）
- 工作区要求：开始新分支前必须 `git status --short --branch` 确认干净
- 本地测试基线：`pytest -q` -> 341 passed, 16 warnings
- 线上部署：`ubuntu@43.156.210.229:/srv/rememate`
- 线上服务：`rememate.service`，gunicorn 监听 `127.0.0.1:8891`
- 线上数据库迁移：`2e79a6ececcc (head)`
- 线上词典：`/srv/rememate-data/dictionaries`，`zh/en/ja/fr` present

## 闭测规则

- 闭测期间只立即修硬 bug：崩溃、数据丢失、权限/隔离、安全、无法完成核心流程。
- 软 bug、体验瑕疵、文案、排序、布局微调，先写入 `docs/BACKLOG.md`，集中分批处理。
- 新功能不要“来一个小需求做一个小需求”。先收集、归类、划切片，再开分支。
- 避免每个微需求都扩全量测试。测试策略按风险分层：
  - 文档/纯 CSS：不跑全量，说明未跑。
  - 单页面轻逻辑：跑相关 integration。
  - 服务层/权限/数据库/迁移/AI 降级：跑相关测试 + `pytest -q`。
  - 部署前基线：必须 `pytest -q` + `flask doctor --strict`。

## 下一阶段方向

1. Bark 能力补全：设置页已有入口，下一步做可用性闭环（保存、测试推送、失败提示、调用点）。
2. SessionPad：先写产品切片和数据边界，不直接动手大改。
3. 闭测观察：只修硬 bug，软反馈进入 BACKLOG。

## 架构速记

- Flask + Jinja2 + HTMX；无前端框架。
- 三角色数据库隔离：
  - `rememate`：app 角色，FORCE RLS。
  - `rememate_dispatch`：后台写入，BYPASSRLS。
  - `rememate_owner`：DDL / migration。
- RLS 依赖 `app.current_user_id` GUC，`before_request` 设置。
- 服务层在 `app/services/*.py`，不要依赖请求上下文。
- 阅读收词归入词库：生词本、手动加词、文本抽词、阅读收词、CSV 导入。
- 生产词典外置：`DICTIONARY_DATA_DIR=/srv/rememate-data/dictionaries`。

## 本机与线上命令

```bash
cd /root/rememate

# 本地测试
.venv/bin/python -m pytest -q
.venv/bin/flask doctor --strict

# 本地 gunicorn
fuser -k 8891/tcp 2>/dev/null || true
.venv/bin/gunicorn -w 2 -b 0.0.0.0:8891 wsgi:app \
  --access-logfile /tmp/gunicorn-access.log \
  --error-logfile /tmp/gunicorn-error.log \
  --pid /tmp/gunicorn.pid --daemon

# 线上健康检查
ssh -i E:\\hermes.pem ubuntu@43.156.210.229 \
  'cd /srv/rememate && .venv/bin/flask doctor --strict'
```

## 部署注意

- 不覆盖 `.env`、`.venv`、数据库、`/srv/rememate-data`。
- 部署前先备份：
  - 代码：`/home/ubuntu/rememate-backups/rememate-code-*.tgz`
  - 数据库：用 `sudo -u postgres pg_dump -Fc rememate`，app/owner 角色会被 FORCE RLS 拦住。
- 当前公网入口曾确认：
  - 服务内部 `127.0.0.1:8891/login` OK。
  - nginx 内部 `Host: demo.rememate.com` OK。
  - 外部 80/443 若连不上，优先查腾讯云安全组 / DNS，而不是 Flask。

## 踩坑索引

详细原文见 `docs/archive/HANDOFF.full-2026-07-08.md`。

1. migration 跨分支污染 `alembic_version`：实验迁移必须用独立测试库。
2. 测试库 `rememate` 角色无 CREATE 权限：自动迁移需 owner 角色 `TEST_MIGRATE_DATABASE_URL`。
3. migration 要可重入：失败重试、手工 schema、跨分支 stamp 都会触发。
4. `datetime.utcnow()` 是 naive：时区计算前必须标 UTC 或用 aware UTC。
5. 时区测试别用带 DST 的城市名；固定偏移用 `Etc/GMT+9` 这类。
6. Windows/WSL 复杂 shell 引号容易炸；复杂操作写脚本，少堆一行命令。
7. Windows 文件系统可能让 SQL 文件只变 mode 位；看 `git diff` 再处理。
8. 查询计数测试访问 `db.engine` 要 `app.app_context()`。
9. UI 改造先纠职责，再调视觉；不要只换皮。
10. 词表是隐式内部概念，用户只管理语言。
11. 造/重置到期词时要用和 service 一致的 Python UTC 表盘。
12. lapse 10 分钟冷却是算法设计，UI 需要说明，不要改算法。
13. 语言切换器应保持当前页面语境，不要跳首页。
14. 设置页语言/母语选择要收起展示，避免常驻多选框扰乱页面。
15. 管理员创建账号不需要预设学习语言/母语。
16. 临时 API key 不要写入文档或提交。
17. CSS 改动易受浏览器缓存影响；必要时硬刷新或版本化静态资源。
18. WSL 服务要监听 `0.0.0.0`，真机访问用 WSL IP。
19. 真机看到和 Playwright 不一致时，先查缓存/端口/旧进程。
20. CSV 导入 AI 不可用要降级为原始列值，不要让 SSE 崩。
21. CJK 阅读文本不能全局去空格，只对 `zh/ja` 合并字间空白。
22. 中日拖选优先于单击分词，避免 3/4 字词被拆成 2 字。
23. 阅读不是专业阅读器路线，定位是“阅读收词”。
24. 生产词典数据不要进 git，放 `DICTIONARY_DATA_DIR`。
25. 候选词 ignored 只代表本批次；全局“永不建议”要另建表。
26. 每日任务卡 v2 暂停，别在当前闭测阶段继续扩大。
27. 含 CJK 字面量的 Python 文件别用 Edit 多行替换，可能出现 Unicode 弯引号。
28. `git checkout` 单文件前先 `git diff`，防止丢未提交变更。
29. 不要并行跑 integration 测试；测试库清理/事务会互相卡。
30. CJK PDF 视觉换行会污染选词；修复必须带语言守卫。
31. 8891 旧 gunicorn/pidfile 会让“重启了但没生效”；必要时 `fuser -k 8891/tcp`。

## Backlog 规则

- `docs/BACKLOG.md` 是唯一待办池。
- 已修复项不要继续留在 BACKLOG；用 git 历史和 `docs/PROGRESS.md` 查。
- 闭测软反馈先写 BACKLOG，不马上开工。
- 硬 bug 可以直接修，但修前仍要判断最小测试集。
