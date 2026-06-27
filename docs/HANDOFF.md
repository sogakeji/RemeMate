# RemeMate 交接记录

> 维护方式：每轮工作结束追加一节，标日期。踩坑单列「避免重复尝试」段，写清症状、根因、解法。
> 与 [BACKLOG.md](BACKLOG.md) 的分工：BACKLOG 记「还没做的事」，本文记「做过的事 + 踩过的坑」。

---

## 2026-06-28 本轮：backlog 七项收口 + codex 残留清理

### 本轮做了什么

七项 backlog 收口（commit `09eff51`，分支 `backlog-cleanup`，18 文件 +252/−65，测试 77 passed）：

- **E1 迁移可重入**：5 个迁移全幂等化。`1ca04f710530` 的 RLS policy 改「DROP IF EXISTS + CREATE」；`b27062024cc0` 的 FK 改查 `pg_constraint` 动态取名 + `IF EXISTS`；`0be5bc17`/`fe681cf5`/`f7429a9f28db` 的 `add_column` 改 `ADD COLUMN IF NOT EXISTS`。两轮 `downgrade base → upgrade head` 验证可重入。
- **B1 htmx 本地化**：`base.html` 从 `unpkg.com` 改用 `app/static/vendor/htmx.min.js`（2.0.3，50KB）。
- **D1+D2 stats 时区+文案**：新增 `timeutil.today_local_start_utc(tz, *, now_utc=None)`，`get_stats`「今日已复习」按用户本地午夜切；`due_count` 文案从「今日到期」改述「待复习」。+4 个跨时区单测。
- **D3 /words 详情 N+1**：`get_word_list(..., eager=True)` 用 `selectinload(words).selectinload(definitions)`，detail 路由 eager 取。+查询计数集成测试断言 definitions 只查一次。
- **D4 lapse 死循环**：`srs.grade` 的 lapse 分支 `due_date = now + LAPSE_MIN_DELAY(10min)`。

**B2（CI 自动跑迁移）跳过**——理由见踩坑 #2，BACKLOG 已记该约束。

**额外修复（必须做，否则主库迁移链断）**：清掉 codex 那条没合的 migration `903c177de1fc` 在主 dev 库 `rememate` 和测试库 `rememate_test` 里的残留——见踩坑 #1。

### 仓库与分支现状

- 主线两条：`master`（`695cc11`，阶段五完成）+ `backlog-cleanup`（`09eff51`，本轮七项，**未合并 master**）。
- 保留未动：`worktree-vip-membership-quota`（`68b6895`，codex 会员分级线，已评审决定丢弃但分支保留）、336 个 `worktree-agent-*` 垃圾分支、1 个 stash `codex-changes-2026-06-25-backup`。**用户决定全部保留**。
- `.claude/` 是会话状态，未入 git（也不该入）。

### 主线进度（master）

阶段一~五完成并过 review；阶段六（AI助教）~ 十未开工。详见 [p1-build-plan.md](arch/p1-build-plan.md)。下一步推进阶段六时可从 demo `D:\home\MemChunking\WordNest` 抄 `importers/cleaning.py`、`importers/extract.py` 的 prompt 模式（见下文「demo 复用」）。

---

## ⚠ 踩坑（避免下次重复尝试）

### #1 codex 没合的 migration 污染了主库的 alembic_version

**症状**：在主 dev 库跑任何 `flask db upgrade/current/heads` 都报 `Error: Can't locate revision identified by '903c177de1fc'`。alembic 链整个断了。

**根因**：codex 在某次 worktree 跑里执行了 `flask db upgrade`，把它的 migration `903c177de1fc_add_membership_tier` 的 revision stamp 写进了**主 dev 库 `rememate` 和测试库 `rememate_test`** 的 `alembic_version` 表。但这个 revision 文件只存在于 `worktree-vip-membership-quota` 分支，master 代码里没有 → alembic 看 version 表说「当前在 903c177de1fc」，结果在代码里找不到该 revision → 直接卡死。它还顺手在 `users` 表加了 `membership_tier` 列（但 CHECK 约束没建成，只加了列）。

**排查命令**（确认是不是这个病）：
```bash
# 查 alembic_version 表
python -c "from sqlalchemy import create_engine,text; from dotenv import load_dotenv; load_dotenv(); e=create_engine(__import__('os').environ['MIGRATE_DATABASE_URL']);
print(e.connect().execute(text('SELECT version_num FROM alembic_version')).scalar())"
# 若显示 903c177de1fc 而代码里没有该文件 → 就是这个病
```

**解法**（已执行）：连 owner 角色，`ALTER TABLE users DROP COLUMN IF EXISTS membership_tier` + `DELETE FROM alembic_version` + `INSERT INTO alembic_version VALUES ('f7429a9f28db')`（主线 head）。

**预防**：worktree 里跑 `flask db upgrade` 前，确认它连的是**测试库**（`TEST_*`），别用 `MIGRATE_DATABASE_URL`（指 dev 库）。codex 当初大概率是在 worktree 里直接用了 dev 库的 MIGRATE_DATABASE_URL 跑迁移，把脏 stamp 写进了 dev 库。

**教训**：alembic 的 `alembic_version` 表是**库级全局状态**，不是分支隔离的。一旦某分支的 migration 被 apply 进某库，删分支/换分支都不会清那个 stamp。跨分支实验迁移时，要么用独立测试库，要么跑完用 `stamp` 把 version 表拉回主线 head。

---

### #2 测试库 `rememate` 角色无 CREATE 权限 → conftest 跑不了迁移

**症状**：想给 conftest 加「session 开始自动 `alembic upgrade head` 建表」（B2 的实质），结果 `CREATE TABLE` 报 `permission denied for schema public`。

**根因**：`scripts/dev/init-test-db.sql` 里 `REVOKE CREATE ON SCHEMA public FROM PUBLIC` 且**没给 `rememate` 角色重新 GRANT CREATE**——`rememate` 角色只有 DML（default privileges grant SELECT/INSERT/UPDATE/DELETE）。但 `config.py` 的 `TestingConfig.MIGRATE_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")`，TEST_DATABASE_URL 的 user 是 `rememate`。所以测试 config 指望用 `rememate` 角色跑迁移，而该角色建不了表 → 自动迁移在测试库里**根本不可行**。

**现状**：conftest 只做 `_wipe`（DELETE 各表），**不建表**，假设 schema 已由人工 `flask db upgrade` 建好。这就是 BACKLOG B2 说的「测试库需手动 `flask db upgrade`」的真实成因。

**正确解法**（B2 将来要做时）：新增 `TEST_MIGRATE_DATABASE_URL` env（owner 角色 `rememate_owner` + `rememate_test` 库），`TestingConfig.MIGRATE_DATABASE_URL` 改读它；conftest 加 session fixture 用该 URL 跑 `alembic upgrade head`。不要给 `rememate` 角色加 CREATE（破坏三角色隔离原则）。

**别走的方向**：
- 不要给 `rememate` 角色 GRANT CREATE on public——那破坏了 v0.1 §2.3 的三角色隔离（app 角色本来就不该有 DDL 权）。
- 不要让 conftest 用 `MIGRATE_DATABASE_URL`（dev 库的 owner URL）跑测试库迁移——库不同，URL 里的库名要换，但角色得是 owner。
- 我临时验证迁移可重入时写过 `scripts/verify_migrations.py`，已删。验证脚本若重建要 monkeypatch `app.config["MIGRATE_DATABASE_URL"]` 为「owner 角色 + 测试库」URL（不是 env 变量覆盖——env.py 读的是 `current_app.config`，环境变量会被 config 覆盖，见踩坑 #6）。

---

### #3 迁移不可重入的真实触发场景

**症状**：`flask db upgrade head` 在「迁移被人工回滚后重试」或「schema 里已部分有这些对象（dev 库手动建过）」时报错：`constraint does not exist` / `policy already exists` / `column already exists`。

**根因**：alembic 正常工作时 `alembic_version` 表会挡住已 apply 的 revision 重跑——所以**正常 upgrade 不会触发不可重入**。只有以下场景中招：
- 迁移中途失败留下 schema 部分建成，版本表没推进，重试时已建对象还在。
- dev 库被手动建过同名对象（如 RLS policy、唯一索引）。
- 像 codex 那样跨分支把 stamp 搞乱，手动 `stamp` 重置后重跑某一段。

**解法**（E1 已做）：所有 DDL 加幂等子句——`DROP CONSTRAINT IF EXISTS` / `DROP POLICY IF EXISTS` 再 `CREATE` / `ADD COLUMN IF NOT EXISTS` / `CREATE UNIQUE INDEX IF NOT EXISTS`。FK 约束名别写死（autogenerate 默认名可能带数字后缀或不同），查 `pg_constraint` 动态取该 (table, column) 的实际外键名再 DROP/ADD。

**PG 语法注意**：
- `CREATE POLICY` **没有 `IF NOT EXISTS`**，只能「DROP IF EXISTS + CREATE」两步。
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 是 PG 原生语法，alembic 的 `op.add_column` 不直接支持该子句，得用 `op.execute` 写原生 SQL。
- 查 `pg_constraint` 时 `conrelid` 是 OID 类型，参数化绑定字符串会报 `invalid input syntax for type oid`。要写 `cast(:table_id as regclass)` 显式转，而不是 `c.conrelid = :table_id`。
- `op.get_bind().execute(裸字符串)` 不行，必须包 `sa.text(...)`（op.execute 对裸字符串 OK 它内部包 text，但 bind.execute 不包）。

---

### #4 `datetime.utcnow()` naive 经 `.astimezone(tz)` 会被当本地时间不是 UTC

**症状**：`timeutil.today_local_start_utc` 算错本地午夜对应的 UTC。

**根因**：`datetime.utcnow()` 返回 **naive** datetime。Python 的 `naive.astimezone(tz)` 假定 naive 是**系统本地时区**（由 `TZ` / 系统 locale 决定），不是 UTC。WSL 系统 TZ 若是 Asia/Shanghai，`naive 05:00` 会被当成「Shanghai 05:00」→ 算成 UTC 前一天 21:00 → 本地午夜全错。

**解法**（timeutil.py 已做）：拿到 naive datetime 后显式标 UTC 再 `astimezone`：
```python
now_utc = now_utc.replace(tzinfo=timezone.utc) if now_utc.tzinfo is None else now_utc
now_local = now_utc.astimezone(tz)
```

**教训**：项目里大量 `datetime.utcnow()`（既有代码的 DeprecationWarning 一大堆）。做时区相关计算时，naive UTC 必须 `.replace(tzinfo=timezone.utc)` 或直接用 `datetime.now(timezone.utc)`。整个项目将来从 naive UTC 迁到 aware UTC 是待还的技术债（本轮没碰，避免扩大改动面）。

---

### #5 时区单元测试别用带 DST 的时区名

**症状**：用 `America/Anchorage`（标准 UTC-9）写断言，CI 在夏天跑就 fail——夏令时 Anchorage 变成 UTC-8。

**解法**：固定偏移测试用 `Etc/GMT+9`（POSIX 固定 UTC-9，无 DST）。注意 POSIX 命名反符号：`Etc/GMT+9` = UTC-9，`Etc/GMT-9` = UTC+9。带 DST 的 IANA 区名（Asia/Shanghai 无 DST 可用，Asia/Shanghai 一贯 UTC+8 无 DST，安全；America/* 大多有 DST，慎用）。

---

### #6 在 Windows git-bash 里经 `wsl.exe` 跑复杂 bash，引号嵌套会炸

**症状**：想一条命令设环境变量再跑 flask CLI，`wsl.exe -d Ubuntu -u root -- bash -lc "cd ... && VAR=$(python ...) flask ..."` 里的 `$()` 和 `\` 转义层层嵌套直接 syntax error。

**解法**：
- 简单命令用 `wsl.exe -d Ubuntu -u root -- bash -lc '...'` 单引号包裹。
- 复杂的（多步、env 覆盖、引号）写成 `.py` 脚本在 WSL 里跑，而不是堆 shell 串。本轮验证迁移可重入就是这么做的（已删的 `scripts/verify_migrations.py`）。
- alembic 的 `env.py` 读 `current_app.config["MIGRATE_DATABASE_URL"]`，**不读环境变量**——所以想让迁移连测试库，得在 Python 里 `app.config["MIGRATE_DATABASE_URL"] = ...`，靠 `MIGRATE_DATABASE_URL=xxx flask db ...` 这种 env 覆盖无效（被 config 覆盖）。

---

### #7 `scripts/dev/init-db.sql` 在 Windows 下反复显示「modified」但 0 改动

**症状**：`git status` 老显示 `scripts/dev/init-db.sql` modified，`git diff` 却 0 行。

**根因**：该文件原是 `100755`（带执行位），跨到 Windows 文件系统后执行位语义丢失，git 反复记录 mode 位变化 `100755 → 100644`，但内容无改动。

**解法**：`git checkout scripts/dev/init-db.sql` 还原 mode 位（暂时的——下次某些操作可能又翻回）。彻底解：`git config core.fileMode false`（本仓库级），让 git 忽略 mode 位差异。本轮没设，每次需要干净 status 前 `git checkout` 一下即可。

---

### #8 N+1 查询计数测试要 `with app.app_context()` 才能 `db.engine`

**症状**：在测试里 `event.listens_for(db.engine, "before_cursor_execute")` 报 `RuntimeError: Working outside of application context`。

**解法**：`db.engine` 访问需要 app context。listener 注册/移除包在 `with app.app_context():` 里，`client.get(...)` 在其外（client 自己推请求 context）即可——event listener 是进程级注册的，不依赖 context 存活。见 `tests/integration/test_words_n_plus_1.py`。

---

## demo 复用（`D:\home\MemChunking\WordNest`）

WordNest 即 docs 里反复提到的 MemoBuddy 实体（v0.1 §「与 MemoBuddy 的关系」）。复用规则：**抄逻辑改命名，不 cherry-pick commit、代码内不出现 memobuddy/wordnest 标识**（v0.1 §2.1 决策）。

直接可抄（阶段六/九推进时）：
- `importers/cleaning.py`、`importers/extract.py`（**截断 JSON 抢救** pattern 值钱）→ 阶段六 AI 抽词/归一化 prompt 对齐。
- `services/llm_service.py` 的 `correct_sentence`（`used_word` 词形/词根容错）→ 阶段四已有自己版，可对齐。
- `dispatch.py`（15min 心跳 + 数据驱动时间窗 + 幂等）→ 阶段九 dispatch 改造遍历用户。
- `push_bark.py` + `importers/bark.py`、`build_podcast.py` + `importers/tts.py`（edge-tts 内容寻址缓存）→ 阶段九。
- `services/demo.py` 的 `normalize_bark_url`（SSRF 防护）→ backlog A2（开放注册前必修）。
- `srs/scheduler.py`（纯函数 NamedTuple 版 SM-2，分离干净 + 多了 `exposure` grade）→ P2 FSRS 切换时对照重构 rememate `srs.py`。

显式否决：`graph_service.py`（HANDOFF 自标 dead-end）、`list_service.py`/`app.py` engine 切换（per-list SQLite，已被 Postgres+RLS 取代）、`migrate_srs.py`/`backup_db.py`（SQLite 专属）。

---

## 待办 / 下一步

- `backlog-cleanup` 合并 master（用户没决定时机）。
- 阶段六（AI助教）开工时抄 WordNest `cleaning.py`/`extract.py`。
- BACKLOG 剩余项（上线前必做的 token 硬约束+TOCTOU、Bitwarden 迁机评估，广场前 NSFW 半挂态，等）按对应阶段拾。
- B2 加 CI 时处理踩坑 #2 的 `TEST_MIGRATE_DATABASE_URL`。
- 整个项目的 naive `datetime.utcnow()` → aware UTC 迁移（技术债，踩坑 #4）。