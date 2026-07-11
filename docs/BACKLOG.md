# RemeMate Backlog

> 已知但有意推迟的事项。每条注明：来源 / 触发时机 / 简述。
> 不含已修复项（那些在 git 历史里）。

---

## 上线前必做（开放注册 / 部署前）

- **按 token 计的额度硬约束 + 额度并发 TOCTOU**
  来源：用户决策 2026-06-23 + review 阶段四 M（MEDIUM）。当前 /write 门禁按「句数」计
  （系统 3 / 自带 20，按提交）。两个相关问题一起处理：
  1. 单句 140 字符 + 批改多轮，token 理论上可放大；自带 key 或开放注册时尤甚。需补按 token
     的硬上限（`UserQuota.tokens_used_today` + `daily_base_limit` 拦截）+ 单请求 token 上限
     `MAX_TOKENS_PER_REQUEST`（token-quota.md 已设计，/write 未接）。
  2. `writing.submit_correction` 是 check-then-record：`check_write_quota`（只读）→ 批改（~3s）
     → `record_correction`（才 +1）。并发提交可都过预检后各自 +1，**突破每日上限**（review C5
     的「check 不预占」同病）。改原子自增：
     `UPDATE user_quota SET corrections_today=corrections_today+1 WHERE corrections_today<:limit RETURNING`，
     按返回行数判放行。邀请制下影响有限，开放注册前必修。

- **htmx 本地化**（review 2026-06-23 L7）✅ 2026-06-28
  base.html 改用 `app/static/vendor/htmx.min.js` 本地引用，不再走 unpkg CDN。

- **CI 自动跑迁移**（review 2026-06-23 L6）
  conftest 不自动迁移；测试库需手动 `flask db upgrade` 到最新。CI 必须有该步骤，否则
  级联/索引类回归测试会因 DB 落后而误判。
  > **已知约束**（2026-06-28 排摸）：测试库的 `rememate` 角色在 init-test-db.sql 里
  > `REVOKE CREATE ON SCHEMA public FROM PUBLIC` 且未单独 GRANT CREATE，**无建表权**；
  > 而 TestingConfig.MIGRATE_DATABASE_URL 指向 TEST_DATABASE_URL（rememate 角色）。
  > 自动迁移需引入 `TEST_MIGRATE_DATABASE_URL`（owner 角色 + rememate_test）让
  > conftest 用 owner 跑 alembic upgrade head。加 CI 时一并处理。

- **迁移约束名动态化（可重入）**（review 2026-06-23 M7）✅ 2026-06-28
  1ca04f530(b27062024cc0 cascade FK → 查 pg_constraint 动态取名/IF EXISTS)＋
  0be5bc17 / fe681cf5 / f7429a9 全部幂等化（policy DROP+CREATE、column IF NOT EXISTS）。
  两轮 downgrade base → upgrade head 验证可重入。

- **Bitwarden 迁机评估**（v0.1 §2.3）
  开放注册前评估把同机 Bitwarden 迁到独立机器（RemeMate 漏洞勿波及密码库）。

---

## 句子广场上线前（phase 7）必做

- **NSFW 判定不能搭批改的 failover 链**（review 阶段四 M，MEDIUM）
  `is_nsfw` 是批改 JSON 的字段，走 `task="correction"` 链（DeepSeek→GPT）。DeepSeek 挂时
  GPT 同时做批改和 NSFW 判定，违反 llm-failover.md「NSFW 仅 DeepSeek、fail-closed」。全挂时
  已 fail-closed（degraded→is_nsfw=True），缺口在「DeepSeek 挂、GPT 在」半挂态：GPT 可能漏判
  NSFW→用户能公开 NSFW 到广场。P1 广场未上线影响小。phase 7 前修：批改 provider≠deepseek 时
  publish 用的 is_nsfw 强制 True（保守），或公开前单独跑一次仅 DeepSeek 的 nsfw 链
  （llm.py 已留 `"nsfw"` 链，当前未被调用）。

---

## 功能 / 体验（相关阶段顺带）

- **阅读收词小优化 v1：去向感 + 来源感**（用户决策 2026-07-09）
  阅读模块继续收敛为「阅读收词入口」，不增强成完整阅读器。下一批小优化优先做：
  点击「加入学习」后默认留在阅读器继续读，并明确提示已加入本篇候选词、提供轻量去审核入口；
  候选审核页和词库详情显示轻量来源（`来自《文档名》` + PDF 原文例句）。不做回到原文位置、
  不在首页复习卡片显示来源、不做单独阅读候选审核页。后续如开工，建议分支名
  `reading-source-polish`，范围只碰候选审核、词库详情、阅读器加入后的提示。

- **SessionPad 编辑器补充模块切换说明**（用户反馈 2026-07-10）
  来源：B2 真机测试。当前切换「词语 / 表达」「错误修正」等模块时，会保留输入框内
  已写正文，只改变条目分类、模块高亮、标签和占位提示；这是为避免现场误点造成草稿丢失。
  用户可能把“正文没有变化”误解为切换未生效。下次集中修改 SessionPad UI 时，在编辑卡中
  增加一条极短说明，明确“切换模块不会清空已输入内容，可先写再分类”。本项只改说明文字，
  不改草稿状态模型，不为每个模块维护独立草稿。

- **SessionPad：同一反馈内容的重复发送策略待定**（闭测反馈 2026-07-11，P1）
  当前整包快照幂等只能阻止完全相同的整包重复提交；同一条内容仍可能通过不同子集或新反馈包反复发送。
  产品规则尚未定稿：可以允许多次发送不同条目、但同一原始条目仅在显式修改或标记为补充后重发；也可
  进一步收窄为只发送“错误修正”。实现前先确认采用哪条规则，并定义去重键、补充发送语义及历史数据
  行为；不要仅按模块类别粗暴去重。

- **SessionPad：为反馈人工拆分补 AI 词语建议**（闭测反馈 2026-07-11，P1）
  B11 已完成可靠的人工路径：一条反馈可拆成多个词语级候选，每个候选保留原句语境，重复项和已有词会
  被过滤。下一切片只在此基础上增加 AI 建议：从反馈中提出值得学习的词语 / 表达，预填到可编辑的逐行
  输入区，用户确认后仍走 B11 的提交路径。AI 不可用、超时或返回异常格式时必须退回人工拆分，不能阻塞
  查看反馈、造成内容丢失或直接入库。不要为 AI 建立第二套候选创建逻辑。

- **三行日记随机问题遵循用户语言设置**（用户反馈 2026-07-10）
  非法语学习者仍会看到法语随机问题。修复时先明确问题应使用用户母语 / `feedback_language`
  还是当前目标语言 / `current_language`，再检查问题池或生成提示是否硬编码法语；无论最终选择哪条
  产品规则，问题都不得与用户语言设置无关。补中文、日语学习场景的回归测试。

- **生词本补“只看星标单词”筛选**（用户反馈 2026-07-10）
  现有词条支持星标，但列表无法只看星标。下次词库体验批次补充筛选，并验证可与搜索、排序组合使用。

- **CSV 导入表头提示同步实际映射能力**（用户反馈 2026-07-10）
  当前仍提示“表头需含 word, meaning（可选 part_of_speech, example, note）”，已经落后于实际支持的
  中文表头及第三方表头别名。后续提示应由解析器支持清单驱动，或改为不易过期的概括文案；
  同步更新导入错误提示测试，避免文案与代码再次漂移。

- **手动加词 AI 填充遵循用户母语**（用户反馈 2026-07-10）
  AI 生成的例句翻译和笔记固定为法语，而不是用户母语。优先检查提示词是否误把目标语言当作
  解释语言，以及路由 / 服务是否漏传 `feedback_language`；修复需覆盖“法国人学中文”和
  “中文母语者学法语”两个方向。

- **闭测软反馈统一入池，不随手开工**（用户决策 2026-07-08）
  闭测阶段只立即修硬 bug：崩溃、数据丢失、权限/隔离、安全、无法完成核心流程。
  软 bug、文案、布局、体验微调统一记录到 BACKLOG，定期分批处理，避免每个小需求都扩大全量测试成本。

- **stats 时区一致性**（review 2026-06-23 M2）✅ 2026-06-28
  `get_stats` 「今日已复习」改用 `today_local_start_utc(user.timezone)` 按本地午夜切。
  +`timeutil.today_local_start_utc`（可注入 `now_utc` 供单测）+ 4 个单测覆盖跨时区边界。

- **/words 详情页 N+1**（review 2026-06-23 M6）✅ 2026-06-28
  `get_word_list(..., eager=True)` 用 `selectinload(words).selectinload(definitions)`，
  detail 路由 eager 取。+集成测试用查询计数断言 definitions 只查一次。

- **lapse 复习体验**（review 2026-06-23 M8）✅ 2026-06-28
  lapse 后 `due_date = now + LAPSE_MIN_DELAY(10min)`，从「即时到期」队首移开，
  本轮先转去复习其他到期词，稍后回到 lapse 牌。死循环感消除。

- **「今日到期」文案**（review 2026-06-23 L1）✅ 2026-06-28
  `due_count` 实为「所有到期（due_date<=now）」（含逾期），文案从「今日到期」改述
  为「待复习」/「待复习：N」（main/index.html + words/stats.html）。语义与 query 对齐。

- **add_word 词表内去重**（review 2026-06-23 L10）
  同表可重复加同词；输入管道 commit 时会埋重复牌。加服务层去重或 unique。

---

## 健壮性 / 纵深防御

- **迁移约束名动态化**（review 2026-06-23 M7）✅ 2026-06-28 → 见「上线前必做」段同名条目的完成注记。

- **output_entries INSERT policy 校验 word_id 归属**（review 2026-06-23 L12）
  oe_ins 只校验 user_id，未断言 word_id 属于本人。正常路径不可达，但配合 word_id CASCADE
  是纵深缺口。policy 加 `word_id IN (本人的 words)`。

- **provisioning engine 复用**（review 2026-06-23 L2）
  `_bypass_session` 每次 `create_engine`。CLI 一次性 OK；P2 开放注册路由需长生命周期共享
  engine + `pool_pre_ping`。

- **/login IP 限流**（review 2026-06-23 L8）
  仅按账号锁定；攻击者轮换账号可跨账号撞库。P2 上 Flask-Limiter。

- **状态/类型字段 DB 端 CHECK**（review 2026-06-23 L9）
  `source_type` / `status` / `role` / `ReviewLog.source` 等自由 String，无枚举约束。

- **healthz 豁免 RLS 钩子**（review 2026-06-23 L3）
  已登录请求的每次 /healthz 触发 load_user 一次查库；高频健康检查压库。可豁免。

- **reset_rls_user 异常吞掉过宽**（review 2026-06-23 L4）
  已随阶段四 RLS 重构移除该 teardown；若将来恢复类似逻辑，`except Exception` 要至少 log。

- **gunicorn timeout 与 SSE**（review 2026-06-23 L11）
  `timeout=60`；长流式端点（造句批改改流式 / 输入管道）慢网络可能被 arbiter 杀 worker。
  SSE 端点单独放宽或加心跳。

- **Global ignored words / do-not-suggest-again** (user feedback 2026-07-08)
  Current WordCandidate.status=ignored only applies to one intake_source. New text extract, CSV import, and reading intake tasks do not auto-filter historical ignored candidates. If we add permanent ignore later, create a separate per-user ignore table keyed by user_id + language_code + normalized word, and keep UI wording separate: ignore this batch vs never suggest again. Do not reuse current ignored semantics as global ignore.
