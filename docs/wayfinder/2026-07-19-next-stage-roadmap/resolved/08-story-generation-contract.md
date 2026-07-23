---
status: resolved
type: grilling
resolved_at: 2026-07-20
contract_version: review_story_v1
---

# 定义多语言短故事生成契约

## Question

如何定义一个可测试的多语言结构化生成契约，覆盖 3–5 个目标词、语言、难度、篇幅、翻译、
目标词校验、缓存、额度、超时和 provider 降级，同时不让 AI 失败阻断复习完成？

## Resolution

### 1. 借鉴 MemoBuddy，但不移植其产品假设

保留固定选词、固定 4–6 句和固定提示词的朴素性；拒绝随机五词、法语/中文写死、自由 Markdown、
Planner/SQL Generator/Reflector 链和通用 AI Tutor 页面。目标词必须来自当天真实复习并确定性排序。

### 2. 语言与难度

- 学习语言：`fr / en / ja / de / es / ru / zh`。
- 反馈语言：`zh / fr / en`。
- 服务端 code 是权威，客户端显示名不参与判断。
- v1 不增加 CEFR、HSK 或 JLPT 设置，不伪装成个性化等级。
- 统一生成清晰学习者短文：一个连贯日常场景、4–6 个短句；除目标词外尽量高频自然，避免生僻
  习语和复杂嵌套。

### 3. Provider-safe 输入快照

生成路由不得接受客户端任意词 ID。日内摘要服务确定 3–5 个目标词，并按顺序分配临时键
`t1`–`t5`。每项只发送：

```json
{
  "key": "t1",
  "surface": "s'effondrer",
  "part_of_speech": "v.",
  "meaning": "倒塌；崩溃"
}
```

确定性规则：

- 先按 `Definition.id` 选择主释义记录：优先第一条 meaning 非空的记录，否则第一条记录。
- `surface` 最多 200 字符，`part_of_speech` 最多 50，`meaning` 最多 400。
- 词性与释义必须来自同一条主释义记录；不存在时传空字符串。
- 不发送例句、笔记、阅读来源、SessionPad 原文、评分、用户资料或数据库 ID。

输入哈希覆盖契约版本、目标/反馈语言 code 和按顺序规范化的完整快照。真正参与提示词的字段变化
才击穿缓存。

### 4. 固定 JSON 输出

调用现有 `general` provider 链并使用 JSON mode：

```json
{
  "title": {
    "target": "目标语言标题",
    "translation": "反馈语言标题"
  },
  "sentences": [
    {
      "target": "目标语言句子",
      "translation": "对应译文",
      "terms": [
        {
          "key": "t1",
          "target_form": "s'est effondré",
          "translation_form": "崩塌了"
        }
      ]
    }
  ]
}
```

- 双语标题均非空且最多 120 字符。
- `sentences` 必须为 4–6 项；每组 target/translation 均非空。
- 整个 JSON 序列化后最多 12,000 字符。
- 不允许 Markdown、HTML、额外顶层字段或模型解释。
- 每个输入 key 在全部 term anchors 中恰好出现一次；禁止未知、重复或空锚。

### 5. 自然词形与双语锚点

目标语言故事使用自然词形，反馈语言译文高亮自然对应译法，不机械重复外语原词。服务端对可见文本
做 Unicode NFKC、大小写、空白和常见撇号折叠后，验证 `target_form` 和 `translation_form` 分别是
所在句子的真实子串，每个临时键恰好一个锚。

再做粗粒度文字系统守卫：中文应含汉字，日语应含假名或汉字，俄语应含西里尔字母，法/英/德/西
语以拉丁字母为主。它只拦明显串语言，不宣称为精确语言识别，也不增加第二个 AI 裁判。

### 6. 单次调用与严格拒绝

一次点击产生一次逻辑尝试；provider failover 仍算同一次。JSON、结构、长度、key 或锚点任一校验失败，
整篇失败：不展示半成品、不缓存为 ready、不在后台偷偷调用第二次 AI 修复。

稳定错误码包括：

- `provider_unavailable`
- `invalid_json`
- `invalid_schema`
- `missing_or_duplicate_term`
- `term_anchor_mismatch`
- `result_too_large`
- `lease_expired`

模型产生了可计量响应但格式无效时仍记录实际 token，并消耗一次逻辑尝试。用户只看到本地化错误，
明确复习记录不受影响。

### 7. 缓存、尝试与并发

缓存身份：

`(user_id, local_date, target_language, feedback_language, contract_version, input_hash)`

- 同一输入最多一个 ready 结果。
- 最多两次逻辑尝试：首次生成和一次用户主动重试。
- ready 缓存读取不限次数，不调用 AI、不增加尝试或 token。
- v1 不新增跨输入的每日故事总数；闭测先观察 token。

状态机在行锁下取得或创建 run。ready 直接返回；未过期 pending 返回生成中；可重试 failed 或租约
过期 pending 取得新的 attempt version，提交事务后才调用 LLM。完成时只有仍持有该 attempt version
的执行者能写 ready/failed，防止旧 worker 覆盖新结果。

pending 租约为 60 秒。它高于正常 25 秒总 deadline，只用于进程中断恢复。第二次仍失败或悬挂后，
该输入停止调用 provider。

### 8. 超时与降级

复用现有 LLM 基座：单 provider 10 秒、整条 failover 25 秒、现有熔断器。v1 不增加队列、SSE、
Redis、流式 JSON 或第三套熔断器。全部 provider 不可用或超时只让回执失败，不影响复习、回词库或
现有写作路径。

故事是私有、临时、不可发布的学习脚手架，不调用公开内容 NSFW provider。未来若允许公开，再单独
定义发布审核。

### 9. 进入现有造句

ready/cached 回执显示目标词。用户选择后发送 `story_run_id + term_key`，服务端验证：

- run 属于当前用户且 ready；
- term key 存在于该 run 快照；
- 对应词仍属于该用户和学习语言。

通过后进入现有造句、批改和显式保存流程。不得信任客户端直接提交的 `word_id`。正文已清理、run
越权、词删除或语言不匹配时，不泄露存在性，安全回退到普通造句推荐。

故事不写入 `OutputEntry`；用户确认保存的句子才是长期资产。

### 10. 保留期限与观察

故事正文、标题、词面快照和锚点最多保留 7 天，不提供历史。失败只保留稳定错误码，不保留 provider
原始响应。长期事件仅记录不含正文的 eligibility、started/ready/failed/cache hit、writing handoff
和 output saved。管理员不得读取故事、译文、目标词或用户句子。

## Minimum acceptance matrix

1. 七种目标语言和三种反馈语言都能构建固定提示词。
2. 3/4/5 个词产生稳定临时键与哈希。
3. provider payload 不含例句、笔记、来源、评分和数据库 ID。
4. 合法双语 JSON、自然词形与译文锚通过。
5. 非 JSON、额外字段、句数越界、未知/重复/缺失 key、空锚、锚不在句中及超长结果失败。
6. 无效结果不部分展示、不 ready、不隐藏二次调用。
7. 相同输入并发只调用一次；缓存命中不调用；失败最多一次主动重试。
8. 租约接管和 attempt version 阻止旧 worker 覆盖。
9. provider 全挂不影响复习完成。
10. 跨用户 run、伪造 term key、删除词和跨语言词不能进入指定词造句。
11. story run 的 SELECT/INSERT/UPDATE/DELETE 均受 FORCE RLS。
12. 正文清理不删除长期无正文事件。

## Implementation boundary

本决议只定义生成契约。实施顺序和测试门由
`11-observation-and-final-implementation-roadmap.md` 固定，第一张代码票为 RS1 数据地基与日内摘要。

