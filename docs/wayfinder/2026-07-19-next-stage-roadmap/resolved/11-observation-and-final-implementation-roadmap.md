---
status: resolved
type: research
resolved_at: 2026-07-20
---

# 闭测观察合同与最终实施路线图

## Resolution summary

Wayfinder 规划阶段完成，没有剩余产品边界需要在写代码前开票。实施保持串行、可回滚：

1. 先验证并发布本地六项安全与数据可信度修复。
2. 单独实现并发布 `Review story + post-review output v1`。
3. 从更新后的 master 单独实现 `SessionPad context-bearing candidate v1`。
4. 最后实现私有管理员观察面板。

不得把三项塞进同一分支或一次部署；串行迁移，避免 Alembic 分叉。

## Privacy-safe observation contract

观察只回答：用户是否重复完成真实学习动作；短故事是否走到生成、写作和保存；SessionPad 是否走到
复盘、发送、感谢和候选采纳。不得读取句子、错误、词语、故事、翻译、伙伴备注、复盘或反馈正文。

### 活跃口径

使用滚动七个 UTC 日：

- 学习活跃：产生合法 ReviewLog、保存 OutputEntry、创建/完成 IntakeSource、创建 PartnerRecap、发送
  PartnerPacket、感谢/采纳，或产生白名单短故事事件。
- 登录、打开页面、管理员建号和语言切换不计学习活跃。
- 重复活跃：窗口内至少两个不同 UTC 日期发生上述动作。
- 只显示聚合数量，不显示身份或个人轨迹。

### 窄事件表

领域表能重建的事实继续从领域表聚合。只为短故事不可重建的漏斗增加
`learning_funnel_events(id, user_id, event_type, occurred_at, dedupe_key)`：

- 不允许 JSON、自由文本、URL、语言、provider 响应或 metadata。
- event type 使用数据库白名单：eligible normal/strong、generation started/ready/failed、cache hit、
  writing handoff、output saved。
- dedupe key 是服务端语义身份的 SHA-256，不保存原始词语或组合字符串。
- 表 FORCE RLS；普通请求只能写自己的事件，管理员只通过窄 dispatch 聚合服务取得数字。
- 故事正文最多 7 天；无正文事件保留 180 天，显式 CLI 支持 dry-run 清理。

### 管理面板 v1

显示最近七日和前一个七日窗口：

- 核心活跃：学习活跃用户、重复活跃用户、活跃天数总和。
- 基础闭环：复习用户、保存输出用户、复习后 24 小时为同一词保存输出的用户。
- 短故事：eligible、started、ready、handoff、story-attributed saved 用户。
- SessionPad：创建复盘、发送反馈、感谢、采纳候选用户。
- AI 可靠性：ready/failed 次数和 token 合计，不显示原始错误。

比率同时显示分子/分母；分母为零不显示百分比。面板留在 admin 区，普通用户 `403`。不做排行榜、
最近用户、个人钻取、内容搜索或“谁没有学习”。v1 不接 Discord bot；未来群内分享要求 cohort 至少
5 人，自动发送还需约 10 个周活跃用户和新的明确决策。

## Final implementation route

### Release 0: trusted closed-beta baseline

这是部署动作，不是新功能分支。当前恢复后的六项修复仍需先在重建的 PostgreSQL 测试环境中完成
migration、定向测试、全量 pytest 和 strict doctor，再单独备份并部署。任何迁移、RLS、评分或登录
异常都停止后续功能发布。

### Branch 1: `feature/review-story-v1`

#### RS1 — 数据地基与日内摘要

- 顺序 migration 增加 `review_story_runs`、`learning_funnel_events`、唯一键、状态约束、索引和 FORCE RLS。
- 为 ReviewLog 增加日内摘要需要的复合索引。
- 实现本地日窗口、同词最差评分、eligibility、确定性 3–5 词快照和 input hash。
- 不调用 provider，不增加路由，不渲染 UI。

#### RS2 — 生成、缓存与降级

- 实现 `review_story_v1` 最小输入、固定 JSON、双语锚点和文字系统校验。
- 实现 pending lease、唯一输入并发、两次逻辑尝试、ready cache 和 7 日正文清理。
- 记录 token 与白名单事件；provider 全挂或无效结果不影响复习。

#### RS3 — 复习回执与写作交接

- 在完成卡下方增加独立 HTMX 回执；静默日不渲染。
- normal/strong/loading/error/ready/cached 都留在回执内。
- 用 `story_run_id + term_key` 服务端验证进入现有 `/write`。
- 只有 OutputEntry 真正保存成功才记录 story-attributed saved。
- 不做故事历史、发布、收藏、图片或第二编辑器。

#### RS4 — 收口

- i18n、桌面/390px 浏览器检查、清理 CLI、运维文档和全量回归。
- 不夹带 Landing、CSV、阅读工具栏或 SessionPad UI。

### Branch 2: `feature/sessionpad-context-candidates-v1`

只从已合并故事分支后的新 master 创建。

#### SP1 — schema 与服务契约

- 顺序 migration 给 WordCandidate 增加 nullable context_excerpt/context_provenance。
- provenance 仅允许 source_quote/user_edited/NULL。
- 不回填旧 source_example，不改历史 definitions。
- SessionPad commit 不再以 source_example 兜底例句。

#### SP2 — SessionPad 产生候选

- AI 与人工共用 term + context。
- AI context 必须能在反馈原文定位，不另造例句。
- 同一 IntakeSource 在来源锁下按规范化词合并。
- 只关联一次伙伴交换，不新增逐消息 context FK。
- AI 失败保留人工拆分和原始反馈。

#### SP3 — 聚焦候选审核

- 仅 SessionPad 使用单候选聚焦队列。
- 显示轻量来源、可编辑语境、provenance、缺语境和瞬时 AI 降级。
- “将语境用作例句”只填草稿；接受才保存。
- 已有词只关联，不创建重复词或自动覆盖释义。
- 不显示 bulk accept；其他来源审核保持不变。

#### SP4 — 收口

- 覆盖 packet、recap、candidate、commit、已有词、RLS、并发和降级。
- 桌面/390px 检查并更新设计与运维文档。
- 模块切换说明可随批加入；重复发送策略继续留 Backlog。

### Branch 3: `feature/closed-beta-observation-v1`

- OB1：固定 dispatch 聚合服务，只返回预定义数字结构。
- OB2：现有 admin 页面增加紧凑统计区，覆盖权限、空数据和小样本。
- OB3：多用户聚合、无身份/正文断言、dispatch 失败降级；不接 Discord bot。

## Test and deployment gates

每个分支覆盖 unit、integration、concurrency、RLS、regression 和 1440px/390px browser 检查。合并前：

1. 相关测试与全量 `pytest -q`。
2. `flask doctor --strict`。
3. `flask db current` 且只有一个 head。
4. `git diff --check` 和干净工作区。

每次发布记录 commit/head、备份 PostgreSQL、不覆盖 `.env`/用户数据/词典，先迁移再 doctor、重启和
真实冒烟。带 migration 的 release 不能只回滚代码。

## Stop conditions

立即停止发布：跨用户越权；故事重复推进评分；AI 失败阻断核心流程；相同输入并发重复调用/候选；
语境自动成为例句；迁移多 head、不可恢复或损伤数据。

停止扩功能、先验证：

- Story 达到 10 个 eligible user-days 且至少 3 人后仍无 writing handoff 或 attributed save，不增加
  历史、图片或入口，先访谈。
- 完成 2–3 次真实双人 SessionPad 交换仍无 thank 或 adoption，不加聊天、群组或复杂互动。
- 约 10 个周活跃用户前不自动向 Discord 发布小样本数据。

## Code-ready handoff

Wayfinder 已无开放票。下一次明确开发指令从干净 master 创建 `feature/review-story-v1`，第一张代码票
只做 RS1 数据地基与日内摘要，不调用 AI、不做 UI。当前恢复环境仍须先满足 `docs/HANDOFF.md` 的
PostgreSQL 验证闸门。

## Implementation status — 2026-07-26

本节只记录实施进度，不改写上方已决边界：

- `feature/review-story-v1` 已创建。
- RS1 数据/RLS/日内摘要、RS2-A 多语言生成契约、RS2-B 事务状态机、RS2-C provider 编排/token/
  无正文漏斗事件均已提交并通过 GCP PostgreSQL 验收；当前迁移 head 为 `f1a2b3c4d5e6`。
- RS2-C 提交 `e800ef0`；定向 52 passed、两条并发路径各连续 5/5、全量
  607 passed。测试机 strict doctor 仅因 provider/词典资产缺失非 0。
- 下一阶段是 RS3“复习回执与写作交接”；不拆出名为 `RS3-C` 的票，先基于已决边界定义第一张
  可验收小票，再开始路由/UI。
- 当前状态的权威入口仍是 `docs/HANDOFF.md`。

