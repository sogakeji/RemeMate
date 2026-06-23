# 会话输入板（Session Pad）详细设计

> 记录日期：2026-06-22
> 状态：详细设计完成，**P2 功能**（推迟至用户量 50-100 后上线）

> **⚠ 编号约定（重要）**：本文撰写早于「Session Pad 推迟至 P2」的决策，正文中残留的 `P1a / P1b / P1.5` 等标签，指的是 **Session Pad 自身的内部开发阶段**（先做主闭环、再做关系记忆增强），**不代表全局产品路线图位置**。整个 Session Pad 在全局路线图上是 **P2**；全局阶段编号以文末「进化路径」表（P2a / P2b / P3 / P4）为准。阅读时把内部的 P1x 一律理解为「Session Pad 上线后的第 x 个内部阶段」。

---

## 一句话定义

语言交换时双方共同打开一个实时协作输入板，随手记录生词和好表达，会话结束后跳转 /extract 各自选词入库，打通「真实对话 → SRS 词库」的闭环。每次会话都绑定语言伙伴关系，让对话有记忆、有积累、有温度。

---

## 品牌故事：三个痛点

语言交换是最有效的口语练习方式之一，但它有三个反复出现的痛点：

**痛点 1：永远重置**
每次见面重新自我介绍、重新问对方学什么语言、重新建立话题。关系没有积累，每次都是第一次。

**痛点 2：人脸盲**
不记得这个人上次聊过什么，说过哪些有意思的话，聊到哪些话题。下次见面无法深入，对话永远停留在表面。

**痛点 3：词汇蒸发**
对话中对方教了你一个词，你教了对方一个词，说了很多好句子——会后全忘。没有工具把真实对话里的词沉淀下来。

> 普通背词 App 帮你记住词。记搭帮你记住——这个词是谁教你的，在哪次对话里出现的，你们当时在聊什么。

---

## 产品定位

Session Pad 是记搭最有品牌辨识度的**差异化输入端**，不是造句输出页，不是单人练习台，不是通用协作文档。

它解决的核心问题不是「我怎么练这个词」，而是「我在和真人对话时遇到的词，怎么不丢」。

**与其他功能的分工**：

| 功能 | 角色 | 触发场景 |
|---|---|---|
| Session Pad | 对话捕捉（输入端） | 和真人语言交换时 |
| /extract | 抽词处理器 | Session 结束后 |
| /write 造句 | 主动输出（输出端） | SRS 到期词触发 |
| 句子广场 | 社交展示 | 造句公开后 |
| SRS | 复习调度 | 词库里的词到期 |

---

## 核心产品逻辑

**以「语言伙伴」为核心对象，不是以「会话」为核心。**

用户的心智模型不应该是「我开了 N 次会话」，而是「我和 Léa 见过 5 次，聊过这些话题，学了这些词，下次见面我要把上次没掌握的词用出来」。

这是记搭区别于所有普通背词工具的根本差异：词汇有来源，来源是人，人有关系，关系有历史。

---

## 功能流程

```
会前：打开语言伙伴卡片，看上次聊了什么、上次入库的词、待处理的记录
    ↓
创建 Session → 选择/新建语言伙伴（只填昵称+语言）→ 生成链接
    ↓
对方打开链接（无需注册，输入昵称即可，3秒内进入）
    ↓
双方实时追加条目：词、短语、句子、备注
    ↓
会话结束 → 生成 session summary → 生成 intake_source → 跳转 /extract
    ↓
owner 筛选词 → commit 入库 → SRS 排程 → word_occurrences 记录 partner 来源
    ↓
原始条目保存 30 天；会话摘要 + 入库词来源永久绑定在语言伙伴关系下
```

---

## 场景优先级

| 场景 | 摩擦度 | 优先级（Session Pad 内部）|
|---|---|---|
| **线上语言交换**（视频通话同时开一个标签）| 低 | **首发主打** |
| **线下会后回顾**（聊完后一起打开，回忆生词）| 中 | 后续增强 |
| **线下实时输入**（聊天同时低头打字）| 高 | 暂不主推 |

---

## 关键设计决策

### 1. 追加式条目流，不是共享文本编辑器

**不做**：两人同时编辑一个大 textarea（光标冲突、patch/merge、断线恢复，P1 成本极高）

**做**：像聊天记录一样追加独立条目，每条是一个 `session_entry`，实时广播新增/编辑/删除。

```
[A] avoir hâte de — 期待做某事
[B] You can say: J'ai hâte de te revoir.
[A] se rendre compte de — 意识到
[B] 例：Je me suis rendu compte que j'avais oublié mon sac.
```

每条独立，不冲突，天然适合后续 /extract 处理。Entry type 默认不强制选择，用户可事后补填类型。

### 2. Guest 免注册加入

对方无需注册 RemeMate 即可加入会话。否则「让语言伙伴先注册」这一步会直接杀死使用场景。

- **Owner**（创建者）：必须是 RemeMate 登录用户
- **Guest**：打开链接，输入昵称即可加入（目标：3秒内进入），可写/编辑/删除自己的条目
- **会后入库**：P1 只有 owner 能入库；guest 若想入库，引导注册（增长钩子）
- **Guest 条目权限**：active 期间可编辑/删除自己创建的条目；session ended 后链接只读

**Guest 隐私提示**（加入页显示）：
> 本会话记录对创建者可见，并可能被保存到其个人词库。建议使用昵称加入，不要输入敏感信息。

### 3. 会前 Partner Context Card：打破永远重置

创建新 session 时，若选择已有语言伙伴，显示 **Partner Context Card**：

- 上次会话日期和话题
- 上次已入库的词（只显示已 commit 到 words 的词）
- 高亮其中 owner 仍未掌握的词（SRS 还在队列）
- **待处理提醒**：若上次 session 结束但未做 /extract，显示「上次会话还有 N 条记录未抽词，是否继续处理？」

这一屏是记搭最有温度的功能点，直接解决痛点 1 和痛点 2。

**数据来源规则**：
- 只显示已 commit 的入库词（不显示未处理 candidates，避免状态混乱）
- 若上次无 AI summary，显示最近 5 条 session_entries 作为摘要

### 4. Partner Context Card vs Partner Profile

| | P1 | P1.5 |
|---|---|---|
| **Partner Context Card** | ✅ 创建 session 前显示 | — |
| **Partner 列表页** (/partners) | ✅ 基础列表：昵称、语言、上次见面、会话数、词数、待处理数 | — |
| **Partner Profile 页** (/partners/<id>) | ✅ 基础信息 + 最近会话摘要 + 待处理 sessions + 开始新 session | — |
| **完整词汇统计**（已掌握/复习中）| — | ✅ P1.5 |
| **历次 session 美化列表** | — | ✅ P1.5 |

Partner Profile 基础版 P1 做，完整统计和美化 P1.5 再补。

### 5. 未处理 Session 提醒机制

用户结束会话后不立即抽词是高概率事件。首页和 Partner 列表都显示 pending extract：

```
[首页提示] 你有 2 个会话待抽词：
  · 和 Léa 的 6/15 会话：12 条记录
  · 和 Marco 的 6/20 会话：8 条记录
  [继续处理 →]
```

`session_rooms.extract_status` 驱动这个显示：`not_started` → 显示提醒；`committed` → 不显示。

### 6. 词汇来源溯源链

从 Session Pad 入库的词，溯源链完整保留：

```
word → word_occurrences → intake_source → session_room → language_partner
```

用户复习这个词时可以看到「2026-06-15 和 Léa 聊天时记的」。

`word_occurrences` 冗余存 `partner_id`，避免每次溯源都要多层 JOIN。

### 7. 句子广场联动（默认匿名）

/write 造句时，若触发词来自 Session Pad，广场标注默认匿名：
- **默认**：「来自一次法语语言交换」
- **Owner 手动开启**：「来自和 Léa 的对话」（使用 owner 私有 display_name，不用 @注册名，guest 未注册时不暴露任何身份）

P1 字段预留，展示逻辑默认匿名；P2 开放 owner 手动选项。

---

## 会话生命周期

| 状态 | 说明 |
|---|---|
| active | 创建后，双方可实时编辑 |
| ended | owner 点击「结束」后生成 summary + intake_source，跳转 /extract；之后只读 |
| expired | 创建后 7 天内未结束自动过期；guest 链接失效 |

**双层保存**（解决"关系记忆"与"隐私"的矛盾）：

| 内容 | 保存时长 | 说明 |
|---|---|---|
| 原始 session_entries | 30 天后清理 | 隐私保护，存储控制 |
| 会话摘要（summary） | 永久，owner 可删 | 支持"上次聊了什么"回顾 |
| 入库词来源（word_occurrences.partner_id）| 永久 | 支持词汇溯源到人 |
| 语言伙伴关系（language_partners）| 永久，owner 可 archive | 关系记忆核心资产 |

**多人上限**：P1 仅支持 owner + 1 guest；P2 扩展至小组（≤4人）。

---

## P1 实施顺序（P1a → P1b）

### P1a：主闭环验证
- Auth + Postgres + Word/SRS 基础
- Guest 免注册加入
- 追加式条目实时同步（WebSocket）
- 会后生成 intake_source → 跳转 /extract → owner 入库

### P1b：关系记忆增强
- language_partners 表 + Partner 列表页
- Partner Context Card（会前上下文）
- 未处理 session 提醒
- Partner Profile 基础页
- word_occurrences partner 溯源

P1a 验证「用户愿意用 Session Pad 记录」后，P1b 让记录有积累价值。

---

## P1 范围边界

**P1 做**：
- 创建 session，绑定/新建语言伙伴（只填昵称+语言）
- 生成分享链接，guest 免注册加入
- 追加式条目流 + WebSocket 实时同步
- 会话摘要生成 + 双层保存
- 会前 Partner Context Card
- 未处理 session 提醒
- 会后跳转 /extract，生成 intake_source
- Owner 入库 + word_occurrences partner 溯源
- Partner 列表页 + Profile 基础页
- Guest 隐私提示 + 条目权限

**P1 不做**：
- 语音转录
- 富文本 / 协作文档
- 多人小组（>2人）
- guest 直接入库
- typing 状态显示
- 会中实时抽词
- 多设备同步（同一用户多 tab）
- Partner 完整词汇统计 / 历次 session 美化
- 广场联动 partner 公开标注（字段预留，展示 P2）

---

## 进化路径

| 阶段 | 内容 | 技术难度 |
|---|---|---|
| **P2a**（首发）| 主闭环：guest 加入 + 实时同步 + 会后入库 | 中 |
| **P2b** | 关系记忆：partner context + 溯源 + 待处理提醒 | 低 |
| **P3** | 语音转录；guest 入库；小组模式；广场联动 partner 标注 | 中 |
| **P4** | 双人实时转录 + 各自抽词（diarization）| 高——真正的市场空白 |

---

## 市场定位

现有产品（VoiceLingua 等）聚焦单人转录、单人背词或通用协作文档；多人语言交换场景下「协作记录 → 各自抽词 → SRS 入库 → 伙伴关系沉淀」的完整链路，目前较少见，是记搭的差异化假设，需 P1 验证。

---

## WebSocket 技术边界

**只做最小同步**，不做富文本协作：

Socket.IO 事件：
```
join_room       — 加入房间
leave_room      — 离开房间
create_entry    — 新增条目（广播给所有人）
update_entry    — 编辑条目
delete_entry    — 删除条目
presence_ping   — 在线状态心跳
```

**持久化以 Postgres 为准**，WebSocket 只做广播。客户端断线后重新拉取 `session_entries`，不依赖内存状态。

P1 单机 gevent + Flask-SocketIO，不上 Redis adapter，不做多节点。

---

## 数据模型

```
language_partners                               ← 语言伙伴关系
  id
  owner_user_id FK
  guest_user_id FK nullable                     ← 对方注册后可关联
  display_name                                  ← owner 私有备注名（如"Léa - 法国建筑师"）
  guest_name                                    ← 对方在 session 中使用的昵称
  target_language_code                          ← owner 正在学的语言
  native_language_code nullable
  notes                                         ← owner 私有备忘
  first_met_at
  last_session_at
  session_count
  archived_at nullable
  created_at
  updated_at

session_rooms                                   ← 会话房间
  id
  owner_user_id FK
  partner_id FK
  room_token                                    ← 足够随机的分享 token
  title
  topic nullable
  status: active / ended / expired
  summary nullable                              ← 会后生成，长期保留
  extract_status: not_started / generated / committed
  intake_source_id FK nullable                  ← 关联生成的 intake_source
  created_at
  ended_at nullable
  expires_at
  raw_entries_deleted_at nullable               ← 原始条目清理时间戳

session_participants                            ← 参与者
  id
  room_id FK
  user_id FK nullable                           ← 已注册用户
  guest_name
  guest_token                                   ← uuid4，httponly cookie，与 room_token 分开
  role: owner / guest
  joined_at
  last_seen_at

session_entries                                 ← 条目流（核心）
  id
  room_id FK
  participant_id FK
  entry_type: word / phrase / sentence / note
  language_code nullable                        ← 双语交换时条目可能属于不同语言
  text
  translation nullable
  note nullable
  tags_json nullable
  created_at
  updated_at
  deleted_at nullable                           ← 软删除，guest 可删自己的条目
```

**会话结束后生成**：
```
intake_sources
  type = session_pad
  source_ref_id = session_room.id
  raw_text = 合并 session_entries（deleted_at IS NULL）
  title = session title + partner display_name
  language_hint = target_language_code
```

**入库词溯源**（word_occurrences 冗余 partner_id）：
```
word_occurrences
  id
  word_id FK
  intake_source_id FK
  source_ref_type: session_pad / extract / csv / quick_add
  source_ref_id
  partner_id FK nullable                        ← 冗余，避免多层 JOIN
  context_text
  context_translation nullable
  created_at
```

---

## /extract 衔接流程

```
1. Owner 点击「结束会话」
2. 后端合并 session_entries → raw_text
3. 生成 session summary（AI 可选，P1 也可跳过直接用 top 5 条目）
4. 创建 intake_source(type=session_pad, source_ref_id=room.id)
5. 更新 session_rooms.extract_status = generated
6. 跳转 /extract/source/<source_id>
7. 用户确认候选词 → commit
8. commit 时写 word_occurrences，填入 partner_id
9. 更新 session_rooms.extract_status = committed
```

---

## UI 形态参考

**桌面三栏**：
```
左侧：Partner Context Card
  · 上次聊了什么（摘要/最近5条）
  · 上次入库词（未掌握高亮）
  · 待处理提醒

中间：Entry Stream（主区域）
  · 双方条目追加流
  · 底部快捷输入框
  · Enter 发送，type 可后填

右侧：Session Actions
  · 复制链接
  · 在线状态
  · 结束并抽词
```

**移动端**：Entry Stream + 输入框为主，Partner Context 折叠；追加式条目流天然适合移动端单手操作。
