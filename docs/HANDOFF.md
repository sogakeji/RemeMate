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
## 2026-06-30 ui-rescope 实测踩到的两个坑

**#11 — Python datetime.utcnow() 与 DB now() 时钟不一致 → 重置到期词后首页仍显示「无到期词」**
- **症状**：用 BYPASSRLS 把测试账号 8 个词 due_date 重置为 DB now()-1min（DB 表盘 06-30 07:06），真机首页仍显示「没有到期词·今日复习完成」。直接查 DB：due<=now() 全成立；RLS 视角 uid=34 也能看到 8 个。唯独 get_due_words 经 service 比较时判空。
- **根因**：words.due_date 是无时区 timestamp 列，存 DB server 本地表盘值。service get_due_words 用 `Word.due_date <= datetime.utcnow()` 比较——后者是 Python 进程 UTC 表盘。本机 WSL 里 Python utcnow() 与 DB server 时钟差了整整 8 小时（Py=06-29 23:11，DB now wall=06-30 07:11+08）。用 DB now() 写 due_date 落 06-30 07:06，对 Python utcnow() 是未来时刻 → 全判未到期 → 首页空。
- **解法**：重置/造测试到期词时，due_date 必须用 **Python datetime.utcnow()** 表盘值（service 比较端用的就是它），不要用 DB now()。即传 Python utcnow-1min 给列。生产不影响（生产写 due_date 也走 Python utcnow()，自洽）。本质：naive datetime 跨 Python/DB 时钟对比，两端时钟须一致；不一致时写入端和比较端必须同一时钟。
- **How to apply**：下次 安置/造到期词测试，先确认 dev WSL 的 Python utcnow() 与 DB server 时钟同步；不同步就统一用 Python 表盘写。

**#12 — lapse「全标忘记会瞬时清空队列」语义不明示（pending，不改算法）**
- **症状**：用户连续刷「忘记」，8 个到期词全 lapse 后首页显示「没有到期词」，产生「算法丢了词」错觉。
- **根因**：srs.py LAPSE_MIN_DELAY 硬编码 10 分钟冷却（防 M8 死循环感），lapse 词 due_date=now+10min。本轮其他到期词刷完后 lapse 词还在冷却 → 队列瞬时清空。算法本身符合 v0.1 §3.6「今天重排」+冷却意图，但 UI 空态没告诉用户「N 个词在冷却、N 分钟后回来」，只冷冰冰显示「无到期词」。
- **决定**（用户拍）：**保持 10 分钟算法不变，UI 明示**。空态文案补「刚复习过的词 N 分钟后回来」，避免错觉。**属 UI 文案，srs 不改。**
- **How to apply**：做词列表页/stats/首页空态时，补冷却提示；backlog 留作「明示 lapse 冷却」项。算法不动。---

## 2026-06-30 ui-rescope 分支交接（建给下一个 agent 接手）

> 本节由本轮主 agent 写，目的是让**换人**时下一个 agent 能快速接手 ui-rescope 分支。读这一节就够开工，不必逐 commit 回放。

### 0. 一句话状态

`ui-rescope` 分支（从 master 切）的 **step1~step4d-切片A + 语言闭环补全 + 修2 + 修1 已全部落地**，测试 **119 passed**。**修1 的工作区改动尚未 commit**（见「待提交」）。ui-rescope 的收尾只剩 **切片B**（删 router 兼容层 + 重评依赖测试 + intake 绑定）+ 几个 pending 文案项。

### 1. 本分支在做什么（战略口径，必读）

用户原话定调：**「用新的地基承接 demo 做不到的功能，丰富 demo 的功能，而不是丢弃 demo 的边界。」**

- demo（`D:\home\MemChunking\WordNest`，即 MemoBuddy）的**各页职责边界照搬**；RemeMate 独有的多用户 RLS / 多语言 / token 额度 / **隐式词表**落到 demo 边界适用的页里做实，**充实边界不替换边界**。
- **隐式词表口径（核心，踩坑 #10）**：词表对用户是**不可见的内部派生层**——用户只见「语言」，系统按 `(user_id, language_code)` 唯一派生一张 word_list，不存在则建。**只改 UX/路由/service，不动 `word_lists` schema**；不变量「每用户每语言零或一张」由 `words.get_or_create_language_list` 的 upsert 保证，**不靠 schema 唯一索引**。RLS policy 已是 `user_id = UID`，隐式继承不用改。**严禁再在 UI 上让用户建/命名/删词表**。
- UI 改造分两层（踩坑 #9）：**职责层先于视觉层**。`ui-port` 旧分支只套了 CSS 皮、没碰职责，被否。ui-rescope 先纠职责，视觉（搬 WordNest 设计系统到 `app/static/style.css` + `base.html`）同步进行。

### 2. 已完成并已提交的步骤（git log 可查）

```
804512e ui-rescope 修2: 首页语言切换器改 demo 下拉菜单形式，移到主题钮边
1f02d80 ui-rescope step4d 语言闭环补全（加词中心默认/stats/造句跟当前语言）
31fbcf8 ui-rescope step4d-切片A: 词列表页隐式化（UI 不暴露建表/删表/加词表单）
41d6866 ui-rescope step4c: 设置页语言选择 + 首页语言切换器 + 未设语言空态
3950f99 ui-rescope step4b: 当前语言状态 service + 按语言过滤
98ff5fb ui-rescope step4a: users.current_language 列 + 迁移
1113e24 ui-rescope step3: 加词中心（手工多词义 + AI 三端点 + 隐式建表闭环）
(state1/step2/step1 在更早 commit)
```

- **step1**：service 地基（隐式词表 + 多词义 + LLM 三封装）
- **step2**：首页主词卡 + grade 迁移（`/` 即复习页，砍 `/review` 作日常入口）
- **step3**：单一加词中心 `/words/add`（手工 JSON 多词义 + AI 一键填充/生成例句/生成笔记，对齐 demo；删零散文加词点）
- **step4a**：`users.current_language` 列 + 迁移 `a1b2c3d4e5f6`
- **step4b**：service 语言状态 + 按当前语言过滤（`get_current_language`/`get_current_language_list`/`get_words_for_current_language`；`get_stats`/`get_due_words`/`get_practice_words` 加 `language_code` 过滤）
- **step4c**：设置页语言选择 + 首页语言切换器 + 未设语言空态引导
- **step4d-切片A**：词列表页隐式化（UI 不暴露建表/删表/加词表单；详情页删内嵌表单改「加词→」导流；未设语言三态引导）。**router 兼容层保留**（POST `/words` 建表、POST `/words/<id>` 加词、POST `/words/<id>/delete` 删表仍能跑），目的是让依赖这些路由的旧测试本轮不挂——**切片B 再删**。
- **step4d 语言闭环补全**：加词中心语言下拉默认当前语言、stats/造句按当前语言过滤、stats CTA 指首页 `/`
- **修2**：首页语言切换器改 demo 下拉菜单形式（`.lang-switcher` 组件），位置移到主题钮边（右上 `.theme-slot`）

### 3. 本轮刚做完、待提交（修1 — 8 改 + 1 新迁移，工作区未暂存）

**修1 = 在学语言集合多选 + current_language 收敛**（用户原话场景闭合）：

> 用户原话：「在设置中我多选几种语言，比如英语 法语和日语。有一天我想只学一种语言了，我去设置中改为英语。那么应该看到修改按钮，允许我把多选改为单选英语然后保存。此时首页就是英语，没有其他语言。」

拆成两个概念：
- **设置页** = 「在学哪几种语言」**集合多选**（偏好清单），存 `users.learning_languages`（VARCHAR 逗号拼接，如 `"fr,en,ja"`，nullable 兼容老用户）。
- **首页切换器** = 「当前主攻」**单选**，存 `users.current_language`，**必须 ∈ 集合**（不变量由 service 收敛）。

落地文件（**未 commit**）：
- `migrations/versions/b2c3d4e5f6a7_add_learning_languages_to_users.py`（新）：`ALTER TABLE users ADD COLUMN IF NOT EXISTS learning_languages VARCHAR(200)`，`down_revision='a1b2c3d4e5f6'`。**已 apply 到 dev + test 两库**，两库 alembic head 都升到 `b2c3d4e5f6a7`（dev 库已确认）。
- `app/models/user.py`：加 `learning_languages = db.Column(db.String(200), nullable=True)`
- `app/services/words.py`：加 `_parse_learning`/`_serialize_learning`/`get_learning_languages`/`set_learning_languages`（收敛不变量：过滤非法 code + 去重保序 + 每个新进集合语言建隐式词表 + 集合变空→current 清空 / current 不在集合→收成集合首个）；重写 `set_current_language`（切语言即默认「在学」加进集合，保证首切不卡）
- `app/blueprints/main/routes.py`：`/settings` GET 传 `learning=get_learning_languages(uid)`；POST 用 `request.form.getlist("languages")` → `set_learning_languages`。**删了 `LanguageChoiceForm` import**（设置页不再用 WTForms 单选 form）
- `app/templates/main/settings.html`：改成多选 checkbox 表单（6 语言，集合内 checked），一个「保存」按钮
- `app/templates/base.html`：lang-menu **只渲染 `learning_languages` 集合内的语言**（不在集合的不出现）；集合空时显示「先在设置里选语言」
- `app/__init__.py`：新增 `inject_learning` context_processor 注入 `learning_languages`
- `app/static/style.css`：去重了三份重复的 lang-switcher CSS 块（之前编辑残留，长大三倍）→ 合一份 + 加 `.lang-empty`、`.lang-check`（设置页多选卡片）+ 暗色
- `tests/integration/test_settings_language.py`：改写为多选（`test_settings_save_sets_learning_languages`：保存 fr+en→集合 `"fr,en"` + 2 词表 + current=fr；`test_settings_narrow_to_single_retracts_current`：多选 fr/en/ja→改单选 en→集合剩 en、current 自动从 fr 收成 en）

**验证**：`pytest -q` → **119 passed**（修1 前 117，+2 新多选用例，旧单选用例改写）。gunicorn HUP 已重载，真机可验。

### 4. 下一个 agent 接手清单（按顺序）

**第 0 步：环境对齐**
```bash
cd /root/rememate
git checkout ui-rescope         # 确认在 ui-rescope 分支
git status -s                    # 应看到 §3 列的 8 改 + 1 新迁移未提交
.venv/bin/python -m pytest -q   # 应 119 passed，绿了再动手
# 确认 dev 库迁移 head（应 = b2c3d4e5f6a7）：
.venv/bin/python -c "from sqlalchemy import create_engine,text; import os; from dotenv import load_dotenv; load_dotenv(); print(create_engine(os.environ['MIGRATE_DATABASE_URL']).connect().execute(text('SELECT version_num FROM alembic_version')).scalar())"
```

**第 1 步（建议先做）：把修1 commit 掉**
工作区那 9 个文件就是修1，已验证 119 passed。建议：
```bash
git add -A && git commit -m "ui-rescope 修1: 在学语言集合多选 + current_language 收敛不变量"
```
（用户要求换人前先记 handoff，没明说是否提交；commit 与否问用户，但**别丢这批改动**——test 库迁移已 apply 到 b2c3d4e5f6a7，工作区和库是配套的。）

**第 2 步：推切片B（ui-rescope 收尾，主剩余工作）**
- **删 router 兼容层**：`app/blueprints/words/routes.py` 里的 POST `/words` 建表、POST `/words/<id>` 加词、POST `/words/<id>/delete` 删表，切片A 保留是为旧测试不挂，切片B 删。
- **重评依赖测试**：删路由后，依赖 POST `/words` 建表/加词的测试改走加词中心 JSON（`POST /words/add` with `{"language_code","word","definitions":[...]}`，见 `test_language_closure.py::test_stats_filtered_by_current_language` 已是这个写法可参考）。
- **intake 绑定**：intake service 里 `prepare_csv`/`prepare_extract`/`quick_add`/`_check_word_list` 及三模板（import/extract/quick_add）的下拉，从 `word_list_id` 改绑 `language_code`（走 `get_or_create_language_list` 自动建表）。

**第 3 步：pending 文案项（踩坑 #12）**
做词列表页 / stats / 首页空态时，补「刚复习过的词 N 分钟后回来」明示 lapse 10 分钟冷却，消除「全标忘记→队列瞬时清空=丢了词」错觉。**算法 srs.py 不改，只改文案。**

**第 4 步：真机回归 + 合 master**
ui-rescope 全部收尾后，真机走一遍六页（首页/词库/加词/造句/统计/设置 + login），确认语言闭环、隐式词表、暗色、响应式都正常，再合 master。

### 5. 本轮新踩的坑（除已在 #11/#12 外，本节无新增）

修1 实现过程干净，没有新的大型踩坑。复述两条已记入的、与本轮强相关的坑，接手必读：

- **#11 时钟坑**：dev WSL 的 Python `datetime.utcnow()` 与 DB server 时钟差 8 小时（已知漂移）。造/重置到期词测试时，due_date 必须用 **Python utcnow()** 表盘写，**不要用 DB now()**——否则 service 用 Python utcnow() 比较，due_date 落 DB 表盘未来时刻 → 首页判空。生产不受影响（生产写也走 Python utcnow()，自洽）。
- **#12 lapse 冷却明示**：`srs.py LAPSE_MIN_DELAY=10min` 硬编码，全标忘记后队列瞬时清空是算法正确行为，UI 要明示「N 分钟后回来」。**算法不改。**
- **迁移在 test 库怎么跑**（踩坑 #2 沿用）：test 库 `rememate_test` 的 `rememate` 角色无 ALTER 权限，跑迁移要用 `MIGRATE_DATABASE_URL`（`rememate_owner` 角色）URL 改指 `rememate_test` 跑 `flask db upgrade` 或手工 `ALTER + UPDATE alembic_version`。conftest 暂不自动跑迁移（B2 pending）。

### 6. 关键文件速查

| 关注点 | 文件 |
|---|---|
| 隐式词表 + 语言状态 service | `app/services/words.py`（`get_or_create_language_list`/`get_learning_languages`/`set_learning_languages`/`set_current_language`/`get_current_language`/`get_stats` 按 lang 过滤） |
| User model | `app/models/user.py`（`current_language`/`learning_languages` 两列） |
| 迁移链 | head = `b2c3d4e5f6a7`，`down_revision` 链：…→ `a1b2c3d4e5f6`（current_language）→ `b2c3d4e5f6a7`（learning_languages） |
| 首页 + 设置 + 语言切换路由 | `app/blueprints/main/routes.py`（`index`/`switch_language`/`settings`/`save_settings`） |
| 全局模板注入 | `app/__init__.py` 的 `inject_lang`（current_language+lang_choices）+ `inject_learning`（learning_languages） |
| 加词中心 | `app/blueprints/words/routes.py` 的 `add_center` + `app/templates/words/add.html` |
| 设计系统 | `app/static/style.css`（搬自 WordNest，lang-switcher + lang-check 块在本文件末尾）+ `app/templates/base.html` |
| 闭合测试参考 | `tests/integration/test_language_closure.py`（4 例：加词默认当前语言/stats 按语言/造句按语言/stats CTA 指首页）、`test_settings_language.py`（多选 + 收敛） |
| 方案文档 | `docs/arch/ui-rescope-plan.md`（职责重定表/路由清单/触点/执行顺序） |

### 7. 保留分支（别误删）

- `master`（阶段五，695cc11）
- `backlog-cleanup`（七项 backlog，09eff51，**未合 master**）
- `ui-port`（被否的旧视觉分支，保留作参考）
- `ui-rescope`（**本分支，在本节就是它**）
- `worktree-vip-membership-quota`（codex 会员分级线，已评审决定丢弃但分支保留）
- 用户早前决定**全部保留**，别清。### 8. 接手前的环境速查（WSL / 项目路径 / 不要踩的坑前置汇总）

> 这一节把散落在各踩坑条里的环境信息集中一份，接手第一件事先读这里定位环境，再回 §4 接手清单。

**项目根**：WSL `Ubuntu`，路径 `/root/rememate`（Windows 端经 `\\wsl.localhost\Ubuntu\root\rememate\` 访问）。从 Windows shell 跑命令统一用 `wsl bash -lc 'cd /root/rememate && ...'`。

**Python**：系统 `python3` 无 `python`；项目虚拟环境在 `.venv/`，跑任何东西都用 **`.venv/bin/python`**（不是 `python` / `python3`）。例：
```bash
.venv/bin/python -m pytest -q                 # 跑测试
.venv/bin/python -m flask db current          # 查迁移当前
```

**DB（PostgreSQL，本地 5432）**——三个角色对应三套 URL，**别混用**：
| URL（`.env`） | 角色 | 用途 | 权限 |
|---|---|---|---|
| `DATABASE_URL` | `rememate`（app 角色） | 应用运行时连 | 受 RLS policy 约束 |
| `MIGRATE_DATABASE_URL` | `rememate_owner` | **跑迁移 / 改 schema** | 有 ALTER/CREATE |
| `DISPATCH_DATABASE_URL` | `rememate_dispatch` | 定时派发 | 受限 |
| `TEST_DATABASE_URL` | `rememate` 角色但指 `rememate_test` 库 | 测试连 | **无 ALTER/CREATE** |

- **主 dev 库**=`rememate`，**测试库**=`rememate_test`。两库当前 alembic head 都 = `b2c3d4e5f6a7`（修1 迁移已 apply 到两库）。
- **跑迁移只能用 `MIGRATE_DATABASE_URL`（owner 角色）**——`rememate` 角色无 ALTER 权限（踩坑 #2）。测试库跑迁移要把 `MIGRATE_DATABASE_URL` 的库名改指 `rememate_test` 再跑，或手工 `ALTER + UPDATE alembic_version`。conftest 暂不自动跑迁移（B2 pending）。

**gunicorn（dev server）**：bind `127.0.0.1:8891`，2 worker，`-k gevent`，`preload_app=False`，**无 `--reload`**。
```bash
pgrep -af gunicorn                      # 看在不在跑（master pid 常为 1614）
kill -HUP <master_pid>                  # 改代码后手动重载 worker
```
改完代码**必须 HUP 重载**，否则真机看不到改动（worker 没自动 reload）。

**真机测试账号**：`test@local.dev` / `_mxE8RVt9Rwk6BbI`（之前手建，不在 `.env` / 脚本里）。`provision_user` + `login` 见 `tests/helpers.py`，测试里用 `PW="pw12345678"` 建临时账号。

**前置不要踩的坑（接手必读，详情见对应踩坑条）**：
- **#11 时钟坑**：dev WSL 的 `datetime.utcnow()`（Python 进程）与 DB server `now()` 时钟差约 8 小时（已知漂移）。造/重置到期词测试时，`due_date` **必须用 Python `utcnow()` 表盘写，不要用 DB `now()`**——否则 service 用 Python utcnow() 比较，due_date 落 DB 表盘未来时刻 → 首页判空。生产不受影响（生产写也走 Python utcnow()，自洽）。
- **#6 引号炸**：在 Windows git-bash 经 `wsl.exe` 跑复杂 bash（`$()` / 反引号 / 引号多层嵌套）会 syntax error。写多步命令优先用单引号包裹 `wsl bash -lc '...'`；实在复杂就写成 `.py` 脚本在 WSL 里跑，或 Write 到 `C:\Users\suqing\AppData\Local\Temp\` 再 `wsl cp /mnt/c/...`。**别堆 heredoc + 反引号**。
- **#2 测试库无 ALTER**：`rememate` 角色对 `rememate_test` 也无 ALTER，跑迁移用 `MIGRATE_DATABASE_URL`（owner 角色）。
- **#1 / #3 迁移链污染**：alembic `alembic_version` 表是**库级全局状态**，不随分支隔离。跨分支实验迁移要么用独立测试库，要么跑完 `flask db stamp <主线head>` 拉回。别用 dev 库的 `MIGRATE_DATABASE_URL` 在 worktree 里跑非主线迁移。
- **#10 隐式词表口径**：词表对用户**不可见**，**严禁再在 UI 上让用户建/命名/删词表**。不变量「每用户每语言零或一张」由 `words.get_or_create_language_list` upsert 保证，不靠 schema 唯一索引。只改 UX/路由/service，不动 `word_lists` schema。
- **#9 职责层先于视觉层**：UI 改动先问「这页职责对不对」再问「美不美」，别只套 CSS 皮（`ui-port` 旧分支就是只套皮被否）。
- **#12 lapse 冷却**：`srs.py LAPSE_MIN_DELAY=10min` 硬编码，全标忘记后队列瞬时清空是正确行为，UI 要明示「N 分钟后回来」——**算法不改，只改文案**。

---

## 2026-07-03 闭测部署前交接（sentence-square-mvp）

### 当前状态一句话

当前分支：`sentence-square-mvp`。准备部署到服务器做邀请制闭测，不是正式公开上线。核心路径已进入可测状态：多用户隔离、语言设置、词库/复习、造句/三行日记、句子广场、管理员创建账号、Bark 配置与测试推送、用户自助改昵称/密码。

### 最近关键提交

- `2ef48e1 Add self-service account settings`
  - 设置页新增“昵称”和“登录密码”自助修改。
  - 密码修改要求当前密码正确，新密码 8-128 位，两次一致。
- `46ca424 Add timezone preference setting`
  - 设置页新增时区选择，含 `Europe/Paris`，保存到 `users.timezone`。
  - 切换时区时重算 `user_quota.quota_reset_at`，闭测法国用户不会按中国本地日重置额度。
- `6741925 Add Bark test push flow`
  - 设置页 Bark 面板支持保存后发送测试推送。
  - 发送前二次校验 URL，只允许 https 公网地址，禁重定向，5 秒超时。
- `bd3f81b Add Bark notification settings`
  - 设置页新增 Bark 地址和通知开关保存。
- `239dd8c Fallback language switch to referrer` / `f90a401 Keep language switch on current page`
  - 全局语言切换器保持在当前页面，不再切语言后跳回首页。

### 已试过但已回退的方向

- `1cbb2db Prototype language mailbox experience`
- `e62cd07 Prototype mailbox card visual treatment`
- 已用 `573c063` / `aa35877` revert。

结论：Slowly/语言信箱方向概念有吸引力，但当前阶段只改文案吸引力有限，改 UI 又体感偏大。闭测前不继续做大 UI 隐喻探索，先保稳定。

### 开发库账号清理

2026-07-03 已按用户要求清理本地 dev 库中管理员以外的账号及其关联数据。清理后仅保留：

- `test@local.dev`（admin）
- `admin@local.dev`（admin）

已删除的非管理员账号包括：`friend@local.dev`、`square-real-*@example.test`、`sogakeji@gmail.com`、`highlight-check@t.com`、`diag@t.com`、`visual-mailbox@local.dev`。

清理方式：使用 `DISPATCH_DATABASE_URL` 事务删除非管理员用户相关的 `push_log`、`token_usage_log`、`sentence_upvotes`、`messages`、`conversations`、`word_candidates`、`source_segments`、`intake_sources`、`output_entries`、`review_logs`、`definitions`、`words`、`word_lists`、`user_quota`、`user_settings`、`users`。第一次脚本因 `conversations` 实际列名是 `user_id`、`messages` 实际列名是 `conv_id` 失败并回滚；修正后成功。临时脚本已删除。

### 闭测前已验证

- 最新全量测试：`190 passed`
- 设置页专项：`17 passed`
- 服务托管：`tmux rememate`，gunicorn 监听 `127.0.0.1:8891`
- 当前本地服务健康检查：`/healthz` 返回 `status: ok`

### 部署前建议执行

在服务器上按这个顺序走：

```bash
cd /root/rememate
git status -s
.venv/bin/python -m pytest -q
.venv/bin/python -m flask db current
.venv/bin/python -m flask doctor --strict
```

生产/闭测环境至少确认：

- `SECRET_KEY` 已设强随机值，不用 dev 默认。
- `DATA_ENCRYPTION_KEY` 是有效 Fernet key。
- `DATABASE_URL` / `MIGRATE_DATABASE_URL` / `DISPATCH_DATABASE_URL` 指向服务器库和对应角色。
- `DEEPSEEK_API_KEY` 或兼容 OpenAI provider key 已配置，否则 AI 批改/抽词会降级不可用。
- 服务器上管理员账号存在；普通朋友账号用管理员页面创建，不预设学习语言和母语，让用户首次登录自行设置。
- Bark 自建/官方地址必须是 https 公网地址；内网、本机、`127.0.0.1` 会被拒绝。

### 近期不建议再做的大改

- 不继续做语言信箱/Slowly 大 UI 隐喻。
- 不在闭测前重做导航和信息架构。
- 不在闭测前引入新的后台调度系统，除非只做手动可验证的小闭环。

### 闭测后优先看什么

- 法国用户是否能顺利设置“中文”为学习语言、母语为法语、时区为法国时间。
- 造句/三行日记是否比抽词导入更能驱动真实使用。
- 句子广场在小用户量下是否因为“只看同语言”而冷清；目前已有“看全部语言”路径，但历史句子里的用户自写词不建议加回词库。
- Bark 测试推送是否能被用户配通；下一步可做“导入完成通知”或“到期复习提醒”，但要继续保持发送前 SSRF 二次校验。

### 仍需记住的坑

- WSL/PowerShell 中复杂命令的 `$()`、管道和引号经常被 PowerShell 抢先解析。复杂操作优先写临时 Python 脚本在 WSL 内跑，跑完删除。
- `8891` 上偶尔会残留游离 gunicorn 旧进程，导致新代码未生效或设置页 500。处理方式：先 `ps -ef | grep gunicorn` 查 PID，精确 kill 旧 master/workers，再用 `tmux new-session -d -s rememate '.venv/bin/gunicorn -c gunicorn.conf.py wsgi:app'` 重托管。
- `datetime.utcnow()` / DB `now()` 时钟坑仍需避免。造测试到期词时用应用侧 UTC 表盘，不要混用 DB 本地时钟。
