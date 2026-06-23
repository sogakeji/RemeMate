# RemeMate 架构 Review — v0.1

> Review 日期：2026-06-22
> 审查对象：`docs/arch/v0.1-direction-and-constraints.md` 及 `docs/design/` 下四份设计文档
> 审查视角：架构师Chatgpt
> 前提假设（用户确认）：注册用户短期 < 100，长期天花板 ≤ 5000

---

## 修复状态（2026-06-23 回填）

下表为本 audit 各 finding 的闭环状态，逐条对照修复后的设计文档核验。✅=已落地　⏳=按计划延后　↘=规模上撤销/下调。

| Finding | 状态 | 落地位置 |
|---|---|---|
| A1 章节号重复 | ✅ | v0.1 §2.5/§2.6 已分号 |
| A2 Session Pad P1/P2 矛盾 | ✅ | 定 P2；session-pad 头部 + 编号约定；routes 已清 |
| A3 点夯 作者/点击者 | ✅ | token-quota §点夯：点击者得 |
| B1 RLS+dispatch 冲突 | ✅ | data-isolation §后台任务：BYPASSRLS 角色分工 |
| B2 RLS 连接残留 | ✅ | data-isolation：teardown 清 GUC + 连续两请求测试 |
| B3 NSFW fail-open | ✅ | llm-failover：fail-closed（is_nsfw=True）|
| B4 HTMX CSRF | ✅ | v0.1 §2.4 |
| B5 SECRET_KEY 一钥多用 | ✅ | 独立 DATA_ENCRYPTION_KEY（token-quota §加密）|
| B6 时区语义 | ✅ | users.timezone + 本地午夜重置 |
| B7 社交软删/级联 | ⏳ 待补 | 广场已进 P1，但作者删号/删句对「一起记」引用方的级联仍未设计，广场扩展前补 |
| B8 活跃用户未定义 | ✅ | sentence-square:65 已定义；P1 硬编码门槛=1，聚合 job 延后 |
| B9 流式中途失败 | ✅ | llm-failover §流式 failover 限制 |
| B10 总超时 | ✅ | llm-failover：25s deadline |
| B11 任务路由盲点 | ✅ | llm-failover：各 task 链显式，NSFW 仅 DeepSeek |
| C1 worker class | ✅ | 定 gevent -w 2（v0.1 §2.2/§6）|
| C2 dispatch TTS 拆分 | ✅ | 独立 timer + flock + 幂等键 |
| C3 本地磁盘音频 / podcast token | ⏳ 上线后 | 音频迁对象存储延后；token 轮换接口已留（dispatch:313）|
| C4 备份异机 | ⏳ 上线后 | rsync 异机延后 |
| D 规模驱动各项 | ↘ 撤销/下调 | 5000 上限下不做（选 gevent 后无需 Redis 等）|

> 详细修复内容见 commit `5c3862b`（RLS 写策略残留补于 `ba51e95`）。后继评审见 [review-2026-06-23-pre-implementation-eng-review.md](review-2026-06-23-pre-implementation-eng-review.md)。

---

## 0. 总体判断

文档决策链清晰、技术选型有 MemoBuddy 验证背书，作为 solo 项目质量高于平均。

**核心结论**：在 5000 用户天花板下，**没有一条是"用户多了就崩"的经典扩展性瓶颈**。会先出问题的都是**架构决策型**问题——它们在几十到几百用户时就会暴露，但修起来都不贵，关键是 P1 文档里要把这些决策写死，而不是留空。

换言之：**不需要为 5000 用户做任何"大数据"准备，但需要为"前 300 个真实用户"做几个正确的早期决策。**

Review 分为四类：
- **A. 文档一致性** — 与规模无关，必改
- **B. 逻辑正确性 / 安全** — 与规模无关，必改
- **C. 早期架构决策** — 几百用户内会暴露，必改
- **D. 规模驱动** — 在 5000 上限下基本撤销或大幅下调

---

## A. 文档一致性（必改，与规模无关）

### A1. 架构文档章节号重复
`v0.1-direction-and-constraints.md` 有两个"2.5"：前端技术栈（:56）与应用层鉴权（:70）。后者应为 2.6。架构基线文档不应有此类硬伤，暴露自审流程缺失。

### A2. Session Pad 的 P1 归属自相矛盾
- `session-pad.md:42` 把"线上语言交换"标为 **P1 主打**；
- `session-pad.md:6` 头部又写"待详细设计（P2/P3 功能）"；
- `v0.1...md:62` 默认 Session Pad 已存在（"仅该页面引入 Socket.IO"）。

三处口径不一致，**必须先定调**。若它是 P1，Socket.IO 多 worker 适配必须在 P1 解决（见 C1）；若不是，2.5 节措辞要改。

### A3. 点夯激励"作者得 / 点击者得"自相矛盾
`sentence-square.md:124-128` 正文写"每次点夯 → 赠送**点击者** token"，紧接着飞轮描述又写"写好句→获夯→**作者**得 token"。两套激励模型未说明谁得。这是会被实现成 bug 的歧义。

---

## B. 逻辑正确性 / 安全（必改，与规模无关）

### B1. RLS 与 dispatch 后台任务的逻辑冲突 ★
`data-isolation-security.md` 的 RLS 策略 `user_id = current_setting('app.current_user_id')` 会**拒绝任何跨用户读取**。但 dispatch / podcast / bark 这些后台任务的本职就是**遍历所有用户**读到期词。文档没有说明后台任务走哪条路径：
- 后台任务如何切换租户上下文（每用户一次 SET 性能差）；
- 是否用 `BYPASSRLS` 角色（那 RLS 兜底意义削弱）；
- 跨用户批量扫描走哪条路径。

**建议**：请求路径走 RLS（第一/二层防御 + RLS 兜底）；后台批处理用独立 `BYPASSRLS` 连接角色 + 显式 user_id 过滤（仅靠第一/二层防御）。这是 RLS 多租户的经典分工，文档应明确写出。

### B2. RLS 连接复用的 current_user_id 残留风险
`SET LOCAL` 是事务级，逻辑上 COMMIT 后失效。但 SQLAlchemy 连接池在归还/重用、跨请求复用、后台线程无请求上下文等场景下，若任一处 COMMIT 时机不对或连接被另一请求复用而未重新 SET，`current_user_id` 可能残留前一个用户的值——**这是跨用户泄漏的最隐蔽路径**。文档把它写成"加个 before_request 即可"过于乐观。

**要求**：
- 连接归还前 `RESET app.current_user_id`；
- 后台任务显式 SET；
- 集成测试覆盖"连续两个请求不同用户"场景。

### B3. NSFW 检测 fail-open = 公开广场可能泄 NSFW ★
`llm-provider-failover.md:64`：全部 provider DOWN 时 NSFW 默认 `is_nsfw=False`（放行）。
`sentence-square.md:74`：`is_nsfw=true` 时隐藏公开按钮。
组合结果：**检测失败 → 默认 False → 公开按钮可见 → NSFW 句子进广场**。对公开社交内容，fail-open 是错误方向。

**建议**：安全敏感检测 fail-closed——provider DOWN 时默认隐藏公开按钮 / 进待审队列。

### B4. HTMX POST 缺 CSRF 保护
`v0.1...md:56-61` 大量 `hx-post`，Flask-Login 默认不防 CSRF。文档未提 Flask-WTF / 自定义 CSRF header。HTMX 站点 CSRF 是必修课。

### B5. 用户 DeepSeek key 加密用 SECRET_KEY 一钥多用
`v0.1...md:91`"系统 SECRET_KEY 派生加密"问题：
- SECRET_KEY 本就承担 session 签名，一钥多用，泄露面叠加；
- 无轮换策略（轮换后旧密文如何解密？）；
- 无信封加密 / KMS 分离。

**建议**：独立 `DATA_ENCRYPTION_KEY`，密文带 key 版本号便于轮换。托管第三方 API key 的基本要求。

### B6. 时区语义未定义（token 额度每日重置）
`v0.1...md:142` 的 `tokens_used_today` 每日重置，但**按谁的时间**？UTC？用户本地？`users` 表无 timezone 字段（:138）。跨日用户会困惑。这是正确性问题，不是性能问题。

**建议**：users 表加 timezone 字段，额度按用户本地日重置。

### B7. 社交内容软删 / 级联未设计
"一起记"把别人 `output_entry` 例句引入自己 SRS。若作者删号 / 删句，引用方例句如何处理？硬级联删除会悄悄吃掉别人复习中的例句；软删 + 快照副本更安全。社交内容生命周期与私有词库的耦合关系需在 P2 上线前补设计。

### B8. "活跃用户"未定义
`sentence-square.md:58-63` 门槛表用"每语言组活跃用户"，但"活跃"=？日活？周活？谁算、多久算一次、存哪？无定义就无法实现。需补聚合任务和活跃定义。

### B9. failover 流式中途失败无处理
`llm-provider-failover.md:31-41` 的代码草图只覆盖"调用即抛异常"的预流式失败。若首 token 之后 provider 才断流，SSE 已开写，无法切到备用 provider。需点明这个限制（要么放弃中途 failover 提示重试，要么缓冲首块后再下发）。

### B10. failover 无总超时预算
链式 failover：若每个 provider 各超时 30s，最坏 90s 才抛 `AllProvidersDown`。需定义**请求级总 deadline**（如 25s）跨 provider 共享。

### B11. failover 任务路由有盲点
`llm-provider-failover.md:18-20` 表格里 NSFW 检测、翻译、对话分属不同 provider 链，但 NSFW 在 DeepSeek 之外是否有备选？若 NSFW 只挂 DeepSeek，DeepSeek 挂时直接走 fail-open（见 B3）。每个 `task` 的 provider 链应显式列出。

---

## C. 早期架构决策（几百用户内会暴露，必改）

这一类是 Review 的重点：它们不是规模问题，而是**文档留空导致的早期决策风险**。

### C1. worker class 未定义 — 这是 P1 最关键的留空 ★★★

`v0.1...md:189` 写定 `gunicorn -w 4`，但**未定 worker class**。这一个留空同时牵动三个子问题：

#### C1a. Socket.IO 跨 worker 丢消息（最早爆，<10 个并发 Session Pad 用户）
Flask-SocketIO 在多 worker 下默认内存 adapter，跨 worker 的房间/广播会丢失——用户 A 在 worker1 输入，用户 B 恰好连在 worker3 就收不到。这是 Socket.IO 多进程部署的著名坑。

#### C1b. SSE 占满 sync worker
默认 sync worker 下，**每个 SSE 长连接独占一个 worker**。`-w 4` 意味着全站最多 4 个并发 AI 流式响应，第 5 个用户阻塞。触发阈值约 **~1000 注册用户**（对应 4 个并发流）。

#### C1c. 内存熔断器在多 worker 下失效
`llm-provider-failover.md:53,80` P1 建议内存版熔断。但 4 个进程各有独立熔断状态——worker1 已熔断跳过 DeepSeek，worker2/3/4 仍持续打挂掉的 DeepSeek，熔断形同虚设。

#### ★ 推荐解法：选定 gevent worker，一招消解 C1a/C1b/C1c
**5000 用户量级，最干净的架构选择是不要上 4 个 sync worker。** 跑 1–2 个 **gevent/eventlet worker**（`gunicorn -k gevent -w 2`），一个进程就能扛住 SSE 长连接和 Socket.IO 并发：

- 不需要 Redis adapter（单进程内存 adapter 够）；
- 不需要担心 SSE 占满 worker（gevent 协程化，一个 worker 成千上万连接）；
- 内存熔断器合法（单进程状态一致）；
- Redis 整个 P1 都不必引入。

**代价**：gevent monkey-patch 全局生效，部分库会踩坑，需在 P1 早期验证。

**行动项**：在架构基线写死 `gunicorn -k gevent -w 2`（或等价方案），不再留空。这一行决策同时关闭 C1a/b/c 三条 finding。

### C2. dispatch 15min timer 塞进播客 TTS 生成 ★
`v0.1...md:198` 单进程 systemd timer 扫描全部用户做 Bark + 播客生成。问题：
- TTS 生成是准实时操作（每用户 ~10–20s），混进心跳循环后，**100–300 用户就可能跑超 15 分钟** → 重叠执行 / 重复推 Bark / 漏推；
- 无分布式锁防重叠；
- 无幂等保证（重复推 Bark 用户收到两次）。

**建议（廉价修法，不必上 Celery）**：
- TTS 生成拆出心跳循环，独立任务；
- 加 `flock` 防重叠；
- 推送幂等键（同一 user+word+due_date 只推一次）。

### C3. 本地磁盘存播客音频
`v0.1...md:114`"音频按 user_id 隔离"——隔离在**哪**？未说明。TTS 音频按用户按词累积，触发阈值约 **1000–2000 用户**（取决于 VPS 磁盘 40–80GB）会变成运维事件（盘满服务挂）。

**补充安全问题**：`podcast_public_base` + token in URL 是"私人播客"标准做法，但 RSS URL 里的 token 一旦泄露给任何看到 feed 的人即可订阅，**安全靠隐蔽**。需说明 token 轮换、撤销机制（与规模无关，见 B 类性质）。

**建议**：上线后第一件优化迁对象存储（S3/R2）；token 支持轮换/撤销。

### C4. 备份在本机 = VPS 挂了数据和备份一起没
`v0.1...md:194` `pg_dump + gzip + 14 天轮替` 到本机 `~/rememate/backups/`。单用户私站可接受，**一旦托管他人词库就必须异地备份**。这是从"个人项目"到"多用户服务"的合规分水岭。

**建议**：rsync 到对象存储 / 异机，廉价即可。仍保留，理由从"合规"降为"对用户负责"。

---

## D. 规模驱动（5000 上限下撤销或大幅下调）

以下 finding 在大用户量下成立，但在 ≤5000 注册用户前提下**不是问题**：

| Finding | 原判断 | 5000 下重判 | 理由 |
|---|---|---|---|
| 单库无水平扩展路径 | 必改 | **撤销** | 5000 用户单 PG 绰绰有余，读写分离/分区/pgbouncer 都不需要 |
| `review_logs` 分区 | 必改 | **撤销** | append-only 到几百万行 PG 也扛得住 |
| `tokens_used_today` 热行竞争 | 必改 | **撤销** | 不同用户不同行，5000 用户里同用户并发打 AI 概率极低 |
| 大表索引（words/review_logs） | 必改 | **下调** | `due_date` 等查询模式索引仍建议建，但不紧迫 |
| Redis 纳入 P1 | 必改 | **撤销** | 选 gevent worker 后 P1 不需要 Redis |
| 读写分离 / 副本 | 上线前 | **撤销** | 5 万用户以上的事 |
| PG max_connections | — | 配置问题 | 取决于 worker/池配置，非用户驱动 |
| 全面可观测性 | 必改 | **下调为软建议** | 5 千用户建议有 Sentry，非架构级要求 |

---

## E. 触发阈值速查表

为便于判断优先级，按下表用量模型重算（语言学习类 AI 重度使用）：

> 注册用户 N → DAU ≈ 20%N → 同时在线 ≈ 2%N → 同时 AI 流式 ≈ 0.4%N → 同时 Session Pad 房间 ≈ 在线 × 5%

| 瓶颈 | 触发条件 | 粗略注册用户阈值 | 性质 |
|---|---|---|---|
| Socket.IO 跨 worker 丢消息 (C1a) | ≥2 sync worker + 同房间两人落不同 worker | **<10 并发** | worker 数驱动，与总量无关 |
| dispatch 15min 超时 (C2) | TTS 生成进 dispatch 循环 | **100–300** | 只推 Bark 不生成音频则 5000 无事 |
| 本地磁盘音频塞满 (C3) | 按词缓存 TTS 累积 | **1000–2000** | 取决于 VPS 磁盘 |
| SSE 占满 sync worker (C1b) | 并发 AI 流式 > worker 数 | **~1000** | 选 gevent 后消失 |
| token 计数热行 (D) | 同用户并发打 AI | **永不** | 撤销，只剩时区语义 (B6) |
| words/review_logs 表性能 (D) | 千万级行 + 索引不当 | **5 万+** | 远超上限 |

**关键解读**：真正会先咬人的是前三条，且都在 5000 目标之内；但前两条（C1a、C2）不是规模问题，是**架构决策型**问题，几十到几百用户就暴露，修起来都不贵。

---

## F. 修订后的 P1 清单（5000 用户上限下）

### P1 必改
| 项 | 类别 | 性质 |
|---|---|---|
| C1 worker class 写定（gevent，消解 C1a/C1b/C1c） | 早期决策 | 架构决策 |
| B1 RLS + dispatch 后台方案 | 逻辑 | 必改 |
| B3 NSFW fail-closed | 安全 | 必改 |
| B4 HTMX CSRF | 安全 | 必改 |
| B2 RLS 连接复用测试 | 正确性 | 必改 |
| A1/A2/A3 文档一致性 | 文档 | 必改 |

### P1 应改
| 项 | 类别 |
|---|---|
| B5 独立加密 key | 安全 |
| B6 时区语义 + timezone 字段 | 正确性 |
| B9/B10/B11 failover 细节（流式中途失败 / 总超时 / 任务路由） | 设计 |
| C2 dispatch 拆 TTS + flock + 幂等 | 韧性 |

### 上线后第一件优化
- C3 播客音频迁对象存储 + token 轮换
- C4 备份异机

### P2 设计补齐
- B7 社交内容软删 / 级联
- B8 "活跃用户"定义

---

## G. 一句话总结

5000 用户天花板下，性能/扩展那半 finding 基本可以扔掉，但**逻辑正确性、安全、文档一致性那半一条不少仍然成立**。最关键的是 C1：与其为多 worker 引入一堆 Redis，不如在 P1 就选定 gevent worker——这是该量级下最省事的解法，也正好填补文档"worker class 未定义"这个真 finding。

**你不需要为 5000 用户做任何"大数据"准备，但需要为"前 300 个真实用户"做几个正确的早期决策。**
