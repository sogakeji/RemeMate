# UI 职责改造方案（纠偏到 demo 边界 + 地基承载新功能）

> 立项日期：2026-06-29
> 性质：**职责层改造**，非纯视觉换皮。之前 `ui-port` 分支只套了 CSS 类名（视觉层），未碰页面职责错位——本方案修正那个错位。
> 立场（用户原话）：「用新的地基承接 demo 做不到的功能，丰富 demo 的功能，而不是丢弃 demo 的边界。」
> 分支：新开 `ui-rescope`（从 master 切，独立于 `backlog-cleanup` / `ui-port`），完成合 master。

---

## 0. 战略原则

- **demo 边界照搬**：各页职责（首页=主词卡、加词中心单一入口、词列表纯列表、stats 纯看板、设置/编辑词/加释义各司其职）原封搬来。RemeMate 现状偏离 demo 边界处（加词散三处、首页/复习两套、stats 有 CTA）改为**回到** demo 边界。
- **新地基承载**：多用户 RLS、多语言隐式词表、token 额度、邀请制、key 加密——这些 demo 单用户私站没有的，落到 demo 边界适用的各页里实现，**充实边界，不替换边界**。
- **隐式词表口径**：**只改 UX/路由/服务，不动 `word_lists` schema。** 底表 `(id, user_id, name, language_code)` 原样；`name` 退化为内部派生值（语言名）；不变量「每用户每语言零或一张词表」由 service upsert 保证，不靠 schema 唯一索引。

---

## 1. 各页职责重定

### 1.1 首页 `/`（问题 1）

| 维度 | demo（照搬） | RemeMate 现状 | 改造 |
|---|---|---|---|
| 职责 | 当天主词卡：当前词、看意思按钮、发音、标记、SRS 三按钮（forgot/fuzzy/known），第一眼暴露词 | 仪表盘：`due_count` 大字 + 「开始复习」+ 空态「去加词」+ 小字统计 | **改成主词卡**，仪表盘价值并入 stats |
| 语言切换 | demo 首页语言切换器（切=切当前语言） | 无 | 加语言切换器 |
| 独立 `/review` | demo 无日常复习页（只有 Bark 回流 `/review/<token>`） | 首页仪表盘 + 独立 `/review` 闪卡**两套并存** | **砍 `/review` 作日常入口**；`/` 即日常复习页。Bark 回流页阶段九再做 |

**第一性原理**（用户原话）：用户是来背词的，第一眼就要暴露单词。

### 1.2 加词中心（问题 2）

**单一主加词入口**，功能做强，删掉散布的零散文加词点。

- nav「加词」→ 指向加词中心（**不是** intake 的 `quick-add` 词穷版）。
- `words/detail.html` 里内嵌的加词表单**移走**。
- stats 的「去加词」CTA **删**。
- 首页空态「去加词」CTA **删**。

加词中心含三方式（demo `add_word.html` + intake 的导入/抽词合并于此）：

| 方式 | 字段 | AI 辅助 |
|---|---|---|
| 手工全字段 | word + **多词义** definition（每条=词性/释义/例句/笔记） | AI 一键填充（`ai_fill_word` 全填）+ 生成例句（`generate_example`）+ 生成笔记（`generate_note`） |
| CSV 导入 | 选语言 → AI 归一化 → 候选审核 | AI 抽词归一化 |
| 文本抽词 | 选语言 → 粘文本 → AI 抽词 → 候选审核 | AI 抽词 |

JSON 提交：demo `add_word` 走 `/add_word` POST JSON `{word, definitions[]}`（多词义数组），RemeMate 现在是 form 单词义——改造后加词中心手工那条走 JSON 多词义提交。

### 1.3 词列表（问题 3 + 加载隐式词表）

| 维度 | demo | RemeMate 现状 | 改造 |
|---|---|---|---|
| 词库列表 `/words` | demo 单语言无此层 | 新建词表表单 + 词表列表 | **删显式建表/删表**（清单见 §2）；`/words` 退化为「按当前语言的词列表」 |
| 词表详情 `/words/<id>` | demo 无（单语言只有一张平面词列表） | 加词表单 + 词清单焊接 | **加词表单移走**；detail 改为纯词列表（搜索/排序/标记/编辑词/加释义/删词） |

**隐式词表落地**：
- 用户心智只有一个概念「我在学法语」；系统层「法语词库」= 该用户 fr 的那张 word_list，**用户不命名、不建、不删**。
- 首页语言切换器切语言 = 切当前语言 = 切当前词库。
- 设置页选「正在学哪种语言」→ `get_or_create_language_list(uid, lang)`，不存在则建（`name` 存内部语言名，用户不可见）。
- 导入多语言 → 按 `language_code` 自动分流，各自语言的隐式词表（自动建）。
- `word_lists` schema **不动**；不变量靠 service upsert-by-`(user_id, language_code)`。

### 1.4 统计 `/stats`（问题 4）

纯看板，无 CTA。补 demo 的：
- SRS 状态条（total / due / learning / mature / new）。
- **易忘词 Top 表**（忘记次数 / 难度 ease / 下次到期）← 需 `get_stats` 加 aggregation。
- **学习热力图**（近 N 周复习/曝光频次，按 ReviewLog.ts 聚合）←原谅该聚合逻辑补上（计划先占位再补）。
- 删现有「今日复习完成 🎉 去加词」CTA。

### 1.5 造句 `/write`（暂缓）
现状 compose + HTMX 片段保留不动，以后整理成 demo 单页（左侧词列表 + 右侧造句 + 输出 vs 输入忘记率 + 随机回顾旧句）。**本轮不做**。

### 1.6 AI 助教（暂缓，阶段六延后）
路由都没有，不做。

### 1.7 设置 `/settings`（对齐 demo，阶段八延伸）
- 「正在学的语言」选择（→ 自动建-切词表）。
- Bark 推送 / 播客 / 时区 / 站点 URL（多用户加 per-user key 加密 + token 额度，demo 原本是单用户裸配置）。
- 现 `/settings` 是 404，**本轮先做「语言选择」最小版**支撑隐式词表闭环（设语言=建词表）；其余 Bark/播客等延后。

### 1.8 编辑词 + 加释义页（对齐 demo，路由都没有）
- `words/edit_word.html`：多词义编辑 + 生成例句/笔记。
- `words/add_definition.html`：为已有词加新词义。
- 当前 `words/detail` 词清单要能链接到这两页。**本轮先补路由 + 模板骨架**，AI 按钮复用 §3 的三个 JSON 端点。

---

## 2. 路由改造清单

### 删除（显式词表管理退场）
- `POST /words` 建词表（`words.lists` 的 POST 分支）→ 删；`GET /words` 改为「当前语言词列表」。
- `POST /words/<list_id>/delete` 删词表 → 删。
- `words/forms.py:NewListForm` → 删（建表用户不做了）。

### 新增
- `GET /` 主词卡（改造 index 路由语义，复用现 `get_due_words`）。
- `POST /words/<word_id>/grade` → 从 `/review/<id>/grade` 迁来，**首页 HTMX 三按钮打这个**（保留现 service `review_word`）。
- 加词中心页路由：`GET/POST /words/add`（JSON 多词义提交）+ AI 三端点 `POST /words/ai-fill`、`POST /words/generate-example`、`POST /words/generate-note`（对齐 demo `/ai_fill_word` `/generate_example` `/generate_note`）。
- 编辑词 `GET/POST /words/<word_id>/edit`、加释义 `GET/POST /words/<word_id>/definitions`。
- `GET/POST /settings`（最小版：语言选择）。
- service 层 `get_or_create_language_list(uid, lang)`。

### 保留不动
- intake 全套路由（import/extract/quick-add/processing/candidates/accept/ignore/bulk-accept/commit）——逻辑保留，但 `word_list_id` 入参改为由 `language_code` 自动绑定（隐式词表）。quick-add 定位=顺手加一词、AI 补全，是加词中心手工方式的一个轻量子入口，**不删**。
- 复习评分 service `review_word` / `srs.grade` / `BUTTON_TO_QUALITY` 不动。
- write 全套不动。

---

## 3. 触点清单（改哪些文件）

**路由**：`app/blueprints/main/routes.py`（index 重写为主词卡）、`app/blueprints/words/routes.py`（删建表/删表、加加词中心+编辑+加释义+grade 迁移）、`app/blueprints/intake/routes.py`（word_list_id 改 language_code 绑定）、新增设置 blueprint 或入 main。

**forms**：`app/blueprints/words/forms.py`（删 NewListForm，AddWordForm 升为多词义 + AI 按钮适配 JSON）。

**服务**：`app/services/words.py`（加 `get_or_create_language_list`、`get_stats` 加 top_lapses + heatmap 聚合、`add_word` 支持多 definition）；`app/services/llm.py`（加 `generate_example` / `generate_note` / `ai_fill_word` 三个高层封装，对齐 demo llm_service.py，底层仍走 `chat()`）。

**模板**：`main/index.html`（主词卡 + 语言切换器）、`words/list.html`（删建表表单→当前语言词列表）、`words/detail.html`（删加词表单→纯词列表 + 编辑/加释义入口）、`words/stats.html`（删 CTA、补易忘词表+热力图）、`words/add.html` / `words/edit.html` / `words/add_definition.html`（新）、`intake/quick_add.html`（word_list_id 改语言选择）、`auth/login.html` 不动、`base.html`（nav「加词」指向加词中心、删 review 入口或保留作首页别名、加语言切换器或放首页）、`review/review.html`+`_card.html`（语义并入首页 `_card`）。

**测试**（重评，非硬保）：
- `test_words.py::test_create_list_and_add_word`：「建词表」概念退场，改测「设语言→自动建词表→加词」。
- `test_words.py::test_delete_list` + 剩`test_delete_list_after_review_cascades`：无显式删表演作，重评为「清空某语言」或移到词级删除测；删表能力本身保留 service 层 `delete_word_list`（管理员/清空场景用），UI 不暴露。
- `test_stats_counts`：断言随 stats 内容更新。
- `test_words_n_plus_1.py`：detail 仍是词列表，N+1 守卫应仍绿。
- `test_intake.py`：word_list_id→language_code 绑定，重写入参。

**不动**：`word_lists` schema、RLS migration（policy 已是 `user_id = UID`，隐式不变量继承）、srs/quota/migration 非 RLS 部分、登录态。

---

## 4. 与 BACKLOG 的关系

- B2「conftest/CI 自动跑迁移」仍待办，本轮不碰。
- A1 token 硬约束+TOCTOU暂不动（已定）。
- 热力图聚合：本方案现在补（计划原说占位，今决定补）——属 stats 改造一部分。
- 设置页 Bark/播客：阶段八，本轮只做语言选择最小版。

---

## 5. 执行顺序（小步）

1. service 层先动：`get_or_create_language_list` + `add_word` 多词义 + `llm` 三封装。配单测。
2. 首页主词卡 + 语言切换器 + grade 迁移，HTMX 三按钮打新 grade 端点。真机看首页。
3. 加词中心页（手工 JSON 多词义 + 导入/抽词并入 + AI 三按钮）。真机加词。
4. 词列表页（删建表/删表，detail 纯词列表，编辑/加释义入口）。
5. stats（删 CTA + 易忘词表 + 热力图）。
6. 设置最小版（语言选择闭环）。
7. 编辑词 + 加释义页骨架。
8. 测试重评 + 收敛 → pytest 全绿 → 真机走全页 → 合 master。

每步独立 commit，committed 身份 `suqing <shinypig88@gmail.com>`。

---

## 6. 验证

- pytest 全绿（断言按职责重写，非功能回归）。
- 真机：首页主词卡挣钱刷词 + 三按钮 HTMX + 语言切换切词库 + 暗色 + 响应式。
- 加词中心：手工 AI 一键填充、生成例句；导入 CSV 走候选；抽词。
- 跨用户隔离仍守（RLS + service 双层，因索引不改 service 兜底）。
- 隐式词表不变量验证：同语言导入两次不建两表。