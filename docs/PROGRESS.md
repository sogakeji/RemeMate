# RemeMate Progress Log

> 历史过程从 `HANDOFF.md` 移出到这里；完整旧交接原文保存在
> `docs/archive/HANDOFF.full-2026-07-08.md`。

## 里程碑

### 2026-06-28：Backlog 七项收口
- 本地化 htmx，修复 stats 时区、words N+1、lapse 冷却体验等基础问题。
- 迁移脚本可重入，补齐多项 RLS / migration 经验。

### 2026-06-29 ~ 2026-06-30：UI 职责纠偏
- 明确 UI 不是单纯换皮，先做页面职责收口。
- 词表概念转为隐式：用户只感知语言，不管理词表。

### 2026-07-03：句子广场 MVP 与闭测准备
- 做过句子广场、三行日记、管理员建号、设置页等闭测能力。
- 后续判断：广场不是闭测第一优先级，保留思路但主线先聚焦词库/复习/造句/阅读收词。

### 2026-07-04 ~ 2026-07-07：Lute-style 阅读收词分支
- 增加 PDF 阅读、查词弹卡、阅读候选词、CJK 选词修复、拼音/假名标注。
- 产品定位从“专业阅读器”收敛为“词库下的阅读收词”。
- 候选词系统与每日任务卡 v1 完成。

### 2026-07-08：合并与闭测部署基线
- `lute-reading-mvp-design` 合并进 `master`。
- 清理分支，仅保留 `master`。
- 部署到云机 `/srv/rememate`，数据库迁移到 `2e79a6ececcc`。
- 线上 `flask doctor --strict` 全 OK，阅读词典数据部署到 `/srv/rememate-data/dictionaries`。

### 2026-07-10：Bark 回流与 SessionPad B1
- Bark 补齐到期词提醒，以及签名链接打开单词三按钮并回流 SRS 熟练度。
- SessionPad 开始特色验证，第一切片只实现私有语言伙伴档案的创建、列表、详情与编辑。
- `language_partners` 启用 FORCE RLS；账号绑定、复盘信纸、反馈包和 AI 均留在后续切片。

### 2026-07-10：SessionPad B2 复盘信纸
- 围绕一位语言伙伴创建带日期和可选标题的私有复盘信纸。
- 两栏保存结构化条目：`帮自己记` / `帮他记`，支持新增、修改和删除。
- UI 不同时平铺两个大栏：先切换记录对象，再用左侧模块按钮驱动右侧大输入区；提交后保留当前侧和模块。
- 私人伙伴笔记只能进入帮自己记，错误修正只能进入帮他记；尚无发送或共享行为。
- `partner_recaps` 与 `partner_recap_items` 启用 FORCE RLS 和复合所有权外键。

### 2026-07-10：SessionPad B3 接入候选词
- 「帮自己记」中的表达和自然说法可主动加入现有候选词审核，不调用 AI。
- 同一条记录幂等加入；私人笔记、下次话题和「帮他记」内容不进入自己的词库。
- 每张复盘复用一个 `sessionpad` intake source，首次加入时固化目标语言。
- `partner_recaps.intake_source_id` 与 `partner_recap_items.candidate_id` 使用同用户复合外键，
  防止跨用户串接来源或候选词。

### 2026-07-10：SessionPad B4 伙伴确认绑定
- 伙伴所有者可以为指定登录邮箱生成 7 天邀请链接，对方登录后主动确认绑定。
- 链接只携带邮箱指纹和签名，不暴露邮箱，也不在生成时查询账号是否存在。
- 每位伙伴只有最新邀请有效；新链接覆盖旧令牌哈希，确认后立即清除。
- 数据库拒绝自绑定和同一用户重复绑定；接收方确认后仍无法查看所有者的历史复盘和私人内容。
- 本片只建立未来反馈包的可靠收件关系，不提前实现反馈包或消息系统。

### 2026-07-11：SessionPad B5 反馈包快照投递
- 发送者从单次复盘的「帮他记」中逐条选择，向已绑定账号发送不可变反馈包。
- 包固定双方显示名、交换日期、标题和条目正文；原记录修改或删除不影响已发送内容。
- 完全相同的重复提交幂等返回原包；数据库复合外键阻止向非绑定账号或错误复盘投递。
- 接收方从「我的 → 收到的反馈」查看列表和详情，仍无法访问发送者的原复盘与私人内容。
- 包和条目启用 FORCE RLS，发送者/接收者只读；感谢和采纳留给后续切片。

### 2026-07-11：SessionPad B6 一次性感谢
- 反馈包接收方可点击一次「感谢对方」，发送者在同一包中看到「对方已感谢」。
- 感谢使用独立记录，不修改反馈包；重复点击幂等且无法撤回或改写。
- 复合外键和 FORCE RLS 保证只有真实接收方能创建，双方可见、第三人不可见。
- 没有引入已读、忽略、评论、回复或通知状态。

### 2026-07-11：SessionPad B7 接收内容采纳
- 反馈包发送时固化伙伴正在学习的语言，后续资料修改不影响候选词去向。
- 接收方可先把表达、自然说法或修正整理为想记住的词，再进入自己的候选词审核。
- 每包复用一个接收方私有 intake source，完整反馈正文作为候选词来源上下文保留。
- 同一条采纳幂等；下次建议不入库，AI 不参与拆词或保存。
- 采纳映射启用 FORCE RLS，仅接收方可见，发送者看不到采纳状态。

### 2026-07-12：全站国际化前三批
- 建立独立于学习语言和反馈语言的 `ui_locale`，服务端 JSON 词典与全局界面语言切换。
- 第一批覆盖导航、登录、首页复习、每日任务和设置；第二批覆盖写作、三行日记、
  AI/HTMX 状态、历史和广场。
- 第三批覆盖生词本、词条详情/编辑、手动加词、文本抽词、CSV 导入、处理状态和候选词审核。
- 英文手动加词的语言下拉按界面语言显示；中英文目录保持键集合一致。
- 桌面和移动端完成视觉检查；全量回归为 435 passed, 16 warnings，`flask doctor --strict` 通过。

### 2026-07-12：语言伙伴闭环国际化
- 第四批覆盖伙伴列表与编辑、账号邀请与双向确认、两栏复盘信纸、AI 会后总结、
  反馈包收发、一次性感谢和候选词采纳。
- 复盘类型与提示在路由适配层本地化，服务层和数据库领域值保持不变。
- 服务层中文校验错误由伙伴路由映射为界面语言，避免英文流程只在失败时退回中文。
- 桌面和 390px 移动端无横向溢出；全量回归为 438 passed, 16 warnings，
  `flask doctor --strict` 通过。

### 2026-07-12：阅读、管理与全站漏译收口
- 第五批覆盖阅读书架、PDF 上传、阅读器工具栏、查词卡、候选状态和管理员账号页面。
- 全站审计补齐独立复习页、Bark 免登录回流卡、首页标题和非法学习语言提示。
- Landing 的 `data-zh`/`data-en` 是自身明确的公开双语切换，不作为漏译清理。
- 阅读/管理相关回归 85 passed；最终全量回归 442 passed, 16 warnings，
  `flask doctor --strict` 通过。

### 2026-07-11：导航信息架构收口
- 桌面一级导航重组为首页、写一写、语言伙伴、词库、我的。
- 造句、三行日记、历史与广场归入写作域；语言伙伴独立于“我的”。
- 移动端改为固定底部五图标导航，顶栏保留品牌、学习语言与主题控制。

### 2026-07-13：国际化并入主线与闭测小批校准
- 全站国际化合入 `master`（`5a21fd5`），应用界面语言与学习语言、解释语言保持独立。
- Landing 文案按当前产品事实校准；未改截图或重做 Landing 布局。
- 生词本增加星标筛选并保持搜索/排序组合；CSV 说明与真实支持的表头映射对齐。
- 三行日记题目、手动加词 AI 填充/例句/笔记均确认走用户设置的解释语言；真机四项重点验证通过。
- CSV 星标列尚未实际写入词条，已单列入 BACKLOG，不在帮助文案中承诺。

### 2026-07-14：状态核验
- `master` 当前代码基线为 `d06de34`；本轮测试修复与状态文档尚未提交。所有保留分支已并入主线，
  两个历史 worktree 仍保留但干净。
- 线上仍为 `5a21fd5`，迁移 `c8d9e0f1a2b3`；本地 Landing 校准与词库小修尚未部署。
- 本地 `flask doctor --strict` 全 OK。当天首次完整测试在 `rememate_test` 清库阶段因
  `user_quota` 外键残留而失效（314 passed, 129 failed, 11 errors）。修复 `_wipe` 的
  完整性错误回退与定向覆盖后，连续两轮全量为 448 passed, 16 warnings；最终回归为
  **449 passed, 16 warnings**。`rememate_dispatch` 已确认具备 BYPASSRLS，故不把原因误记为角色缺权。

### 2026-07-15：阅读收词小优化 v1
- 阅读器通过 AJAX 加入候选后继续停留原页，侧栏持久展示本篇已有候选、明确成功状态和轻量审核入口；
  重复加入保持幂等，已忽略候选再次加入会恢复为待审核。
- 阅读候选审核和词库详情显示文档标题与 PDF 原句；阅读文档删除后以原文件名回退，非阅读来源不误标。
- 词库详情通过显式 `user_id` 约束的一次查询取回来源；来源原句不再与普通例句重复显示，用户笔记不做
  字符串清洗或改写。
- 新增 8 个回归测试，覆盖 AJAX 去向、幂等/恢复、来源回退、非阅读缺省、中英界面、跨用户隔离和
  完整详情请求的查询次数。定向回归 `76 passed, 15 warnings`；最终全量
  **457 passed, 16 warnings**，`git diff --check` 与 `flask doctor --strict` 均通过。
- 本轮改动已部署到闭测服务器；部署前完成代码与 PostgreSQL 备份，线上迁移仍为
  `c8d9e0f1a2b3`。严格 doctor、服务健康检查和公网 HTTPS 首页均通过；没有生产数据覆盖。

## 当前 Git

- 主线：`master`；测试基线修复与阅读收词 v1 已提交（2026-07-15）。
- 分支状态：所有本地功能分支均已并入 `master`；`backlog-vocab-language-polish` 与
  `landing-public-home` 仅保留为干净的附加 worktree。主工作树干净。
- 代码规模：约 27,705 行（当前已跟踪 Python/HTML/CSS/JS）。
- 最近完整绿线：457 passed, 16 warnings。
- 当前验证状态：`flask doctor --strict` 通过；2026-07-15 阅读收词 v1 定向 76 passed，
  全量 457 passed。

## 过程归档

- 完整旧 HANDOFF：`docs/archive/HANDOFF.full-2026-07-08.md`
- 当前交接入口：`docs/HANDOFF.md`
- 统一待办池：`docs/BACKLOG.md`
- 每日任务卡：`docs/daily-task-card.md`

### 2026-07-22：丢盘恢复与六项本地修复重放

- WSL2 虚拟磁盘丢失后，放弃块设备恢复，从闭测云机 `1b72128` 恢复代码到
  `D:\home\RemeMate`；未复制或覆盖生产数据库、环境变量、虚拟环境和词典数据。
- 在 `recovery/replay-six-fixes` 重建六个独立提交：输出记录词条所有权 RLS、独立 NSFW 审核、
  可恢复的双向伙伴确认、顺序词条幂等、数据库规范化唯一约束、Web/Bark 复习评分幂等。
- 新迁移链为 `d9e0f1a2b3c4 -> e0f1a2b3c4d5`；迁移不自动合并重复用户词条。
- 语法/JSON/迁移 head/空白检查通过；17 个可离线单元测试通过。恢复机尚无 PostgreSQL，
  所有数据库集成与全量测试均明确待跑，六项修复尚未部署。
- 六项代码修复最新提交为 `e410753`，随后已 fast-forward 到本地 `master`。旧“当前 Git”段落
  属于 2026-07-15 基线；完成数据库验证前不部署，也不向直接连接生产工作仓库的 `origin` 推送。

### 2026-07-22：Wayfinder 路线图与 UI 决议恢复

- 从 Codex 任务历史、Markdown staging、补丁和静态原型恢复 2026-07-19 下一阶段 Wayfinder。
- 恢复 11 份正式决议：短故事触发/数据/评分幂等/独立回执/多语言生成契约，SessionPad 语境模型与
  聚焦候选审核，以及隐私安全观察合同和最终实施路线。
- 短故事原型字节副本作为历史审计资产保留；SessionPad 一次性候选原型曾按决议删除，只恢复完整
  UI 状态与选择契约，不伪造 HTML。
- Wayfinder 已完成，无开放规划票；恢复没有修改任何生产代码、模型或迁移。
- 未来仍先满足六项安全修复的数据库验证闸门，再串行 review story、SessionPad context candidates、
  closed-beta observation，避免迁移分叉。

### 2026-07-23 ~ 2026-07-26：Review Story RS1 至 RS2-C

- 从恢复后干净 `master` 创建 `feature/review-story-v1`。
- RS1 建立 `review_story_runs`、`learning_funnel_events`、FORCE RLS、日内摘要、确定性 3–5 词
  快照与 input hash；迁移 head 为 `f1a2b3c4d5e6`。
- RS2-A 完成 `review_story_v1` provider-safe 输入、固定双语 JSON、自然词形锚点、文字系统守卫、
  稳定错误码和单次 provider 尝试，不产生数据库副作用。
- RS2-B 完成事务状态机：首次 claim、60 秒租约、同输入并发唯一、ready cache、一次主动重试、
  租约接管和 attempt version 防陈旧回写。
- GCP PostgreSQL 验收全绿。并发复验曾暴露测试夹具把 session 级 RLS GUC 绑定到池连接的问题；
  测试改为 request context 后稳定通过，生产状态机未因此改动。
- RS2-B 提交为 `e6f926e`。
- RS2-C 串联 claim、单次 provider attempt、complete、ready cache、实际 token 记账和
  `learning_funnel_events` 无正文幂等事件；观测/记账失败只降级，不改变已完成状态或重复调用 AI。
- RS2-C GCP 验收定向 52 passed，两条并发路径各连续 5/5，全量
  **607 passed, 16 warnings**；单一 migration head `f1a2b3c4d5e6`。strict doctor 仅因测试机
  未配置 provider/词典非 0，数据库与迁移项均 OK。
- RS2-C 提交为 `e800ef0`；下一阶段为 RS3 复习回执与安全写作交接，尚无路由/UI。
### 2026-07-30：Review Story v1 合并与闭测部署

- Review Story v1 完成 RS1 至 RS4、整分支只读审查与多语言写作交接修复；GCP 最终全量
  **621 passed, 16 warnings**，migration 保持单一 head `f1a2b3c4d5e6`。
- 功能分支由 `a7fcf91` 合并到本地 `master`，部署前文档状态为 `ce79a74`。
- 部署前创建并校验代码与数据库备份：
  - `/home/ubuntu/rememate-backups/rememate-code-before-review-story-20260730-071534.tgz`
  - `/home/ubuntu/rememate-backups/rememate-db-before-review-story-20260730-071534.dump`
- 通过 Git bundle 将生产从 `1b72128` fast-forward 到恢复修复与 Review Story 版本；未覆盖
  `.env`、`.venv`、生产数据库、词典目录或既有 `admin-initial-login.txt`。
- 生产迁移由 `c8d9e0f1a2b3` 升至 `f1a2b3c4d5e6`；升级前重复词组检查为 0。
  `flask doctor --strict`、服务重启、日志检查、公网首页与 `/healthz` 均通过。
- 部署前后用户与核心业务数据计数保持一致：用户 6、词条 160、输出 1、伙伴 5、复盘 6；
  新增故事运行与漏斗事件表初始为空。
- 发布自动化闸门完成。仍待闭测账号进行一次真实 provider 的“复习达阈值 → 生成故事 →
  选词写作 → 批改保存”人测；通过后进入 SessionPad context-bearing candidate v1。
### 2026-07-30：Review Story 部分队列可达性硬修复

- 闭测用户在 100+ 到期词中复习 20 个、遗忘 5 个后仍看不到故事，确认根因为路由和模板把回执绑定到“当前无到期词”。
- 产品资格重新明确：当天同语言累计至少复习 10 个不同词；模糊或遗忘的不同词合计超过 5 个为 strong，否则 normal；少于 10 个始终 silent。
- `fix/review-story-partial-queue` 让回执可与当前到期词卡同时存在，继续保持显式点击才调用 AI、服务端选词、缓存和写作交接边界。
- GCP 定向 151 passed、全量 **621 passed, 16 warnings**；无迁移。
- 修复提交 `2f09304` 已纯快进合并到本地 `master` 并部署闭测生产。部署前完成代码与 PostgreSQL
  备份；strict doctor、服务重启、内外网 200、日志与核心数据计数核验均通过。真实账号部分队列
  场景复验通过，Review Story v1 本轮硬修复正式收口。

### 2026-07-30：SessionPad 带语境候选 SP1

- 从已部署 `master@1be9ddc` 创建 `feature/sessionpad-context-candidates-v1`，生产未变。
- `word_candidates` 新增可空候选语境与来源字段，迁移 head 顺序推进到 `a2b3c4d5e6f7`；不回填历史数据。
- SessionPad 完整伙伴反馈不再自动写入最终例句；显式例句仍保存，阅读及其他 intake 来源不回归。
- 服务层完成 trim、300 字符上限、`source_quote` / `user_edited` 来源契约、清空联动和失败不变更。
- GCP 实际完成 migration downgrade/upgrade，扩大定向 **73 passed**，全量
  **627 passed, 16 warnings**；SP1 无 UI 改动，下一票为 SP2 候选产生。

### 2026-07-30：SessionPad 带语境候选 SP2

- 新增统一候选标准化与创建服务，packet AI/人工和 recap 入口共用 term/context、已有词过滤、同来源合并和计数逻辑。
- AI 语境必须定位回当前反馈原文；不可定位时留空。人工新建/修改语境标为 `user_edited`，未修改且可复核的 AI 原文标为 `source_quote`。
- packet 表单支持可编辑 term + context 多行，AI 失败时保留人工输入；新 SessionPad 候选不再复制完整反馈到 `source_example`。
- 新迁移 `b3c4d5e6f7a8` 为活跃候选增加同来源规范化唯一索引，并在升级前审计历史重复；GCP downgrade/upgrade 往返和并发路径已通过。
- 相邻回归 80 passed，HTTP 并发连续 5/5，最终全量 **644 passed, 16 warnings**。SP2 完成当时尚未合并或部署；SP3 当前状态见下节。
### 2026-07-30：SessionPad 带语境候选 SP3

- SessionPad 候选审核改为单候选聚焦队列，提供待审核/已接受/已忽略导航与轻量伙伴交换来源；其他 intake 来源继续使用原审核页。
- 候选支持编辑 term/context、显示 `source_quote` / `user_edited` / 缺语境状态；显式“将语境用作例句”只填草稿，不自动污染最终例句。
- 已有词只建立关联且不覆盖释义；补齐 commit 时已有词竞态链接与同来源重复编辑的数据库兜底。
- AI 降级提示保持瞬时；旧通用 accept/ignore、bulk-accept 和 commit-all 路由不再允许 SessionPad 绕过逐张审核。
- GCP 扩大相邻回归、1440px 桌面和 390px 暗色真浏览器已通过；最终全量为 **658 passed, 16 warnings**。SP3 已提交为 `4c84f46`，尚未合并或部署，下一票为 SP4 收口。
