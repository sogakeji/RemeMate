---
status: resolved
type: research
resolved_at: 2026-07-20
---

# SessionPad 带语境候选数据模型

## Question

在不破坏 packet、adoption、WordCandidate、intake source 和 RLS 的前提下，如何分离完整伙伴反馈、
候选短语境和最终词条例句，并处理重复、历史数据、AI JSON 与手动降级？

## Current evidence

- `PartnerPacketItem.content` 是收到的不可变完整反馈。
- `PartnerPacketIntake` 把反馈包映射到接收方拥有的 `sessionpad` intake source。
- `PartnerPacketItemAdoption` 保留反馈条目到候选的采用关系。
- `PartnerRecap.intake_source_id` 能反查“帮自己记”的某次复盘。
- `WordCandidate.source_id` 已把候选归入一次 intake source。
- 最终 `Word` 在同用户、同语言词表内已有规范化唯一约束。

结构性问题是完整反馈目前被复制进候选 `source_example`，commit 又可能把它当成
`Definition.example`，导致完整来源、候选语境和最终例句混为一个字段。

## Resolution

### 1. 三层语义分离

- **交换来源**：某位伙伴的某一次语言交换；完整内容继续在 packet/recap 中。
- **候选语境**：候选上可空、可编辑的短学习语境。
- **最终例句**：用户明确准备写入词条定义的例句。

候选语境不自动成为最终例句。只有用户明确选择“用作例句”或填写最终例句后才写入。

### 2. 最小字段迁移，不新增语境表

`word_candidates` 新增：

| Field | Type | Null | Meaning |
| --- | --- | --- | --- |
| `context_excerpt` | `Text` | yes | 可编辑候选短语境，服务层限制 300 字符 |
| `context_provenance` | `String(20)` | yes | `source_quote` 或 `user_edited` |

数据库 CHECK 只允许上述非空值；空语境的 provenance 必须为空，非空语境必须有 provenance。

不新增逐条消息关联表。产品只要求候选关联到某位伙伴的一次交换，不要求证明来自包内哪条消息。
现有 `source_id` 足以反查伙伴、交换日期、标题和语言。

### 3. 两条 SessionPad 路径统一

- 收到反馈：`WordCandidate -> IntakeSource <- PartnerPacketIntake -> PartnerPacket`。
- 帮自己记：`WordCandidate -> IntakeSource <- PartnerRecap.intake_source_id -> PartnerRecap`。

两条路径共用“来源 / 候选语境 / 最终例句”模型。完整反馈只在用户主动查看来源时从 packet/recap
读取，不复制进候选语境。

### 4. `source_example` 兼容边界

- 新 SessionPad 候选不再写 `source_example`。
- SessionPad 入库只使用显式 example，不再用 `source_example` 兜底。
- 阅读收词和其他 intake 的既有 `source_example` 行为保持不变。
- 不做全局字段重命名。

### 5. 重复与身份

- 同一用户、同一 `source_id`、同一规范化词语，在 pending/accepted 状态只保留一个候选。
- 同一次提交先在内存去重；同包多条反馈命中同词时复用一个候选，保留 adoption 来源事实。
- 后续来源不静默覆盖已有非空语境。
- 不同交换再次遇到同一词时允许不同候选，因为来源和语境不同。
- 最终词库仍只有一个 `Word`。
- 接受词库已有的候选时关联既有 `word_id`，不创建第二个词，也不自动改写既有释义或例句。

实现阶段评估活动候选 partial unique expression index：

```sql
UNIQUE (source_id, lower(btrim(word)))
WHERE status IN ('pending', 'accepted')
```

迁移前审计历史重复；若存在，不在迁移中猜测合并。

### 6. AI 与人工统一契约

AI 只返回建议，不直接创建候选：

```json
{
  "candidates": [
    {
      "term": "prendre des cours",
      "context": "les personnes âgées prennent des cours de danse"
    }
  ]
}
```

- AI 最多 8 项，人工最多 20 项。
- `term` 必填，trim 后最多 80 字符。
- `context` 可空，trim 后最多 300 字符。
- 按现有 `normalize_word_key` 去重，保持第一个展示形式。
- 同一请求重复词优先保留第一个非空且有效语境。
- AI context 必须是当前反馈原文的连续片段；允许折叠 Unicode 空白和换行差异，不允许改写或
  另造例句。无法定位时置空。
- AI 产生的语境标为 `source_quote`；用户创建或编辑后标为 `user_edited`。

### 7. 手动降级

AI 不可用、超时、空结果、JSON 异常或语境定位失败时：

- 不创建半成品候选。
- 不记录成功用量。
- 保留完整反馈与用户输入。
- 显示明确降级提示。
- 用户仍能手动提交 term，context 可空或手填。

人工提交和 AI 预填走同一创建服务。

### 8. 重试与并发

- 同一 packet/recap 复用唯一 sessionpad intake source。
- 相同结构化提交返回同一候选。
- 已有非空语境不被重试覆盖；空语境只有在用户明确再次提交时才补入并标记 `user_edited`。
- AI 建议只是预填，不得修改已存在候选。
- 服务层使用来源级锁或等价串行化，数据库唯一索引作并发兜底。
- adoption 插入保持幂等，并允许一条反馈对应多个候选。

### 9. 历史兼容

- 不把历史 `source_example` 自动回填为 `context_excerpt`。
- 历史待审核 SessionPad 候选显示空语境，可重新 AI 提取或手填。
- 不删除或改写已进入 `Definition.example` 的历史内容。
- 新版本停止继续使用 SessionPad `source_example` 兜底，先阻止新污染。

### 10. 所有权与 RLS

本模型不新增用户拥有表：

- 候选读取和修改始终按 `WordCandidate.user_id`。
- `source_id` 必须属于同一用户，保留复合所有权约束。
- 接收来源只经接收方拥有的 `PartnerPacketIntake` 解析。
- 发送方看不到接收方候选、语境、采用状态或最终词条。
- 后台 dispatch 权限不扩大到候选编辑。

## Minimum regression matrix

- 字段约束、历史空值和非 SessionPad 来源兼容。
- 同来源规范化重复合并、同包多 adoption、不同交换重复候选、最终词库唯一。
- 接受带 context 但无 example 时不写最终例句；明确采用后才写。
- AI 原文定位、超长/异常 JSON、全挂和人工降级。
- 重试、并发、已有词关联和不覆盖已有语境。
- packet/recap 两条来源及跨用户 RLS。
- 阅读、CSV、文本抽词与通用候选审核不回归。

## Next

数据模型由候选审核决议 `10-sessionpad-candidate-review-prototype.md` 承接；最终实施边界见
`11-observation-and-final-implementation-roadmap.md`。

