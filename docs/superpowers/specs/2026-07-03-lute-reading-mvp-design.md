# Lute-style PDF 阅读学语言 MVP 设计

> 日期：2026-07-03  
> 分支：`lute-reading-mvp-design`  
> 状态：用户已批准设计，等待实现计划  
> 背景：RemeMate 已进入邀请制封闭测试。现有 CSV/文本抽词/加词中心可用，但“先整理材料再导入词汇”的门槛偏高。新功能参考 Lute v3 / LingQ / Learning With Texts 的“读中学”模式，用阅读器降低词汇输入门槛。

---

## 1. 目标

新增一个 **PDF 阅读学语言** MVP：用户上传文本型 PDF，进入阅读器边读边选词；选词后弹出本地词典卡片；点击“加入学习”后，该词进入 RemeMate 现有候选审核与入库链路，并把 PDF 原文中包含该词的整句写入词库例句字段。

本功能的目标不是做完整 Lute clone，而是在 RemeMate 现有基座上增加一个低门槛输入入口：

- 用户不需要先整理 CSV。
- 用户不需要先粘贴一整段让 AI 抽词。
- 用户可以在真实阅读场景里发现生词。
- 加入词库时自动带上原文语境。
- 入库后仍复用现有隐式词表、候选审核、去重、SRS 初始化、多用户隔离。

---

## 2. 参考项目与许可口径

### 2.1 Lute v3

- 项目：`https://github.com/LuteOrg/lute-v3`
- 许可证：MIT License
- 结论：可以参考 Lute 的产品边界和阅读学习思路。若复制任何实质代码，必须保留 copyright 和 MIT license notice。本 MVP 优先参考思路，不引入 Lute 代码。

### 2.2 不重复造轮子

调研结论：PDF 解析、日语分词、离线词典已有成熟库，RemeMate 不应自写底层能力。

| 能力 | MVP 选择 | 说明 |
|---|---|---|
| 文本型 PDF 提取 | pypdf | PyMuPDF 官方 PyPI 元数据为 AGPL 3.0 / Artifex 商业双许可，不作为闭测/未来商业服务器默认依赖。MVP 默认 parser 改为 BSD-style license 的 `pypdf`；`pdfminer.six` 作为 MIT fallback 候选。只处理文本型 PDF，不做 OCR。 |
| 日语分词/词形 | fugashi + unidic-lite | 用于日语选词归一化，不手写日语规则。 |
| 日语词典 | jamdict / JMdict | 离线 JMdict 查询候选。 |
| 通用词典 | 本地词典 adapter | 优先适配许可证清晰的本地词典数据，后续可支持 StarDict/MDict/DSL。 |
| 英法词形 | 后续 adapter | MVP 先 exact lookup + lowercase，不强行引入复杂词形还原。 |

所有第三方依赖和词典数据必须写入 `docs/THIRD_PARTY.md` 或等价文档：用途、许可证、是否随仓库分发、下载/更新方式。

---

## 3. MVP 边界

### 3.1 第一版做

- 只支持 **文本型 PDF** 上传。
- 保存阅读材料到用户书架。
- 阅读器显示 PDF 抽出的纯文本。
- 记录最后阅读位置。
- 用户主动选中词/短语后弹词典卡片。
- 首批目标语言且 MVP 仅允许：中文、英文、日文、法文。
- 查词使用本地离线词典，不走 AI。
- 用户点击“加入学习”后创建候选词。
- 阅读候选入库时，`definitions.example` 必须来自 PDF 原文整句。
- 所有入库仍走现有 `WordCandidate` 审核/commit 链路。

### 3.2 第一版不做

- OCR / 扫描件识别。
- EPUB / TXT / Markdown / 网页链接。
- AI 即时查词。
- 全文翻译。
- 全篇自动分词高亮。
- Lute 式词熟悉度等级。
- 复杂 PDF 版式还原。
- 阅读完成率统计。
- 把词典大文件提交进 git。

### 3.3 PDF vs EPUB 取舍

EPUB 对纯阅读器通常更容易处理，因为文本和章节结构更清晰。PDF 更常见，更符合闭测用户“导入文档/PDF”的预期，但文本质量不稳定。本 MVP 选择 PDF 是因为输入价值更高，不是因为技术更简单。范围限定为“文本型 PDF”，扫描件/OCR 后续再评估。

---

## 4. 产品流程

### 4.1 页面与路由

| 页面 | 路由 | 职责 |
|---|---|---|
| 阅读书架 | `GET /reading` | 展示用户已上传 PDF：标题、语言、最近阅读时间、继续阅读按钮。 |
| 上传 PDF | `GET /reading/new` / `POST /reading` | 选择语言并上传文本型 PDF。pypdf 提取文本后保存阅读材料。 |
| 阅读器 | `GET /reading/<doc_id>` | 渲染文档正文，支持选词弹卡、加入学习、保存最后位置。 |
| 查词 API | `POST /reading/<doc_id>/lookup` | 接收选中文本和位置，查本地词典，抽取原文整句语境。 |
| 加入候选 API | `POST /reading/lookups/<lookup_id>/add-candidate` | 把 lookup 转成 `WordCandidate`。 |
| 删除文档 | `POST /reading/<doc_id>/delete` | 删除阅读材料和 lookup；已入库词不删除。 |

### 4.2 阅读器交互

1. 用户打开阅读器。
2. 页面显示 PDF 抽出的纯文本段落。
3. 用户选中词或短语。
4. 前端提交：`term`、`selection_start`、`selection_end`。
5. 后端校验文档归属当前用户。
6. 后端基于 `selection_start/end` 从文档正文抽取完整句子。
7. 后端调用 `dictionary.lookup(language_code, term)`。
8. 后端写入 `reading_lookups`。
9. 前端弹卡片，显示词、释义、词性、PDF 原文整句、“加入学习”。
10. 用户点击“加入学习”。
11. 后端创建 `WordCandidate`，并把 PDF 原文整句写入 `WordCandidate.example`。
12. 用户进入现有候选审核页确认并入库。
13. commit 后词库里的 `definitions.example` 就是 PDF 原文整句。

### 4.3 原文语境硬规则

阅读导入产生的词必须携带原文语境：

- `WordCandidate.word` = 用户选中的词/短语。
- `WordCandidate.meaning` = 词典释义。
- `WordCandidate.part_of_speech` = 词典词性，如果有。
- `WordCandidate.example` = PDF 原文中包含该词的完整句子。
- `WordCandidate.context_start` / `context_end` = 原文位置。
- `WordCandidate.note` 可记录来源，例如 `来自《xxx.pdf》`。

词典例句不能覆盖 PDF 原文整句。若词典返回例句，可只在弹卡展示或保存到 lookup JSON，不能作为阅读候选的主例句。

### 4.4 阅读位置

MVP 只保存最后阅读位置，不做完成率：

- 前端滚动时节流上报，或离开页面前上报。
- 后端写入 `reading_documents.last_position`。
- `last_position` 使用 Postgres `JSONB`（或等价 JSON 类型），不是无校验字符串。
- JSON schema 固定为：`{"char_offset": int, "scroll_ratio": float}`。
- `char_offset` 必须在 `[0, len(content_text)]` 内；`scroll_ratio` 必须在 `[0, 1]` 内。
- 下次打开文档时滚到附近位置。

---

## 5. 架构

新增 `reading` 模块，边界独立，但复用现有 intake/candidate 入库基座。

### 5.1 服务边界

| 服务 | 职责 | MVP 默认实现 |
|---|---|---|
| `reading.parsers` | 文件校验、文本型 PDF 抽纯文本、返回标题/文本/页数/元数据。 | pypdf |
| `reading.dictionary` | `lookup(language_code, term)`，统一返回释义/词性/例句/来源。 | 本地离线 adapter |
| `reading.tokenize` | 处理选中文本、归一化、日语分词/lemma。 | 日语用 fugashi；其他语言先简单 normalize。 |
| `reading.context` | 根据 selection offset 抽取包含选词的完整句子。 | 语言标点规则 + 长度截断。 |
| `reading.service` | 保存阅读文档、保存最后位置、创建 lookup、加入候选。 | RemeMate 业务服务。 |
| `intake.service` | 候选审核、commit 入库、去重、SRS 初始化。 | 复用现有 `WordCandidate` 链路。 |

### 5.2 关键原则

- 阅读器不直接写 `words`。
- PDF parser 不做词典查询。
- 词典 adapter 不知道用户和词库。
- 入库继续走 `WordCandidate` 和 commit。
- 未来加 EPUB/TXT/MD 只新增 parser，不改阅读器核心。
- 未来换词典源只换 adapter，不改阅读器核心。

---

## 6. 数据模型

### 6.1 新表：`reading_documents`

字段建议：

- `id`
- `user_id` FK users, not null
- `language_code` string, not null
- `title` string, not null
- `source_filename` string, not null
- `content_text` text, not null
- `content_hash` string, not null
- `page_count` integer, not null
- `last_position` JSONB nullable
- `created_at`
- `updated_at`

索引/约束：

- unique `(user_id, content_hash)`，防同一用户重复上传同一 PDF。
- `language_code` 只允许 MVP 支持集：`zh/en/ja/fr`。其他语言后续再放开。
- `page_count >= 0`。
- `title` / `source_filename` 最大长度要有上限，避免超长文件名进库。
- 所有查询必须带 `user_id` 应用层过滤。
- migration 必须为 `reading_documents` 开启 RLS，并创建 `user_id = current_setting('app.current_user_id')` 对应 policy，保持和现有多用户隔离口径一致。

### 6.2 新表：`reading_lookups`

字段建议：

- `id`
- `document_id` FK reading_documents, cascade delete
- `user_id` FK users, not null
- `term` string, not null
- `normalized_term` string
- `language_code` string, not null
- `dictionary_result_json` JSONB nullable
- `context_sentence` text nullable
- `context_start` integer nullable
- `context_end` integer nullable
- `candidate_id` FK word_candidates nullable, set null
- `created_at`

索引/约束：

- index `(user_id, document_id)`
- index `(user_id, normalized_term)`
- `language_code` 只允许 `zh/en/ja/fr`。
- `context_start >= 0`，`context_end >= 0`，且两者同时存在时 `context_start < context_end`。
- migration 必须为 `reading_lookups` 开启 RLS，并创建按 `user_id` 隔离的 policy。
- 删除 reading document 时 cascade 删除 lookup；已入库的 `WordCandidate` / `Word` 不随文档删除。

### 6.3 复用现有表

- `IntakeSource`：新增 `source_type='reading_pdf'`，作为阅读候选的来源容器。实现时需要更新所有基于 `source_type` 的分支、注释、测试和任何 CHECK/常量定义。阅读 lookup 转候选时，若该 document 还没有对应 source，则创建一个 `status='done'`、`total_segments=0` 的 reading source；后续同一文档的候选复用该 source。
- `WordCandidate`：复用 `word`、`part_of_speech`、`meaning`、`example`、`note`、`context_start`、`context_end`、`status`、`word_id`。
- `Word` / `Definition`：不新增字段。commit 后由现有逻辑写入。

阅读候选的原文例句必须不可被候选页编辑覆盖。实现方式二选一：

1. 推荐：给 `WordCandidate` 增加 `source_example` 或 `context_sentence` 字段，阅读候选 commit 时优先写该字段到 `Definition.example`；候选页可编辑的 `example` 只作为显示草稿，不覆盖源例句。
2. 次选：候选页对 `source_type='reading_pdf'` 的 `example` 字段设为只读。

验收测试必须覆盖“候选页编辑不能把 PDF 原文例句替换掉”。

### 6.4 现有 intake 表约束更新

若实现中为 `IntakeSource.source_type` / `WordCandidate.status` / `IntakeSource.status` 增加数据库 CHECK 约束，必须包含：

- `IntakeSource.source_type`: `csv`, `text_extract`, `quick_add`, `reading_pdf`
- `IntakeSource.status`: `processing`, `done`, `error`
- `WordCandidate.status`: `pending`, `accepted`, `ignored`

所有新约束必须可重入，遵守 HANDOFF 里迁移可重入踩坑：动态查约束名或使用显式命名 + `IF EXISTS` 防重复执行。

---

## 7. 词典策略

### 7.1 接口

统一接口：

```python
dictionary.lookup(language_code, term) -> DictionaryResult
```

`DictionaryResult` 字段：

- `term`
- `normalized_term`
- `language_code`
- `part_of_speech`
- `meanings`
- `examples`
- `source`
- `confidence`

### 7.2 首批语言

| 语言 | MVP 策略 |
|---|---|
| 中文 `zh` | 本地词典 adapter，外置 Kaikki.org/Wiktionary Chinese 数据，用户主动选词/短语，exact lookup 优先。 |
| 英文 `en` | 本地词典 adapter，外置 Kaikki.org/Wiktionary English 数据，exact lookup + lowercase。 |
| 日文 `ja` | fugashi + unidic-lite 做归一化/lemma，jamdict + 外置 JMdict 查词。 |
| 法文 `fr` | 本地词典 adapter，外置 Kaikki.org/Wiktionary French 数据，exact lookup + lowercase。 |

MVP 只允许 `zh/en/ja/fr` 四种语言上传阅读材料和查词。其他语言后续再放开；第一版 UI 不展示 unsupported language 入口，后端也拒绝。

### 7.3 数据存放

真实词典数据不提交到 git。推荐：

- `.env` 增加 `DICTIONARY_DATA_DIR=/srv/rememate-data/dictionaries`
- 小型测试词典放 `tests/fixtures/dictionaries/`
- `flask doctor --strict` 检查目标语言词典是否存在

缺词典或未命中时：

- 弹卡显示“词典暂未命中”。
- 仍显示 PDF 原文整句。
- 允许无释义加入候选。
- 候选页可手动补释义。
- 不调用 AI。

### 7.4 许可硬门

实现开始前必须完成第三方许可确认，不允许边写边赌：

- PyMuPDF 官方 PyPI 元数据为 `Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License`，闭测/未来商业服务器默认依赖不可接受；MVP 默认使用 `pypdf`，`pdfminer.six` 仅作为 fallback 候选。这个决定是 Slice 1 的放行条件。
- `fugashi` / `unidic-lite` / `jamdict` / JMdict 已在 `docs/THIRD_PARTY.md` 逐项记录 license、数据来源、更新方式。
- 中文、英文、法文词典数据源选用外置 Kaikki.org/Wiktionary 数据，具体 license、安装路径、更新方式见 `docs/THIRD_PARTY.md`。没有明确再分发许可的数据不得随仓库或服务器镜像分发。
- 真实词典数据全部外置，不进 git；仓库只放最小测试 fixture。

---

## 8. 错误处理

| 场景 | 处理 |
|---|---|
| 非 PDF | 提示“当前版本只支持文本型 PDF”。 |
| 扫描件或无文本 PDF | 提示“这个 PDF 可能是扫描件，当前版本暂不支持 OCR”。 |
| PDF 太大或页数太多 | 上传前拦截并提示拆分上传。 |
| pypdf 解析失败 | 保存失败，不创建阅读材料，提示用户换文件。 |
| 词典缺失 | 弹卡降级，允许手动加入候选。 |
| 词典未命中 | 弹卡显示原文整句和“无释义加入候选”。 |
| offset 漂移 | 后端校验 selection 文本；失败时用附近窗口抽句并记录 warning。 |
| 词已在当前语言词库 | 弹卡显示“词库中已存在”，不重复加入。 |

---

## 9. 测试计划

| 层级 | 测试内容 |
|---|---|
| parser 单测 | 文本型 PDF 能抽出文本；空文本/扫描件样 PDF 报明确错误；超大小/页数被拦截。 |
| dictionary 单测 | `zh/en/ja/fr` adapter 命中、未命中、缺词典文件降级；日文 normalization 不手写规则。 |
| context 单测 | 给定 `content_text + selection_start/end`，抽出完整句子；中文/日文/英文/法文标点覆盖；超长句截断。 |
| service 单测 | 上传 PDF 创建 `reading_documents`；lookup 创建 `reading_lookups`；加入学习创建 `WordCandidate` 且 `example=PDF 原文整句`。 |
| 隔离集成测试 | A 用户不能读/查/删 B 用户文档；lookup/candidate 都按 `user_id` 过滤。 |
| UI 集成测试 | 上传 PDF → 阅读器 → 选词查词 → 弹卡 → 加入候选 → 审核 → 入库，最终 `Definition.example` 是原文整句。 |
| doctor 测试 | `DICTIONARY_DATA_DIR` 缺失/词典缺失时给出正确 WARN/FAIL。 |
| migration 测试 | Alembic upgrade/downgrade 可跑，RLS/policy 存在，约束名可重入。 |
| abuse 测试 | 重复上传同一 PDF、unsupported language、offset 篡改、超大 PDF/超长文本、删除文档后 lookup 清理、阅读候选例句不可被审核页编辑覆盖。 |

---

## 10. MVP 切片

### Slice 1：设计与依赖确认

- 写本设计文档并提交。
- 已确认 PyMuPDF 为 AGPL/commercial 双许可，不作为默认依赖；parser 默认改为 `pypdf`。
- 确认 fugashi / unidic-lite / jamdict / JMdict 许可。
- 选定中文、英文、法文词典数据源，记录 license、安装路径、更新方式。
- 写 `docs/THIRD_PARTY.md` 或等价第三方依赖记录文档结构。
- 没有完成许可确认，不进入代码实现。

### Slice 2：PDF 阅读材料

- migration：`reading_documents`。
- pypdf parser adapter。
- PDF 上传/保存/书架/阅读器只读展示。
- 保存最后位置。
- parser 单测 + 文档隔离测试。

### Slice 3：查词弹卡

- `reading_lookups` 表。
- dictionary service + 本地测试词典 fixtures。
- context sentence 抽取。
- 选词 lookup API。
- 弹卡 UI。

### Slice 4：加入候选与入库

- lookup → `WordCandidate`。
- `example` 必须是 PDF 原文整句。
- 跳到现有候选审核页。
- commit 后词库 `Definition.example` 验证。

### Slice 5：闭测加固

- `doctor --strict` 检查 `DICTIONARY_DATA_DIR`。
- 文件大小/页数/字符限制。
- 错误文案。
- 真机完整流程。

---

## 11. 开放问题 / 实现前硬门

1. **已决策**：PyMuPDF 官方 PyPI 元数据为 AGPL/commercial 双许可，不适合作为闭测/未来商业服务器默认依赖；parser adapter 默认使用 `pypdf`，`pdfminer.six` 作为 fallback 候选。
2. **已决策**：中文/英文/法文词典数据源选用外置 Kaikki.org/Wiktionary 数据；license、安装路径、更新方式记录在 `docs/THIRD_PARTY.md`。数据不得随仓库或默认服务器镜像分发。
3. **已决策**：日语 tokenizer 使用 fugashi + unidic-lite；词典使用 jamdict + 外置 JMdict，优先外置到 `DICTIONARY_DATA_DIR`。
4. `WordCandidate` 原文例句不可变的实现方式需在实现计划里二选一：新增 `source_example/context_sentence` 字段，或候选页对 reading candidate 的 example 只读。推荐新增字段。

---

## 12. 验收标准

MVP 完成时，以下路径必须成立：

1. 用户上传一个文本型 PDF。
2. PDF 变成书架里的阅读材料。
3. 用户打开阅读器，能看到纯文本内容。
4. 用户选中一个词。
5. 弹卡显示词典释义和 PDF 原文整句。
6. 用户点击“加入学习”。
7. 系统创建候选词。
8. 用户审核并 commit。
9. 词进入当前语言隐式词表。
10. 词库详情中该词的例句字段等于 PDF 原文整句。
11. 另一个用户无法访问该 PDF、lookup 或候选。
12. 扫描件 PDF 给出明确“不支持 OCR”提示。
