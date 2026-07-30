# RemeMate Backlog

> 已知但有意推迟的事项。每条注明：来源 / 触发时机 / 简述。
> 不含已修复项（那些在 git 历史里）。

---

## 已决下一阶段实施队列

权威路线：`docs/wayfinder/2026-07-19-next-stage-roadmap/MAP.md` 和
`resolved/11-observation-and-final-implementation-roadmap.md`。以下不是松散想法，不应再次从零设计：

1. **SessionPad context-bearing candidate v1**：SP1 已提交；SP2 的 AI/人工 `term + context`、原文
   定位、packet/recap 统一创建、同来源合并与并发兜底已完成，并通过 644 项最终全量验收。
   下一张票才是 SP3 SessionPad 专属单候选聚焦审核，不要提前混入 observation dashboard。
2. **Privacy-safe observation dashboard v1**：最后开发；只聚合无正文信号，不做排行榜、个人钻取或
   Discord 自动发布。

恢复 master 的六项安全/数据可信度修复与 Review Story 已于 2026-07-30 部署；后续部署仍须显式
决策并先过目标环境 migration、全量测试和 strict doctor。

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

- **SQLAlchemy metadata 与既有迁移结构对齐**（SP2 发布检查 2026-07-30）
  GCP `flask db check` 会把 reading/recap 的复合外键、若干既有索引和
  `uq_words_list_normalized_word` 报为待删除/重建；这些漂移早于 SP2，SP2 新 partial unique index
  已被正确识别。引入 CI migration check 前应单独审计模型声明与实际迁移，避免自动生成破坏性
  “修复”迁移；不要在业务功能票中顺手接受 autogenerate 输出。
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

- **生产数据自动备份、轮替与异机副本**（线上核验 2026-07-15）
  当前升级前由人工在 `/home/ubuntu/rememate-backups/` 创建代码归档和 PostgreSQL dump，历史备份
  不会自动清理；现有文件体积很小，闭测期继续保留。正式开放注册前必须补齐每日自动备份、
  14 天轮替和至少一份异机/对象存储副本，并做一次实际恢复演练。不要只实现同机定时备份：
  当前服务器没有启用 `rememate-backup.timer`，同机磁盘故障仍会同时丢失主库和备份。

---

## 句子广场上线前（phase 7）必做



## 功能 / 体验（相关阶段顺带）

- **Landing 中文标题的窄屏断行校验**（用户反馈 2026-07-13）
  当前事实校准版的中文标题「围绕你的真实语料，而不是通用词表。」在特定窄宽度下曾把结尾
  「表。」挤到第二行。本轮仅通过收短文案缓解，不调整 landing 布局；后续真正重做 landing
  时，需在中文桌面与移动端逐条检查标题断行、行高和 CTA 宽度。当前 landing 文案改动保持本地
  未提交，不同步云端。

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

- **CSV 星标列尚未写入词条**（代码审查 2026-07-13）
  解析器可识别 `marked` / `starred` / `是否标注` 等表头，但 `WordCandidate` 没有承载字段，commit 时
  不会写入 `Word.marked`。当前导入提示不承诺星标列，避免误导；如要支持，需明确真值写法并补候选词字段、
  迁移、commit 与回归测试，作为独立数据变更处理。

- **闭测软反馈统一入池，不随手开工**（用户决策 2026-07-08）
  闭测阶段只立即修硬 bug：崩溃、数据丢失、权限/隔离、安全、无法完成核心流程。
  软 bug、文案、布局、体验微调统一记录到 BACKLOG，定期分批处理，避免每个小需求都扩大全量测试成本。

- **移动端阅读工具栏与底部导航避让**（国际化视觉审计 2026-07-12）
  390px 真机尺寸下，阅读器底部工具栏与全局固定五图标导航占用同一底部区域，工具栏可能被
  导航遮挡，导致字号、行距、字体和阅读模式控制不易触达。后续阅读 UI 批次应明确移动端层级：
  工具栏放在全局导航上方并增加安全区/底部间距，或阅读模式临时收起全局导航。不要在国际化
  分支夹带定位调整；需用实际滚动、沉浸模式和 iOS/Android 安全区截图验证。

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



---

## 健壮性 / 纵深防御

- **迁移约束名动态化**（review 2026-06-23 M7）✅ 2026-06-28 → 见「上线前必做」段同名条目的完成注记。



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
