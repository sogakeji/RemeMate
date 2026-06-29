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
- 整个项目的 naive `datetime.utcnow()` → aware UTC 迁移（技术债，踩坑 #4）。---

## 2026-06-29 UI 职责纠偏立项（ui-rescope）

### 触发
用户真机看 UI 后指出**四件事**：①首页应=当天主词卡而非仪表盘；②加词散三处、还缺 demo 的 AI 一键填充/生成例句；③点词表进的是加词表单不是词列表；④统计页不该有「去加词」CTA。
重新对照 demo + v0.1 文档 + 真实代码后**确认根因**：之前 `ui-port` 分支只套 CSS 类名（视觉层），**没碰页面职责错位**。RemeMate 现状偏离了 demo 的职责边界——加词散在 nav(指错到 intake quick-add) / detail 页(内嵌) / stats CTA(顺手塞) 三处；首页仪表盘 + 独立 `/review` 闪卡两套复习入口并存；stats 闯进加词导流。

### 战略（用户定调，原话）
「用新的地基承接 demo 做不到的功能，丰富 demo 的功能，而不是丢弃 demo 的边界。」
= demo 各页职责边界照搬；RemeMate 独有的多用户 RLS / 多语言 / token 额度 / 隐式词表落到 demo 边界适用的页里做实，**充实边界不替换边界**。

### 已拍板的三个决策
1. **首页 = 当天主词卡**（第一眼暴露词，第一性原理=来背词）。砍 `/review` 作日常入口，`/` 即复习页；仪表盘大字价值并入 stats。Bark 回流 `/review/<token>` 阶段九再说。
2. **单一加词中心**：手工全字段(JSON 多词义 + AI 一键填充/生成例句/生成笔记，对齐 demo `/ai_fill_word` `/generate_example` `/generate_note`) + CSV 导入 + 文本抽词合并于此；删掉所有零散文加词点。
3. **隐式词表**： diagnosed 后重新认识——词表对用户是不可见的内部派生层，"我在学法语"=那张 fr word_list。首页语言切换器、设置页选语言、导入按 `language_code` 自动分流自动建表。**口径=只改 UX/路由/服务，不动 `word_lists` schema**；不变量"每用户每语言零或一张"由 service `get_or_create_language_list` upsert 保证，不靠 schema 唯一索引。RLS policy 已是 `user_id = UID`，隐式继承不用改。

stats 回纯看板（删 CTA，补 demo 的易忘词 Top 表 + 学习热力图，热力图按 ReviewLog.ts 聚合本轮就补）；造句以后再整；AI 助教延后；设置/编辑词/加释义向 demo 对齐（设置本轮只做语言选择最小版闭环，编辑词+加释义先补骨架）。

### 产物
- 方案文档：`docs/arch/ui-rescope-plan.md`（载体：各页职责重定表、路由删除/新增清单、触点文件列表、执行顺序、验证）。
- 分支：待开 `ui-rescope`（从 master 切，独立于 `backlog-cleanup` / `ui-port`）。
- **本节只立项 + 写方案，尚未动代码。**

### 踩坑追加（避免下次重复）

**#9 — UI 改造的层次：视觉换皮 ≠ 职责纠偏**
- **症状**：`ui-port` 分支把 WordNest CSS 令牌+组件类名套到 RemeMate 模板，真机看"好看但分工乱"——加词散三处、首页/复习两套复习、stats 闯导流。用户判定"不符合在 demo 基础做多用户多语言的预想"。
- **根因**：UI 改造有两层——**视觉层**（CSS 类名/令牌/暗色/响应式）和**职责层**（每页干什么、不干什么）。`ui-port` 只做了视觉层，没碰职责层，而 RemeMate 的职责分工**本来就偏离了 demo 边界**（demo 页分工清晰：首页主词卡/单一加词页/词列表纯列表/stats 纯看板）。套好看的皮盖在乱分工上 = 皮绣花在错布上。
- **解法**：先做 `docs/arch/ui-rescope-plan.md` 的职责层（删散布加词点、首页合并复习、stats 去 CTA、隐式词表、加词中心聚拢），职责对了再套视觉。**顺序不可反**——先视觉后职责 = 返工。
- **How to apply**：下次 UI 工作先问"这页职责对不对"，再问"样式美不美"。demo 是单用户私站但有成熟的职责边界可抄，抄边界比抄皮重要。

**#10 — 隐式词表：用户层从未"看到"词表**
- **症状**：初版把"词表"当 demo 没有但 RemeMate 必须自补的显式管理对象（`words/list.html` 有建表表单+命名+删表按钮），结果用户被要求命名、手动建/删一个本不该操心的中间概念。
- **根因**：错认了词表的定位。demo 单语言只有一张平面词表、用户从不接触"词表"概念是因为它**隐式**—— Mondays学法语=系统自动建那张 fr 表。RemeMate 多语言只是把"隐式按语言派生"从单语言扩到多语言，**不是把隐式变成显式**。
- **解法**：词表退回隐式——UX/路由/服务层让用户只见"语言"，不建/命名/删词表；`word_lists` schema 不动，`name` 存内部语言名。设语言/切语言/导入自动建-切-分流。
- **How to apply**：review C1 把"建表当 day-1 阻塞点"那条设计**作废**——隐式化后阻塞自动消失（首次设语言/导入时自动建表）。别再让用户在 UI 上手动建表。