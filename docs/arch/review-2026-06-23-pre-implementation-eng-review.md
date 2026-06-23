# RemeMate 工程评审 — 动手前最后一道闸

> Review 日期：2026-06-23
> 审查对象：`docs/arch/` 6 篇 + `docs/design/` 5 篇全量
> 审查视角：plan-eng-review（架构 / 正确性 / 安全 / 测试 / 性能 / 失败模式）
> 前提沿用：注册用户短期 <100，长期 ≤5000，invite-only P1
> 关系：本文是 [review-2026-06-22-architecture-audit.md](review-2026-06-22-architecture-audit.md) 的后继。6-22 audit 的 A/B/C 类大部分已落地，本轮聚焦它漏掉的一类——**「按文档写出来就坏」的 day-1 正确性/安全 bug**。
> 已决策（2026-06-23）：P1 worker class 定为 `gunicorn -k gevent -w 2`（见 §五·5）。

---

## 修复状态（2026-06-23 回填）

本评审全部 finding 已在 `5c3862b` 落地、`ba51e95` 补最后一处，逐条经验证核对。✅=已落地并验证。

| Finding | 状态 | 落地位置 |
|---|---|---|
| A1 RLS 三层空转 | ✅ | data-isolation §RLS落地清单（5c3862b）+ output_entries 拆 policy（ba51e95）|
| A2 webhook/bark SSRF | ✅ | dispatch §SSRF防护：is_safe_push_url，保存 + 发送双校验 |
| A3 provisioning | ✅ | auth-flow create_user 三表一事务；quota _get_or_create + _maybe_reset 处理 None |
| A4 摘要 timer | ✅ | dispatch：每 15 min + 本地 08:00 窗口，覆盖半小时偏移时区 |
| A5 worker/熔断 | ✅ | v0.1：gevent -w 2 |
| B1 广场 P1/P2 | ✅ | 定 P1（sentence-square 头部）|
| B2 session-pad 编号 | ✅ | 编号约定说明 |
| B3 Alembic vs RLS | ✅ | v0.1 §2.2：手写 migration 例外 |
| C1 建词表入口 | ✅ | routes：POST /words |
| C2 commit 加载 source | ✅ | first_or_404 + user_id scope |
| C3 候选 context 字段 | ✅ | WordCandidate.context_start/end |
| C4 CSV SSE | ✅ | /intake/<id>/process SSE + nginx proxy_buffering off |
| C5 单请求上限 | ✅ | MAX_TOKENS_PER_REQUEST=20k |
| C6 三按钮→SM-2 | ✅ | v0.1 §3.6：映射 2/3/5 + 单测要求 |
| C7 点夯反刷 | ✅ | token-quota：三重反刷 |
| E 命名/琐碎 | ✅ | output_entries↔OutputEntry、音频路径统一、复习幂等键改当天日期等 |

> 验证残留（output_entries 写隔离）已由 `ba51e95` 闭环。前序 audit 见 [review-2026-06-22-architecture-audit.md](review-2026-06-22-architecture-audit.md)。

---

## 0. 总体判断

6-22 audit 把「用户多了会崩」的扩展性问题清干净了，但它聚焦规模/安全/一致性，**漏掉了一整类 day-1 就炸的正确性 bug**。最关键的发现：headline 的「三层防御」里第三层 RLS 按现在写法基本是空转的；新用户 provisioning 不完整，首次用 AI 直接崩；webhook 推送是 server-side SSRF，直通同机 Bitwarden。这三条会在前 10 个真实用户身上就暴露，而现有文档和测试完全没覆盖。

severity 分四档：
- **P1-必改**：按文档实现就坏的正确性/安全 bug
- **先定调**：范围/标签自相矛盾，不定就会实现成 bug
- **设计缺口**：功能描述了但落不了地
- **较小项**：命名漂移、交叉引用悬空等

每条带 `file:line` 和置信度（9-10 = 读代码验证的具体 bug；7-8 = 高置信模式匹配；5-6 = 中等，需复核）。

---

## A. P1 必改：按文档实现就会坏

### A1. 三层防御的第三层（RLS）按现在写法基本无效 ★★★ (置信 9)

`data-isolation-security.md` 的 RLS 兜底有 4 个独立的坑，任一个都让 layer-3 失效或反而把表锁死：

**A1a — ENABLE 了但没建 POLICY = 默认拒绝 = 表对所有人返回 0 行。**
`data-isolation-security.md:52-53` 对 `review_logs`、`output_entries` 执行了 `ENABLE ROW LEVEL SECURITY`，但 `:56` / `:60` 只给 `word_lists`、`words` 建了 `CREATE POLICY`。Postgres 里 RLS enabled + 无 policy = deny-all。结果：复习记录、造句日记表对**本人也返回零行**，`/stats`、`/write` 历史、SRS 调度全读空。上线第一天就坏，且是静默坏（无报错，只是没数据）。

**A1b — 没有 FORCE，而 app 角色是表 owner → RLS 对 owner 直接跳过。**
Alembic 迁移用 `rememate` 角色跑，表 owner 就是 `rememate`，app 也用 `rememate` 连库。Postgres 默认**不对表 owner 施加 RLS**。于是 layer-3 静默失效——测试时一切正常（layer-2 service 层还在挡），真出 bug 时兜底根本不存在。必须 `ALTER TABLE ... FORCE ROW LEVEL SECURITY`，或让迁移 owner 角色 ≠ app 连接角色。文档全程没提 FORCE 和表 ownership。

**A1c — 一大半用户数据表没有 RLS policy。**
`definitions`（无 user_id，只有 word_id）、`conversations` / `messages`（messages 只有 conv_id）、`intake_sources` / `source_segments` / `word_candidates` 都没写 policy。`input-pipeline.md:144` 一句「RLS policy 同其他表」但没有任何一条真写出来。`definitions` 和 `messages` 没有 user_id 列，必须用 JOIN 子查询 policy，不能照抄 `word_lists` 的写法。layer-3 实际只覆盖 12 张用户表里的 2 张。

**A1d — `SET LOCAL ... = :uid` 写法本身有问题。**
`data-isolation-security.md:74` 的 `text("SET LOCAL app.current_user_id = :uid")`——`SET` 语句在 psycopg2 协议层不接受绑定参数，这个 bind 很可能不生效或退化成字符串拼接（拼接 = 注入面）。正解是 `SELECT set_config('app.current_user_id', :uid, true)`，可参数化、事务级。配套：`:57` 的 `current_setting('app.current_user_id')::int` 在 GUC 未设置时会**抛异常**，应改两参形式 `current_setting('app.current_user_id', true)`（缺失返回 NULL → fail-closed 返回 0 行，而不是 500）。

**A1e（次要，置信 6）— 多 commit 丢 GUC。**
`SET LOCAL` 是事务级。一个请求里若多次 commit（intake commit、grade 提交都 commit），第一次 COMMIT 后 GUC 就没了，同请求后续查询在「无 user_id」状态下跑。需要明确「一请求一事务」或每次 commit 后重设。

**修法**：建一份「RLS 落地清单」放进手写 migration——FORCE、每张用户表的 policy SQL、`set_config` 注入方式、owner/连接角色分离。并补对应集成测试（见 §D）。注意现有 `data-isolation-security.md:122-138` 的测试用 service 层调用，**测不到 RLS 本层**（layer-2 先挡了），必须补一个直连 DB、用 app 角色、绕过 service 层验证 policy 真能拦的测试。

### A2. Webhook / Bark 推送是 server-side SSRF，直通同机 Bitwarden ★★★ (置信 9)

`dispatch-multiuser.md:39-40`：

```python
if settings.webhook_url:
    requests.post(settings.webhook_url, json={...}, timeout=5)
```

`webhook_url` 是用户在 /settings 里自填的，dispatch 后台直接对它发 POST。经典 SSRF：用户可设成 `http://127.0.0.1:8890/...`（同机 MemoBuddy）、`http://169.254.169.254/...`（云元数据）、或本机 Bitwarden 端口。而 `v0.1-direction-and-constraints.md:56-58` 明确写了 RemeMate 与 Bitwarden 同机、且这是已知安全顾虑。

关键：v0.1 的缓解措施是「开放注册前把 Bitwarden 迁走」，但 **SSRF 在 invite-only P1 就能打**——一个被邀请账号（或被盗的邀请账号）day-1 就能横向打同机服务。`bark_url`（`:38`）同理。

**修法（进 P1，不能等迁 Bitwarden）**：URL scheme 白名单（仅 https）、解析后拒绝私网/环回/链路本地 IP 段、禁止跟随重定向、超时已有（5s）。

### A3. 新建用户不完整 → 首次用 AI 直接崩，且额度永不重置 ★★ (置信 9)

`auth-flow.md:93-110` 的 `create_user` **只插 `User` 一行**，不建 `UserSettings`、不建 `UserQuota`。但：

- `token-quota.md:81` `quota = UserQuota.query.get(user_id)` → 新用户拿到 `None` → 下一行 `_maybe_reset(quota)` / `quota.daily_base_limit` 直接 `AttributeError`。**任何新用户第一次点 AI 功能 = 500。**
- 就算建了行：`token-quota.md:36` `quota_reset_at` 没有 default（`None`），而 `:106` `_maybe_reset` 是 `if quota.quota_reset_at and ...`——`None` 永远跳过重置。**用户当天烧满额度后 `tokens_used_today` 永不归零，永久锁死 AI。**
- `dispatch-multiuser.md:58` 自己写着「各开关默认值在 `flask create-user` 建账号时写入 `user_settings`」——它知道该写，但 auth-flow 的 create_user 没写。文档自相矛盾。

**修法**：create_user 在同一事务里建 User + UserSettings（含四个 notify 开关默认值）+ UserQuota（含 `daily_base_limit` 和初始化的 `quota_reset_at = 下一个本地午夜`）。

### A4. 每日摘要的定时调度自相矛盾，且对默认时区根本不触发 ★★ (置信 8)

三处口径打架：
- `dispatch-multiuser.md:68`（架构拆分表）：`rememate-summary.timer 每日 08:00 UTC`
- `dispatch-multiuser.md:98`：`"""每小时触发..."""`
- `v0.1-direction-and-constraints.md:232`：`每小时`

按 `:68` 的「每日 08:00 UTC」跑：默认时区是 `Asia/Shanghai`（`auth-flow.md:133`），08:00 UTC = 北京 16:00 ≠ 本地 08:00 → `is_summary_time` 永远 false → **默认时区用户（你绝大多数早期用户）永远收不到每日摘要**。

就算按「每小时」跑：`dispatch-multiuser.md:121` 的窗口是本地 `08:00–08:14`（15 min），而 timer 每小时只在整点附近开火。整数偏移时区（北京 +8）本地 08:00 = UTC 整点能命中；**半小时偏移时区（印度 +5:30、尼泊尔 +5:45）本地 08:00 落在 UTC 的 :30/:15，整点 timer 永进不了 15 min 窗口** → 这些用户永远收不到摘要。

**修法**：timer 改每 15 分钟（窗口逻辑就对了），或 timer 保持每小时但窗口放宽到整点那一小时；先删掉 `:68` 的「每日 08:00 UTC」错误表述。

### A5. （已决策为 gevent，本条降级为「执行项」）熔断器与 worker class

6-22 audit C1（★★★）建议 gevent；后续提交回退为 `v0.1:215-217` 的 `sync -w 4`，但熔断器设计仍写死单进程前提（`llm-provider-failover.md:53,112`「内存版，gevent 单进程下状态一致」），`-w 4` 下 4 个独立内存熔断器 = C1c 复活。

**2026-06-23 已定**：P1 改回 `gunicorn -k gevent -w 2`，内存熔断器状态一致、SSE 不占满 worker、P1 不引入 Redis、P2 上 Session Pad 无需重切 worker。**执行项**：
- `v0.1:215-217` 部署段把 `-w 4 sync` 改为 `-k gevent -w 2`；
- P1 早期验证 gevent monkey-patch 与 psycopg2 / requests / edge-tts 的兼容性；
- `llm-provider-failover.md` 把「内存熔断（多 worker 失效）」的措辞坐实为「gevent 单进程，内存版即可」。

---

## B. 必须先定调：范围/标签自相矛盾

### B1. 句子广场到底 P1 还是 P2？(置信 9)

- `routes-and-modules.md:2-3` 自称「P1 基线」，里面却完整包含 `square` 蓝图（`:37`）、`social.py / SentenceUpvote` 模型（`:21`）、`/write/<id>/publish 公开到句子广场`（`:130`）、`/square/upvote|report|learn`（`:152-154`）→ 当 P1 在做。
- `sentence-square.md:6` 头部写「**P2 社交功能**」。
- `v0.1-direction-and-constraints.md:139` §4 把「社交功能」笼统推到 P2，但没点名广场。

与当年 A2（Session Pad 归属）同病，audit 没抓到广场这条。**必须定**：广场 + 点夯 + 「一起记」进不进 P1。不定的话，routes 文档会把 P2 的东西当 P1 实现。

### B2. Session Pad 文档通篇还挂着 P1 标签（A2 只修了一半）(置信 9)

头部 `session-pad.md:6` 改成了「P2 功能」，但正文没跟着改：`:84` 场景优先级「**P1 主打**」、`:201`「## P1 实施顺序（P1a → P1b）」、`:220`「## P1 范围边界 / P1 做 / P1 不做」，而 `:249` 进化路径表又用「P2a 首发 / P2b / P3 / P4」。同一篇里 P1a/P1b 和 P2a/P2b 两套编号并存。**修法**：全文 P1→P2 重编号，或加一句「本文 P1x 编号一律读作 P2x」。

### B3. Alembic「不手写 ALTER TABLE」与 RLS 需要手写迁移冲突 (置信 8)

`v0.1-direction-and-constraints.md:39`「迁移用 Alembic，不手写 ALTER TABLE」。但 RLS 的 `ENABLE/FORCE ROW LEVEL SECURITY`、`CREATE POLICY`、两个数据库角色（`rememate` / `rememate_dispatch BYPASSRLS`）的创建和 GRANT，Alembic autogenerate **全抓不到**，必须手写迁移或建库脚本。文档要承认这个例外，并指定 RLS/角色放在哪个手写 migration 里。

---

## C. 设计缺口：功能描述了但落不了地

| # | 缺口 | 证据 | 置信 |
|---|---|---|---|
| C1 | **没有建词表的入口**。`IntakeSource.word_list_id` 是 `nullable=False`（`input-pipeline.md:108`），CSV/extract/quick-add 都要求先有 word_list；但 `routes-and-modules.md:122-126` 只有 `GET /words`、`GET /words/<id>`，没有 POST 建表。新用户零词表、无法建表 → 整个核心入库链 day-1 卡死。 | 上述行 | 8 |
| C2 | **`commit_intake_source` 用了未定义的 `source`**。签名 `input-pipeline.md:170` 只收 `source_id`，函数体却用 `source.word_list_id`（`:182`）、`source.status`（`:207`），从没 `source = IntakeSource.query.get(source_id)`。草图 bug，会原样变真 bug。 | 上述行 | 8 |
| C3 | **`/extract` 承诺的原文高亮没落点**。`input-pipeline.md:81` 让 DeepSeek 返回 `context_start/end` 字符偏移「用于高亮原文」，但 `WordCandidate` 模型（`:129-141`）没有 context 偏移字段。 | 上述行 | 8 |
| C4 | **CSV 全同步处理会超时**。`input-pipeline.md:60` CSV「同步、每批 20 条调 DeepSeek」。500 词 ≈ 25 批 ×（2-10s）= 几分钟卡在一个 HTTP 请求里。gevent 缓解了 worker 占用，但 nginx `proxy_read_timeout` 仍会掐断长请求；CSV 应像 `/extract` 一样走 SSE 或分块。 | 上述行 | 7 |
| C5 | **额度不限单次请求大小（TOCTOU）**。`token-quota.md:73-103` check 用 `estimated_tokens`、record 用实际值；一次超大 `/extract` 估低 → 过 check → 实际烧的钱事后才记。`check_and_reserve` 名为 reserve 实则不预占。需补单请求 token 上限。 | 上述行 | 7 |
| C6 | **三按钮 → SM-2 质量分映射未定义**。首页是「三按钮」（`v0.1:21`），SM-2 是 0-5 质量分。三按钮怎么映射到 `ease`/`interval` 更新，全套文档没写。SRS 是产品心脏，映射函数（含测试）应在 P1 文档定死。 | 上述行 | 8 |
| C7 | **点夯换额度可被刷，反刷机制是悬空引用**。`sentence-square.md:128` 说「反刷机制见 token-quota.md」，但 token-quota 里没有反刷，只有总 bonus 封顶 = base_limit（`:145`）。`UNIQUE(entry_id,user_id)` 只防同句重复夯，刷量 = 句子数 × 500。（P2，但交叉引用要么补内容要么删。） | 上述行 | 7 |

---

## D. 测试评审（plan 必须自带的测试）

文档现在唯一明确要求的测试是跨用户隔离（`data-isolation-security.md:122`），且如 A1b 所述它测不到 RLS 本层。按「100% 关键路径」补：

```
模块                          必须覆盖的路径 / 失败模式                         现状
─────────────────────────────────────────────────────────────────────────────
services/rls.py        ├─ [GAP★critical] app 角色下 policy 真能拦截(A1b)     无
                       ├─ [GAP★critical] review_logs/output_entries 本人能读  无(A1a 会全空)
                       ├─ [GAP] 一请求多 commit 后 GUC 仍在(A1e)              无
                       └─ [★ 已要求] 连续两请求不同用户                       已要求
services/quota.py      ├─ [GAP★] 新用户无 UserQuota 行 → check 行为(A3)       无
                       ├─ [GAP] quota_reset_at=None 的重置(A3)                无
                       ├─ [GAP] 跨午夜重置 + 时区(token-quota:123)            无
                       └─ [GAP] 单请求超额度上限(C5)                          无
dispatch/runner.py     ├─ [GAP★] is_summary_time 半小时偏移时区(A4)           无
                       ├─ [GAP] 幂等键 + 7天清理交互(见 §E)                   无
                       └─ [★ 部分] 单用户异常不中断遍历(已有 try/except)      部分
services/llm.py        ├─ [→EVAL] NSFW fail-closed(provider 全 down)          设计有,需 eval
                       ├─ [GAP] 25s 总 deadline 真的生效                      无
                       └─ [GAP] 流式首 token 后断流提示重试                   无
services/srs.py        └─ [GAP] 三按钮 → SM-2 质量分映射(C6)                  未定义
intake commit          ├─ [GAP] source 未加载(C2)                            无
                       └─ [GAP] 同词去重静默跳过                              无
dispatch send_notif    └─ [GAP★] webhook 私网/环回 URL 被拒(A2)              无
```

**最危险的「无测试 + 无错误处理 + 静默」组合**：A1a（RLS 全空读，静默返回空）和 A3（新用户 quota 崩，直接 500），且都零测试覆盖。这两个是 critical gap。

---

## E. 较小项

- **命名漂移**：表 `output_entries`（`v0.1:179`）vs 模型 `PracticeAttempt`（`routes-and-modules.md:20`）；音频路径 `~/rememate/audio/`（`dispatch:251`）vs `/srv/rememate/`（`v0.1:208`）。统一。
- **复习提醒幂等键 vs 7 天清理交互**：`dispatch:230` 幂等键用 `due_date`，`PushLog` 7 天清理（`:271`）；逾期未复习的词幂等键固定 → 当天只推一次、之后再不推，直到 7 天后日志清理才可能重推。与摘要的 per-day 键哲学不一致。明确「逾期词是否每天重新提醒」。
- **podcast token 无轮换/撤销**（6-22 C3 遗留）：`podcast_token` 是静态字段，RSS token-in-URL，泄露即可订阅，无 revoke 路径。上线后第一件优化，但设计要先留接口。
- **Postgres max_connections 共享**：gevent -w 2 + 连接池 + dispatch + 三个 timer 共用同机 PG 15 实例（与 MemoBuddy 共享）。gevent 下连接数远小于 sync，风险低，但部署时给两个库的池大小和 `max_connections` 留个明确数。

---

## F. 修订后的 P1 清单

### P1 必改（动手前先把文档改对）
| 项 | 类别 | 性质 |
|---|---|---|
| A1 RLS 落地清单（policy 补全 / FORCE / set_config / owner 角色分离） | 安全·正确性 | ★★★ |
| A2 webhook/bark SSRF 防护（白名单 + 私网拒绝 + 禁重定向） | 安全 | ★★★ |
| A3 create_user 建全 UserSettings + UserQuota（含 quota_reset_at 初始化） | 正确性 | ★★ |
| A4 每日摘要 timer/窗口对齐（删「每日 08:00 UTC」表述 + 半小时时区） | 正确性 | ★★ |
| A5 部署改 `-k gevent -w 2`，熔断措辞坐实 | 架构 | 已决策 |
| B1 句子广场 P1/P2 定调 | 范围 | 必定 |
| B2 Session Pad 文档 P1→P2 重编号 | 文档 | 必改 |
| B3 RLS/角色走手写 migration（承认 Alembic 例外） | 工程 | 必改 |

### P1 应改
| 项 | 类别 |
|---|---|
| C1 建词表入口（POST /words） | 功能完整性 |
| C2 commit_intake_source 加载 source | 正确性 |
| C3 WordCandidate 加 context 偏移字段 | 设计 |
| C4 CSV 改 SSE/分块，避免 nginx 超时 | 韧性 |
| C5 额度加单请求上限 | 防滥用 |
| C6 三按钮 → SM-2 映射定义 + 测试 | 核心算法 |
| D §测试缺口（尤其 RLS 本层、新用户 quota） | 测试 |

### 上线后第一件优化
- podcast 音频迁对象存储 + token 轮换/撤销
- 备份异机（6-22 C4）

### P2 设计补齐
- C7 点夯反刷机制（补 token-quota 内容或删交叉引用）
- 社交内容软删/级联（6-22 B7）、「活跃用户」聚合任务（6-22 B8，现 `sentence-square.md:65` 给了定义但 dispatch 没有对应聚合 job）
- Session Pad guest 写入 + RLS 的交互（guest 无 user_id，`set_rls_user` 只对 authenticated 设 GUC）

---

## G. 一句话总结

6-22 audit 把「用户多了会崩」清干净了，本轮抓的是「按文档写出来就崩」的另一半：**RLS 第三层空转 + 新用户 provisioning 不全 + webhook SSRF**——这三个会在前 10 个真实用户身上炸，且现有测试零覆盖。worker 已定 gevent，剩下的 P1 必改都不贵，关键是动手前先把文档改对，别把这些坑直接写进代码。
