# RemeMate Backlog

> 已知但有意推迟的事项。每条注明：来源 / 触发时机 / 简述。
> 不含已修复项（那些在 git 历史里）。

---

## 上线前必做（开放注册 / 部署前）

- **按 token 计的额度硬约束**
  来源：用户决策 2026-06-23（阶段四）。当前 /write 门禁按「句数」计（系统 3 / 自带 20），
  按提交次数。问题：单句 140 字符 + 批改多轮，token 理论上仍可能被放大；自带 key（20 句、
  长度不限）或将来开放注册时尤甚。**邀请制下不会失控**，但开放注册前必须补一层按 token 的
  硬上限（`UserQuota.tokens_used_today` 已有，接 `daily_base_limit` 做拦截）+ 单请求 token 上限
  （`MAX_TOKENS_PER_REQUEST`，token-quota.md 已设计但 /write 未接）。

- **htmx 本地化**（review 2026-06-23 L7）
  base.html 从 unpkg CDN 加载 htmx；CDN 宕/被墙时核心复习/造句交互全废。改为本地静态资源。

- **CI 自动跑迁移**（review 2026-06-23 L6）
  conftest 不自动迁移；测试库需手动 `flask db upgrade` 到最新。CI 必须有该步骤，否则
  级联/索引类回归测试会因 DB 落后而误判。

- **Bitwarden 迁机评估**（v0.1 §2.3）
  开放注册前评估把同机 Bitwarden 迁到独立机器（RemeMate 漏洞勿波及密码库）。

---

## 功能 / 体验（相关阶段顺带）

- **stats 时区一致性**（review 2026-06-23 M2）
  `get_stats` 的「今日已复习」按 UTC 午夜切，没用 `current_user.timezone`。应复用 timeutil
  按用户本地午夜算。Asia/Shanghai 用户本地 00:00–08:00 的复习会错位。

- **/words 详情页 N+1**（review 2026-06-23 M6）
  detail.html 逐词懒加载 `w.definitions`。`get_word_list` 改 `selectinload`/`joinedload` 预加载。

- **lapse 复习体验**（review 2026-06-23 M8）
  lapse 后 `due_date=now` + `/review` limit=1 → 同一张牌可能立刻再现，有「死循环感」。
  考虑 lapse 后压到队尾或加最小间隔。

- **「今日到期」文案**（review 2026-06-23 L1）
  `due_count` 实为「所有到期（due_date<=now）」，文案写「今日到期」，语义不符。

- **add_word 词表内去重**（review 2026-06-23 L10）
  同表可重复加同词；输入管道 commit 时会埋重复牌。加服务层去重或 unique。

---

## 健壮性 / 纵深防御

- **迁移约束名动态化**（review 2026-06-23 M7）
  b27062024cc0 硬编码 FK 约束名、无 `IF EXISTS`，不可重入。改查 `pg_constraint` 动态取名。

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
