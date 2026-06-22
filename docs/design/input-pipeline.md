# 输入管道设计文档

> 记录日期：2026-06-23
> 状态：P1 实现

---

## 一句话定位

输入端是"够用的基础设施"，不是产品差异点。目标：让用户的词条稳定进库，不丢、不乱、可审核，DeepSeek 做归一化，人工审核候选词后 commit。

---

## 整体数据流

```
用户输入（CSV / 文本粘贴 / 快速加词）
    ↓
intake_sources（记录来源元信息）
    ↓
source_segments（按段落/行拆分，保留原始文本）
    ↓
DeepSeek 抽词 + 归一化
    ↓
word_candidates（待审核候选词）
    ↓
用户在 /intake/<source_id>/candidates 逐条 accept / ignore
    ↓
POST /intake/<source_id>/commit
    ↓
words + definitions（正式入库，触发 SRS 初始化）
```

所有步骤在同一请求链内同步完成（CSV 和快速加词），或通过 HTMX SSE 流式显示进度（文本抽词）。P1 无异步队列。

---

## 三种入口

### A. CSV 上传

**适用场景**：从 Aisten、Anki 等工具导出的词表。

**格式约束（硬约束，不猜测）**：

```
word,part_of_speech,meaning,example,note
décollage,nm,起飞,Le décollage m'a coupé le souffle.,可选备注
```

- 第一行必须是 header，列名不区分大小写，顺序任意
- 必填列：`word`、`meaning`；其余列可缺失
- 编码：UTF-8（上传页面提示并提供模板下载）
- 格式不符 → 返回错误 + 下载模板链接，不尝试猜测列映射

**处理逻辑**：

1. 解析 CSV，逐行写入 `source_segments`（每行一条 segment）
2. 按批次（每批 20 条）调 DeepSeek 归一化：补全缺失字段、修正词形、标准化 part_of_speech
3. 归一化结果写入 `word_candidates`，`status='pending'`
4. 跳转至 `/intake/<source_id>/candidates` 审核页

CSV 文件本身不持久化存储，仅在请求生命周期内处理。

---

### B. 文本抽词 /extract

**适用场景**：粘贴文章、字幕、对话记录，自动抽出生词。

**处理逻辑**：

1. 用户粘贴文本，选择目标语言（`language_code`）
2. POST 创建 `intake_source`（type=`text_extract`），原文存 `source_segments`（整段作为一个 segment）
3. SSE 流式响应：DeepSeek 边抽边返回候选词，前端实时渲染卡片
4. 抽词完成后页面转为审核态（同 /candidates 页面逻辑）

**DeepSeek 抽词 prompt 要点**：
- 只抽对用户可能陌生的词（非极高频词）
- 每词返回：`word`, `part_of_speech`, `meaning`（目标语言释义）, `example`（从原文摘取原句）, `context_start/end`（字符偏移，用于高亮原文）
- 不抽专有名词、缩写、数字

---

### C. 快速加词 /quick-add

**适用场景**：用户在复习或日常中临时加一个词，不想走完整 CSV 流程。

**处理逻辑**：

1. 用户填写：词 + 可选释义
2. 若用户填了释义 → DeepSeek 仅做补全和规范化
3. 若用户只填词 → DeepSeek 全量生成释义、例句
4. 结果直接进 `word_candidates`（`status='pending'`）并跳转单词审核页
5. 用户确认后立即 commit，无需批量审核流程

快速加词是唯一允许直接从候选跳过批量审核的入口。

---

## 数据模型

```python
class IntakeSource(db.Model):
    __tablename__ = "intake_sources"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source_type     = db.Column(db.String(20), nullable=False)  # csv / text_extract / quick_add
    language_code   = db.Column(db.String(10), nullable=False)
    word_list_id    = db.Column(db.Integer, db.ForeignKey("word_lists.id"), nullable=False)
    original_name   = db.Column(db.String(200))   # CSV 文件名 or 文本前 50 字符
    status          = db.Column(db.String(20), default="processing")  # processing / done / error
    total_segments  = db.Column(db.Integer, default=0)
    total_candidates= db.Column(db.Integer, default=0)
    accepted_count  = db.Column(db.Integer, default=0)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at    = db.Column(db.DateTime)


class SourceSegment(db.Model):
    __tablename__ = "source_segments"
    id              = db.Column(db.Integer, primary_key=True)
    source_id       = db.Column(db.Integer, db.ForeignKey("intake_sources.id"), nullable=False)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    segment_index   = db.Column(db.Integer, nullable=False)   # 排序用
    raw_text        = db.Column(db.Text)                      # 原始行/段落，保留备查


class WordCandidate(db.Model):
    __tablename__ = "word_candidates"
    id              = db.Column(db.Integer, primary_key=True)
    source_id       = db.Column(db.Integer, db.ForeignKey("intake_sources.id"), nullable=False)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    word            = db.Column(db.String(200), nullable=False)
    part_of_speech  = db.Column(db.String(50))
    meaning         = db.Column(db.Text)
    example         = db.Column(db.Text)
    note            = db.Column(db.Text)
    status          = db.Column(db.String(20), default="pending")  # pending / accepted / ignored
    word_id         = db.Column(db.Integer, db.ForeignKey("words.id"))  # commit 后填入
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

RLS 约束：所有表均有 `user_id` FK，Postgres RLS policy 同其他表（见 data-isolation-security.md）。

---

## 候选词审核页 /candidates

**交互设计**（HTMX，无页面跳转）：

```
[词：décollage]  [词性：nm]  [释义：起飞]
[例句：Le décollage m'a coupé le souffle.]
              [接受]  [忽略]
```

- 每张卡片独立操作（`hx-post` → 服务端标记 status → 返回 HTMX 片段更新该卡片状态）
- 卡片支持内联编辑：用户可在接受前修改释义/例句（HTMX `hx-trigger="change"`）
- 顶部批量操作：「全部接受」（`POST /intake/candidates/bulk-accept`）
- 审核完成后点「提交入库」（`POST /intake/<source_id>/commit`）

**状态持久化**：审核过程中途离开，已操作的卡片状态保留（DB 已写入），重新进页面继续。

---

## commit 逻辑

```python
def commit_intake_source(source_id: int, user_id: int):
    candidates = WordCandidate.query.filter_by(
        source_id=source_id,
        user_id=user_id,
        status="accepted",
    ).all()

    for c in candidates:
        # 去重：同词表内已有同词则跳过（不报错，静默跳过）
        existing = Word.query.join(WordList).filter(
            WordList.user_id == user_id,
            WordList.id == source.word_list_id,
            Word.word == c.word,
        ).first()
        if existing:
            c.word_id = existing.id
            continue

        word = Word(
            list_id=source.word_list_id,
            word=c.word,
            due_date=datetime.utcnow(),   # 立即进入 SRS 队列
            interval=1, ease=2.5, reps=0, lapses=0,
        )
        db.session.add(word)
        db.session.flush()

        defn = Definition(
            word_id=word.id,
            part_of_speech=c.part_of_speech,
            meaning=c.meaning,
            example=c.example,
            note=c.note,
        )
        db.session.add(defn)
        c.word_id = word.id

    source.status = "done"
    source.accepted_count = len([c for c in candidates if c.word_id])
    source.completed_at = datetime.utcnow()
    db.session.commit()
```

去重策略：同词表内完全匹配词形则静默跳过，不报错，不合并定义。用户如需更新定义，进词库详情页手动编辑。

---

## DeepSeek 调用规范

| 入口 | 调用时机 | 批次大小 | token 计入 |
|---|---|---|---|
| CSV | 上传后同步 | 每批 20 条 | 是 |
| /extract | 用户提交后 SSE 流式 | 整段 | 是 |
| /quick-add | 用户提交后同步 | 单词 | 是 |

失败处理：
- DeepSeek 单批失败 → 该批候选词 `status='error'`，标注"AI 处理失败，请手动填写"，不阻断整体流程
- 用户 token 额度耗尽 → 提示升级或填写自己的 key，CSV 场景允许跳过 AI 归一化直接用原始列值创建候选词

---

## 明确不做（P1）

- 异步队列（Celery / RQ）：同步 + SSE 足够覆盖 P1 文本量
- 文件持久化存储：CSV 不存服务器，处理即丢
- 格式自动猜测：列名必须匹配模板，否则报错
- 自动去重合并定义：同词静默跳过，不做 merge
- 邮件自动导入：P1 不做
- Eudic 同步：P1 不做
