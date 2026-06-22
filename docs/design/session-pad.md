# 会话输入板（Session Pad）详细设计

> 记录日期：2026-06-22
> 状态：详细设计完成，P1 实现范围已定义

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
会前：打开语言伙伴档案，看上次聊了什么、上次记了哪些词
    ↓
创建 Session → 选择/新建语言伙伴 → 生成链接
    ↓
对方打开链接（无需注册，输入昵称即可加入）
    ↓
双方实时追加条目：词、短语、句子、备注
    ↓
会话结束 → 生成 intake_source → 跳转 /extract
    ↓
各自筛选词 → commit 入库 → SRS 排程
    ↓
这段对话永久绑定在语言伙伴关系下，下次见面前可回顾
```

---

## 场景优先级

| 场景 | 摩擦度 | 优先级 |
|---|---|---|
| **线上语言交换**（视频通话同时开一个标签）| 低 | **P1 主打** |
| **线下会后回顾**（聊完后一起打开，回忆生词）| 中 | P2 |
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

每条独立，不冲突，天然适合后续 /extract 处理。

### 2. Guest 免注册加入

对方无需注册 RemeMate 即可加入会话。否则「让语言伙伴先注册」这一步会直接杀死使用场景。

- Owner（创建者）：必须是 RemeMate 登录用户
- Guest：打开链接，输入昵称即可加入，可写条目
- 会后入库：P1 只有 owner 能入库；guest 若想入库，引导注册（增长钩子）

### 3. 会前上下文：打破永远重置

创建新 session 时，若选择已有语言伙伴：
- 显示上次会话日期和话题
- 显示上次共同记录的词
- 高亮其中 owner 仍未掌握的词（SRS 还在队列）

这一屏是记搭最有温度的功能点，直接解决痛点 1 和痛点 2。

### 4. 语言伙伴档案（Partner Profile）

每个语言伙伴有一个简单档案页，记录这段关系的全部历史：
- 认识多久、见过几次
- 共同记录过的词/表达总数
- 这段关系带来的词中，哪些已掌握、哪些还在复习
- 对方母语 / 目标语言
- 历次 session 列表

这是社交留存的核心钩子——用户不舍得离开，因为关系数据在这里。

### 5. 词汇来源溯源

从 Session Pad 入库的词，`intake_source.type = session_pad`，保留 `room_id` 引用。

用户在复习这个词时，可以看到「这个词是 2026-06-15 和 Léa 聊天时记的」。

/write 造句时，如果这个词来自某次 Session，造出来的句子可以在广场标注来源「来自和 @Léa 的对话」。

---

## 会话生命周期

| 状态 | 说明 |
|---|---|
| active | 创建后，双方可实时编辑 |
| ended | owner 点击「结束」后，跳转 /extract；之后只读 |
| expired | 创建后 7 天内未结束自动过期；guest 链接失效 |

**记录保存**：ended/expired 的 session 记录默认保存 30 天，owner 可手动删除，不公开，不进社交 feed。

**多人上限**：P1 仅支持 owner + 1 guest（双人语言交换）；P2 扩展至小组（≤4人）。

---

## P1 范围（明确边界）

**P1 做**：
- 创建 session，绑定/新建语言伙伴
- 生成分享链接，guest 免注册加入
- 追加式条目流 + WebSocket 实时同步
- 会前上下文：显示上次记录的词
- 会后跳转 /extract，生成 intake_source
- Owner 入库闭环
- 语言伙伴档案页（基础版）
- session 记录保存 30 天

**P1 不做**：
- 语音转录
- 富文本 / 协作文档
- 多人小组（>2人）
- guest 直接入库
- typing 状态显示
- 实时抽词（会中 AI 提取）
- 多设备同步（同一用户多 tab）
- 语言伙伴关系图谱

---

## 进化路径

| 阶段 | 内容 | 技术难度 |
|---|---|---|
| **P1** | 追加式协作记录 + 伙伴关系 + 会后 /extract | 中 |
| **P2** | 单人语音转录 + 自动抽词；guest 入库；小组模式 | 中 |
| **P3** | 双人实时转录 + 各自抽词（diarization）| 高——真正的市场空白 |

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
language_partners                               ← 语言伙伴关系（P1 新建）
  id, owner_user_id FK, guest_user_id FK nullable,
  guest_name, target_language_code, native_language_code,
  first_met_at, session_count, created_at

session_rooms                                   ← 会话房间
  id, owner_user_id FK, partner_id FK,
  room_token, title,
  status: active / ended / expired,
  created_at, ended_at, expires_at

session_participants                            ← 参与者
  id, room_id FK, user_id FK nullable,
  guest_name, guest_token,
  role: owner / guest,
  joined_at, last_seen_at

session_entries                                 ← 条目流（核心）
  id, room_id FK, participant_id FK,
  entry_type: word / phrase / sentence / note,
  text, translation, note,
  created_at, updated_at, deleted_at
```

**会话结束后生成**：
```
intake_sources
  type = session_pad
  source_ref_id = session_room.id
  raw_text = 合并 session_entries
  title = session title + partner name
  language_hint = target_language_code
```

---

## 与句子广场的联动

/write 造句时，若触发词来自某次 Session Pad（`intake_source.type = session_pad`），造出来的句子可在广场标注「来自和 @伙伴昵称 的对话」，让社交属性有真实温度，不只是陌生人之间的投票。
```
