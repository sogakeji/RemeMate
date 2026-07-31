# RemeMate HANDOFF

## 2026-07-31 SessionPad 带语境候选 v1 — 整分支审查修复

- 整分支只读审查发现并复现：同一 recap 的两个不同条目并发加入候选时，预先加载的 SQLAlchemy identity map 会让第二个请求在取得行锁后仍看到旧 `intake_source_id`，从而创建两个 SessionPad 来源。修复提交为 `b270d04`。
- recap 行锁查询现在使用 `populate_existing()` 强制刷新锁后状态；两个真实 HTTP 请求即使都在锁前读到空来源，最终仍只创建一个 source、两个候选都归入该 source，recap 反向链接与 `total_candidates` 保持一致。
- ignored 语义明确为“忽略本次审核”，不是永久忽略该 recap 条目。再次加入时先解除旧 ignored candidate 链接，再通过共享创建服务新建或复用 active pending candidate；旧 ignored 记录保留，不绕过同来源唯一约束。
- 新增 recap 双条目确定性并发回归和 ignored 重加回归。GCP 完整相邻矩阵为 **118 passed, 15 warnings**；recap source、packet adoption、数据库 active-candidate 三条并发路径连续 **5/5**；最终全量为 **660 passed, 16 warnings**。
- GCP migration current/heads 均为单一 `b3c4d5e6f7a8`，Python 编译与 `git diff --check` 通过。strict doctor 非零仍仅因验收机未配置 LLM provider 和 `zh/en/ja/fr` 外置词典；数据库、dispatch、migrate、迁移、密钥和管理员均正常。
- 审查发现的两个正确性问题均已修复，未发现新的合并阻断项。分支仍未合并或部署；下一步仅为明确的 merge/deploy 决策，不得提前开发 observation dashboard。

## 2026-07-31 SessionPad 带语境候选 v1 — SP4 收口

- SP4 已提交为 `18943e1`；功能分支 `feature/sessionpad-context-candidates-v1` 已完成 SP1–SP4，但尚未合并或部署。生产仍为 `master@1be9ddc`，migration head 仍为 `f1a2b3c4d5e6`。
- 收口没有扩张候选领域逻辑；补入复盘编辑器模块切换说明，明确切换分类不会清空草稿。中英文均有回归，重复发送策略继续留在 Backlog。
- 设计文档已将 context-bearing candidate v1 标为实施完成；闭测运维文档补齐两条顺序迁移的重复数据停止条件、单一 head 检查、SessionPad 冒烟矩阵和带迁移回滚边界。
- GCP 完整相邻回归覆盖 packet、recap、candidate、commit、已有词、RLS、并发、AI 降级及阅读候选兼容，结果为 **116 passed, 15 warnings**；两条候选并发路径连续 **5/5**；最终全量仍为 **658 passed, 16 warnings**。
- 1440px 桌面与 390px dark mode 真浏览器复验通过：模块切换草稿保留、说明可见、无横向溢出。SP3 已验证的聚焦候选审核 UI 未改动。
- GCP migration current/heads 均为单一 `b3c4d5e6f7a8`。strict doctor 非零仅因验收机未配置 LLM provider 和 `zh/en/ja/fr` 外置词典；数据库、dispatch、migrate、迁移、密钥和管理员均正常。中英文 **603** 个键对齐、**53** 个模板编译通过，`git diff --check` 通过。
- SessionPad context-bearing candidate v1 已完成开发与分支验收。下一步是整分支只读审查及明确的 merge/deploy 决策；不得直接部署，也不得提前混入 observation dashboard。

## 2026-07-30 SessionPad 带语境候选 v1 — SP3 聚焦审核

- 功能分支仍为 `feature/sessionpad-context-candidates-v1`；SP1 为 `d2ec131`，SP2 为 `d40e30a`。SP3 已提交为 `4c84f46`、尚未合并或部署；生产仍为 `master@1be9ddc`。
- SessionPad 候选审核改为专属单候选队列，保留待审核/已接受/已忽略导航；显示伙伴、交换日期、标题和复盘/反馈包链接，不默认展开反馈正文。
- 候选 term 与 context 可编辑；原文语境保持 `source_quote`，改变后为 `user_edited`，清空显示缺语境。“将语境用作例句”只在浏览器内填入例句草稿，只有显式接受后才保存；commit 不会自动把 context 写成最终例句。
- 已存在词条只关联 `word_id`，不重复建词、不覆盖既有释义；commit 前后出现既有词的竞态均能补链。同来源改名冲突返回友好错误，并由数据库 partial unique index 兜底。
- AI 不可用只作为本次审核页的瞬时提示，不写入候选领域状态。SessionPad 不显示 bulk accept；对抗性复核进一步封闭旧通用 accept/ignore、bulk-accept、commit-all HTTP 入口，避免绕过逐张审核。CSV、文本抽词和阅读候选旧入口保持不变。
- GCP 已通过 107 项扩大相邻回归和新增守卫的 19 项回归；1440px 桌面与 390px dark mode 真浏览器通过，来源条、单卡聚焦、显式语境转例句、接受后推进、缺语境、AI 降级和无横向溢出均验证。最终全量为 **658 passed, 16 warnings**。
- migration 未增加，功能分支仍为单一 head `b3c4d5e6f7a8`。GCP strict doctor 非零仅因测试环境无管理员、LLM provider 和外置词典；数据库、dispatch、migrate、migration 与密钥均正常。下一票是 SP4 收口，不得混入 observation dashboard。
## 2026-07-30 SessionPad 带语境候选 v1 — SP2 候选产生

- 功能分支仍为 `feature/sessionpad-context-candidates-v1`；SP1 已提交为 `d2ec131`，SP2 实现已完成、尚未合并或部署。生产仍为 `master@1be9ddc`，生产 migration head 仍为 `f1a2b3c4d5e6`。
- 新增共享 `sessionpad_candidates` 服务：AI 与人工统一生成最多 8 / 20 个 `term + context`；term 最多 80 字符，context 最多 300 字符。同次输入按 `normalize_word_identity` 合并，保留首个展示写法，首个有效非空语境可补空。
- AI context 只能是当前反馈原文的连续片段，仅允许 Unicode 空白折叠差异；无法定位时置空，不允许生成或改写例句。未改的 AI 片段为 `source_quote`，用户新建或编辑后为 `user_edited`。
- packet 收到反馈与 recap「帮自己记」已接入同一创建服务。新 SessionPad 候选不再写 `source_example`；AI 建议只预填表单，不创建候选，AI 不可用时仍显示人工 term/context 表单。
- 同一来源用行锁串行创建；迁移 `b3c4d5e6f7a8` 增加 active partial unique expression index：同 `source_id + lower(btrim(word))` 在 pending/accepted 中只能有一个，ignored 不阻止重新候选，不同来源可保留同词。迁移前发现历史重复会明确失败，不猜测合并。
- GCP 已完成迁移 downgrade/upgrade 往返，当前单一 head `b3c4d5e6f7a8`；相邻回归 **80 passed**，packet 真实 HTTP 并发连续 **5/5 passed**，最终全量 **644 passed, 16 warnings**。SP2 完成当时 SP3 尚未开始；当前状态见上方 SP3 段。
- GCP `flask doctor --strict` 的非零仅因测试环境无管理员、LLM provider 和外置词典，数据库/dispatch/migrate/迁移/密钥均正常。`flask db check` 仍会报告本票之前已存在的 reading/recap 外键与索引 metadata 漂移；未报告 SP2 新索引缺失，本票不顺手修旧漂移。

## 2026-07-30 SessionPad 带语境候选 v1 — SP1 数据地基

- 功能分支：`feature/sessionpad-context-candidates-v1`，从已部署里程碑 `master@1be9ddc` 创建；生产仍停在 `1be9ddc`，本分支尚未部署。
- 顺序迁移 `a2b3c4d5e6f7` 为 `word_candidates` 增加可空 `context_excerpt` / `context_provenance`；来源只允许 `source_quote`、`user_edited` 或空，语境与来源必须成对，服务层限制 300 字符。
- 不回填历史 `source_example`，不改历史 `definitions`。SessionPad 入库不再用完整伙伴反馈 `source_example` 兜底最终例句；用户明确填写的 `example` 仍正常保存，阅读及其他 intake 来源保持旧规则。
- 用户编辑语境会 trim 并标为 `user_edited`；清空时两字段同时置空；超长编辑在修改候选前失败，原状态与数据保持不变。
- GCP PostgreSQL 验收：迁移实际 downgrade/upgrade 往返成功，单一 head `a2b3c4d5e6f7`；相邻边界 **73 passed**，全量 **627 passed, 16 warnings**，`git diff --check` 通过。测试曾抓出 PostgreSQL CHECK 对 `NULL` 的三值逻辑漏口，已用显式 `context_provenance IS NOT NULL` 修正并回归。
- SP1 本身没有路由、模板或 UI 改动；后续 SP2 状态见上节，SP3 仍不得提前混入本数据地基。

## 2026-07-30 Review Story 部分队列硬修复

- 闭测真实使用暴露：用户当天已复习足量词，但只要仍有其他到期词，故事回执就不会出现；到期词多时等同于功能长期不可达。
- 修复分支：`fix/review-story-partial-queue`。资格统一为按用户本地日和当前语言累计不同词：少于 10 个始终静默；达到 10 个后，`模糊 + 遗忘`不同词超过 5 个为 strong，否则 normal。strong 不再绕过 10 词下限。
- 回执现在可与当前到期词卡同时显示，用户可以继续复习；AI 仍只在显式点击后调用，不把故事变成复习门禁，也不要求清空到期队列。
- 实现未新增迁移或会话表；缓存仍绑定服务端选择的目标词快照与 input hash。
- GCP 验收：Review Story 相邻边界 **151 passed**，全量 **621 passed, 16 warnings**；JSON、Python 编译与 `git diff --check` 通过。
- 修复提交 `2f09304` 已于 2026-07-30 纯快进合并到本地 `master` 并部署闭测生产。部署前代码/数据库备份分别为
  `rememate-code-before-review-story-hotfix-20260730-1105.tgz` 和
  `rememate-db-before-review-story-hotfix-20260730-1105.dump`；生产 strict doctor、服务重启、内外网 200 与新日志检查均通过。
  部署前后计数一致：用户 6、词条 160、输出 1、伙伴 5、复盘 6、故事运行 0。真实账号已通过“仍有到期词时达到门槛并出现故事入口”的部分队列复验。

## 2026-07-30 Review Story 闭测部署状态

- 当前权威仓库：`D:\home\RemeMate`；当前分支：`master`。
- Review Story v1 已通过 `a7fcf91` 合并进本地 `master`，并于 2026-07-30 连同恢复后的六项
  安全/数据可信度修复部署到闭测生产；部署前本地文档状态为 `ce79a74`。
- 已完成并提交：
  - RS1 数据/RLS/日内摘要地基：`222d7c0`，PostgreSQL 验收补强为 `f0d90e8`、`c761902`；
  - RS2-A 多语言生成契约：`c07ff42`；
  - RS2-B 事务状态机：`e6f926e`，包含 pending lease、唯一输入并发、两次逻辑尝试、
    ready cache、attempt version 防旧 worker 覆盖及跨用户 RLS；
  - RS2-C provider 编排、token 记账与无正文漏斗事件：`e800ef0`。只有拿到 generation lease
    才调用一次 provider；缓存、pending 和已有失败不调用 AI，观测或记账失败不重开生成。
- RS2-B 的 GCP 复验已全绿。曾出现的第五次并发失败来自裸 `app_context` 把 session 级 GUC
  留在连接池中的错误测试模型；并发测试已改走真实 `request_context + after_begin` RLS 注入路径，
  生产状态机没有因此修改。
- RS2-C GCP 验收：定向 **52 passed**，state claim 与 orchestration/provider-once 两条并发路径
  各连续 **5/5 passed**，全量 **607 passed, 16 warnings**；migration 单一 head
  `f1a2b3c4d5e6`。测试机缺 LLM provider 与 `zh/en/ja/fr` 词典使 strict doctor 非 0，
  DB/dispatch/migrate/keys/admin 均 OK，此环境例外不视为生产发布闸门通过。
- 当前迁移 head：`f1a2b3c4d5e6`，单一 head。
- **RS3 第一张小票“复习完成回执与按需生成”已完成并提交：`4937253`。**
  - 首页和兼容 `/review` 的完成态共用同一独立回执；silent 日完全不渲染，normal/strong
    只展示各自说明与生成按钮。
  - 只有用户点击 HTMX POST 后才调用 RS2-C 编排；ready/cached/error/pending 都返回到回执内部，
    不改变复习完成卡和“回到词库”入口。
  - 本票的公开测试边界是完成态 HTTP 响应与生成 POST；不接 `/write`，不记录 writing handoff
    或 output saved，不增加故事历史、发布、图片或第二编辑器。
  - GCP 验收：定向 **81 passed**，全量 **613 passed, 16 warnings**；桌面 1440px 与移动端
    390px dark mode 真浏览器通过，页面加载不自动调用 AI，重复点击命中缓存，失败留在回执内部。
    migration 保持单一 head `f1a2b3c4d5e6`；strict doctor 非 0 仅因测试机缺 LLM/词典。
- **RS3 第二张小票“从复习故事显式交接到现有写作页”已完成并提交：`132fca2`。**
  - ready/cached 回执中的目标词按钮只提交 `story_run_id + term_key`；服务端重新校验当前用户、
    ready 状态、有效期、目标语言和词条所有权，URL、session 与 OutputEntry 均不携带故事正文。
  - 进入 `/write` 后使用用户明确点击的目标词，输入框保持为空；批改不保存，只有显式保存成功后
    才记录 `story_output_saved`。重复保存不重复创建 OutputEntry 或事件，观测事件异常不阻断交接
    与业务保存。
  - GCP 验收：定向 **93 passed**，全量 **618 passed, 16 warnings**；桌面 1440px 与移动端
    390px dark mode 真浏览器通过，无横向溢出。migration 保持单一 head `f1a2b3c4d5e6`，
    `git diff --check` 通过；strict doctor 非 0 仍仅因测试机缺 LLM/词典。
- **RS3 已完成。** 仍不增加故事历史、发布、图片或第二编辑器；这些不是本阶段的隐含尾项。
- **RS4 收尾已完成并提交：`bf1ee9b`。**
  - `flask cleanup-review-stories` 默认 dry-run；只有显式 `--apply` 才通过 dispatch/BYPASSRLS
    删除过期缓存。ready 正文及 failed/pending 私有输入快照保留 7 天，无正文漏斗事件保留 180 天。
  - GCP 验收：定向 **67 passed**，全量 **620 passed, 16 warnings**；两用户真实清理得到
    `dry-run 4/2 → apply 4/2 → dry-run 0/0`，新鲜缓存和 180 天内事件保留。migration 仍为单一
    head `f1a2b3c4d5e6`，`git diff --check` 通过；strict doctor 非 0 仅因测试机缺 LLM/词典。
  - RS4 未修改 UI、路由、模板、CSS 或翻译文件；RS3 已验收的 1440px/390px 浏览器代码字节未变，
    因此不要求重复截图。中英文 582 个键对齐、51 个模板本地编译通过。
- **整分支只读审查后的合并前修复已完成并提交：`4825336`。**
  - 修复 Review Story 写作交接会持久修改 `current_language`、并可能扩写 `learning_languages`
    的多语言状态污染；写作页和提交现在只在本次交接中使用故事目标语言，用户全局语言偏好保持不变。
  - 同一修复消除了用户在交接后切换全局语言时，提交阶段拿错语言导致批改不匹配的边界。
  - 补充多语言回归测试，并收紧 cleanup 对“`content_expires_at` 尚未到期但 `updated_at`
    已很旧”的保留测试。GCP 定向 **63 passed**，全量 **621 passed, 16 warnings**；
    migration current/heads 均为单一 `f1a2b3c4d5e6`，`git diff --check` 通过。
  - strict doctor 非 0 仍只因 GCP 未配置 LLM provider 和 `zh/en/ja/fr` 外置词典；数据库、
    dispatch、迁移、密钥和管理员检查均通过。
  - 审查中的日内 summary 重复聚合和全局 cleanup 扫描是后续规模化观察项，不是当前硬 bug，
    本轮未借机改动缓存或清理架构。
- **Review Story v1 已完成整分支审查、合并并部署闭测生产。**
  - 部署前代码备份：
    `/home/ubuntu/rememate-backups/rememate-code-before-review-story-20260730-071534.tgz`
    （SHA-256 `fa0be2fc1b3d8961321f15a47d3c81704c26ad48c5ab701b8096b7c48c505749`）。
  - 部署前数据库备份：
    `/home/ubuntu/rememate-backups/rememate-db-before-review-story-20260730-071534.dump`
    （SHA-256 `902356f29511d2812db493f177e3f66bfd36facd9cc8623c329ab0c486c267df`）。
  - 生产迁移从 `c8d9e0f1a2b3` 升至单一 head `f1a2b3c4d5e6`；迁移前规范化重复词组为 0。
  - 生产 `flask doctor --strict` 全绿，`rememate.service` 重启正常，公网首页与 `/healthz`
    均返回 200，journal 未见新错误。
  - 部署前后数据计数一致：用户 6、词条 160、输出 1、伙伴 5、复盘 6；新故事表初始为空。
  - 自动化与发布闸门已通过；仍需用真实闭测账号完成一次“复习达阈值 → 生成故事 → 选词写作 →
    批改保存”的最终人测，确认生产 provider 真实回路。
  - 人测通过后，下一条功能分支是 SessionPad context-bearing candidate v1。
- 工作区另有 `docs/README.md` 修改，以及 `.reme/`、`NUL`、`_hexdump_keys.js`、
  `_hexdump_kitty.js`、`docs/arch/review-2026-07-26-dead-code-and-refactor-audit.md` 未跟踪内容，
  均与本票无关，不得加入 Review Story 收口提交。

## 2026-07-22 丢盘恢复闸门

- WSL2 虚拟磁盘已丢失且不再做磁盘恢复。本地项目从闭测云机恢复到 `D:\home\RemeMate`；
  云机代码 `1b72128` 是恢复基线，线上用户数据、`.env`、`.venv` 和词典目录均未复制或覆盖。
- 本地 `master` 在生产基线之后重放了六项安全/数据可信度修复，并已于 2026-07-30 部署：
  - `26f481a`：`output_entries.word_id` 所有权 RLS，迁移 `d9e0f1a2b3c4`；
  - `994362a`：广场 NSFW 审核与批改 failover 分离，审核不可用时公开 fail-closed；
  - `637cd93`：已接受邀请但未建立反向资料时，伙伴页持续显示待确认关系；
  - `5a27f78`：同语言手动加词顺序幂等，保留首条词形、释义和 SRS 状态；
  - `b88ba88`：同词表规范化词条数据库唯一，手动并发/编辑冲突/候选批量保存点兜底，
    迁移 `e0f1a2b3c4d5`；
  - `e410753`：Web 与 Bark 对同一当前到期状态最多评分一次，重放与延迟请求不再重复推进 SRS。
- 当前本地迁移 head：`e0f1a2b3c4d5`。迁移遇到历史规范化重复词时会中止并只报告重复组数量，
  不自动合并用户数据。
- **GCP Ubuntu 独立验收已完成（2026-07-22）**：用户态 PostgreSQL 16.14 + 三角色 +
  `rememate_test`，migration 两边到 `e0f1a2b3c4d5`。Gate4 资源充足全量
  **`486 passed, 16 warnings`（`FULL_RC=0`）**；定向六项相关 **122 passed**。
  唯一曾失败的集成断言是测试 SQL `AmbiguousColumn`（`tests/integration/test_words.py`
  已改为 `w.word, w.id`，未改业务代码）。`flask doctor --strict`：DB/迁移/admin OK，
  测试机无 LLM/词典仍 WARN → 非 0。完整过程见
  `docs/recovery-validation-2026-07-22.md`。
- **pytest 行为闸门已绿**。严格“含 doctor strict 全绿”仍差测试机 LLM/词典配置。
  开 `feature/review-story-v1` 前：接受测试机 doctor WARN，或补配置后再 strict；
  仍须用户明确启动分支。生产部署前另跑目标环境 `pytest -q` +
  `flask doctor --strict`（生产有 admin/LLM/词典）。
- `origin` 直接指向生产工作仓库；普通开发仍不得直接推送。上述六项修复与 Review Story 已按
  `docs/deploy-closed-beta.md` 的备份、迁移、doctor、重启和冒烟流程部署。

## 2026-07-22 Wayfinder 规划恢复

- 已恢复完整的 2026-07-19 下一阶段路线图：
  `docs/wayfinder/2026-07-19-next-stage-roadmap/MAP.md`；恢复来源和原型资产边界见同目录
  `RECOVERY.md`。
- 本次只恢复规划文档和历史短故事原型，不代表短故事、SessionPad 带语境候选或观察面板已实现、
  测试或部署。
- 串行顺序已经定稿：先验证并发布六项可信基线；再做 review story；随后做 SessionPad context
  candidates；最后做隐私安全的管理员观察面板。
- 短故事采用完成卡下方的可选独立复习回执。第一张代码票 RS1 只做 schema、FORCE RLS、日内摘要、
  确定性选词与测试，不调用 AI、不开发 UI。
- SessionPad 后续分离不可变交换来源、可编辑候选语境和最终例句，并采用单候选聚焦审核；语境只有
  经用户明确操作才能成为例句。
- Wayfinder 已完成且无开放规划票。pytest 恢复闸门已绿；仍须用户明确启动后，才能创建
  `feature/review-story-v1`（见上方恢复闸门与 `docs/recovery-validation-2026-07-22.md`）。

下面的“当前状态”是 2026-07-15 云机里程碑基线，保留用于说明当时闭测版具备的功能；最新生产
状态以上方 2026-07-30 部署记录为准。

> 轻量交接页。历史过程已移到 `docs/PROGRESS.md`，完整旧文档见
> `docs/archive/HANDOFF.full-2026-07-08.md`。软 bug / 延后事项统一进
> `docs/BACKLOG.md`。

## 当前状态

- 日期：2026-07-15
- 当前分支：`master`。测试基线修复与「阅读收词小优化 v1」均已提交并部署，工作树干净。
- `navigation-ia-mobile`、`i18n-foundation`、SessionPad、Bark、Landing 与词库/解释语言小修均已合入 `master`；
 现有本地分支全部已被 `master` 包含。两个附加 worktree（`backlog-vocab-language-polish`、
  `landing-public-home`）干净，但尚未清理。
- 本地数据库迁移：`c8d9e0f1a2b3 (head)`；`flask doctor --strict` 于 2026-07-15 全部 OK。
- 最近完整绿线：`457 passed, 16 warnings`（2026-07-15）；阅读收词相关定向回归
  为 `76 passed, 15 warnings`，新增 v1 回归为 `8 passed`。
- **测试基线已恢复**：原始 `314 passed, 129 failed, 11 errors` 的首个错误是
  `tests/conftest.py::_wipe` 删除 `users` 时被残留 `user_quota` 外键拦截，导致后续连锁失败。
  `_wipe` 现在仅在数据库完整性错误后以逐用户 GUC 方式重试清理，并有 3 个定向回归测试覆盖
  基础清理、双用户清理和 FK 回退路径。`rememate_dispatch` 在测试库中已核验具备 `BYPASSRLS`；
  不把问题归因于缺权限。
- **阅读收词小优化 v1 已完成并部署**：阅读器加入候选后继续停留原页，显示本篇候选词和
  轻量审核入口；候选审核与词库详情显示阅读文档名和 PDF 原句，非阅读来源不误标。删除阅读文档后
  以文件名回退；再次加入已忽略候选会恢复为待审核。来源查询保持用户隔离并以单次查询加载。
- 线上部署：`ubuntu@43.156.210.229:/srv/rememate`，服务为 `rememate.service`，gunicorn 监听
  `127.0.0.1:8891`。2026-07-15 已部署 `9ef23b8`，迁移为 `c8d9e0f1a2b3 (head)`；严格 doctor、
  服务健康检查和公网 HTTPS 首页均通过。线上工作树仅有部署前已存在的未跟踪
  `admin-initial-login.txt`。
- 线上词典：`/srv/rememate-data/dictionaries`，`zh/en/ja/fr` present。

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

三个月第一性目标：证明用户会因为“自己真实遇到的词和句子被 RemeMate 帮他记住并用出来”，而每天回来。详见 `docs/strategy/2026-07-09-three-month-focus.md`。

1. 闭测观察：SessionPad 已完成真实双人闭环测试；线上继续只修硬 bug，软反馈进入 BACKLOG。
2. 阅读收词小优化 v1 已完成，进入真机闭测观察；继续保持「阅读收词入口」定位，不扩成专业阅读器。
3. SessionPad 后续仅按闭测证据成批处理：模块切换说明、重复发送策略等已有 BACKLOG；
   不做 guest、聊天室或实时协作。
4. Bark 能力已完成闭环：保存、测试推送、到期词提醒、签名链接打开三按钮评分回流均已在 `master`。
5. 公开门面：未登录访问 `/` 显示中英双语 Landing，登录用户仍直接进入复习首页；登录页同步双语切换。
6. 导航信息架构已完成：桌面一级导航为首页、写一写、语言伙伴、词库、我的；
   造句/历史/广场成为写作域同级视图，收到的反馈归入伙伴域；移动端使用固定底部五图标导航，
   品牌与语言/主题控件保持在同一顶栏。
7. 全站国际化已完成：`i18n-foundation` 建立独立 `ui_locale`、服务端翻译目录和全局切换路由；
   第一批覆盖导航、登录、首页复习/每日任务和设置；第二批覆盖造句、三行日记、
   AI/HTMX 状态、历史和广场；第三批覆盖生词本、词条详情/编辑、手动加词、
   文本抽词、CSV 导入和候选词审核；第四批覆盖伙伴列表、邀请与双向确认、复盘信纸、
   AI 总结、反馈包、感谢和候选词采纳；第五批覆盖阅读收词、阅读器、管理页、独立复习页和
   Bark 回流卡。全站模板与路由漏译审计已完成，Landing 保留自身明确的中英双语切换，详见
   `docs/strategy/2026-07-12-app-i18n.md`。

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
- Bark 回流链接：`/bark/review/<token>` 免登录打开单词三按钮页。token 由
  `app/services/review_links.py` 用 `SECRET_KEY` HMAC 签名，包含 `user_id + word_id + exp`；
  路由用 `DISPATCH_DATABASE_URL` 读取/评分这一张卡，并用 `push_log` 防止同一链接重复评分。
  生产需设置 `PUBLIC_BASE_URL=https://rememate.com`，否则通知不会带可点击回流链接。
- SessionPad B1 使用 `language_partners` 表；记录只属于创建者，服务层所有查询显式传
  `user_id`，数据库启用 FORCE RLS。后续 B4-B12 已建立账号绑定、不可变反馈包、一次性感谢、
  接收方私有候选词采纳与 AI 辅助摘要；当前产品以双人、非实时的语言交换复盘为边界。
- SessionPad B2 使用 `partner_recaps` + `partner_recap_items`；信纸和条目同样 FORCE RLS，
  复合外键把 owner 贯穿伙伴、信纸、条目。`private_note` 只允许 `for_me`，`correction`
  只允许 `for_partner`。B3 通过 `intake_source_id` + `candidate_id` 接到现有候选词管道；
  只有 `for_me` 的 `expression` / `natural_phrase` 可加入，复盘仍是作者私有草稿，
  没有任何发送行为。B4 在 `language_partners` 增加 `linked_user_id` 和待确认令牌哈希；邀请令牌
  绑定目标邮箱指纹，确认跨越两个用户边界时只允许 `partner_invites` 服务通过 BYPASSRLS 事务
  更新这一条关系。迁移 head 为 `6d2e3f4a5b7c`。
  B5 使用 `partner_packets` + `partner_packet_items`；包只允许绑定关系中的发送者创建，发送者和
  接收者可读但都不能修改/删除。包保存标题、日期、双方显示名和条目正文快照，不向接收方开放
  原始复盘。迁移 head 为 `7e3f4a5b6c8d`。
  B6 使用独立 `partner_packet_thanks` 表保存一次性感谢；复合外键确保感谢者就是包接收方，
  FORCE RLS 允许双方查看、只允许接收方创建，不提供更新或删除策略。当前迁移 head 为
  `8f4a5b6c7d9e`。
  B7 在反馈包上固化 `language_code`，并使用 `partner_packet_intakes` +
  `partner_packet_item_adoptions` 保存接收方私有的候选词来源和采纳链接；发送者受 RLS 隔离，
  看不到对方是否采纳。当前迁移 head 为 `9a5b6c7d8e0f`。

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
32. GCP 验收机公网直连应用端口常被 VPC 防火墙挡住（即使 Console 已建规则）；真机测优先
    Cloudflare quick tunnel / localhost.run 或 SSH -L，详见
    `docs/recovery-validation-2026-07-22.md` §16。
33. 1GB 验收机跑全量前：停 Hermes（系统级 unit `Restart=always`，只 pkill 不够）、
    停 gunicorn/隧道，`max_connections` 勿过低（20 会连接槽假失败；验收用 100），
    建议 1.5G swap。
34. RLS 下测试 SQL join 多表必须表别名限定列（如 `w.id`），否则 `AmbiguousColumn`。

## Backlog 规则

- `docs/BACKLOG.md` 是唯一待办池。
- 已修复项不要继续留在 BACKLOG；用 git 历史和 `docs/PROGRESS.md` 查。
- 闭测软反馈先写 BACKLOG，不马上开工。
- 硬 bug 可以直接修，但修前仍要判断最小测试集。
