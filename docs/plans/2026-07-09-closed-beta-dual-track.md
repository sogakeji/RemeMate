# 双轨制闭测功能完善与开发验证计划

> 日期：2026-07-09
> 状态：Draft，等待用户审核；本文件只做规格和计划，不代表已开始写代码。
> 关联：`docs/strategy/2026-07-09-three-month-focus.md`、`docs/design/session-pad.md`、`docs/BACKLOG.md`

## Problem Statement

RemeMate 已进入闭测基线。当前产品同时面临两类需求：

1. 主线必须证明用户会因为“自己真实遇到的词和句子被 RemeMate 帮他记住并用出来”，而每天回来。
2. SessionPad 作为特色功能，需要在闭测期间和真实语伴共同验证吸引力。

这两类需求不能混在一起随手开发。否则会出现三个风险：

- 闭测主线被大功能拖慢，硬 bug 和日常体验没压实。
- SessionPad 被做成聊天室、协作文档或社交产品，偏离语言学习复盘。
- 每个小需求都扩大测试面，导致回归成本失控。

## Solution

采用双轨制：

- **A 轨：日常复习 + 输出闭环补强**。优先让现有闭测版更稳定、更会把用户带回学习。
- **B 轨：SessionPad 小切片验证**。只做真实语伴复盘的最小闭环，用行为验证吸引力。

两条轨道共享原则：

- AI 是增强层，不是保存、记录、入库、推送的门禁。
- 软 bug 和体验想法先入 BACKLOG，按批次处理。
- 每个切片都必须说明测试范围，避免无谓全量回归。
- 不做 guest，不做实时协作，不做聊天室，不做完整社交。

## Success Metrics

### A 轨成功标准

- 闭测用户可以稳定完成：收词 → 候选审核 → 入库 → 复习 → 造句 / 三行日记 → 保存 / 批改。
- Bark 至少支持测试推送和一个真实调用点，失败时用户知道发生了什么。
- 阅读收词加入后，用户知道词去了哪里；候选审核和词库详情能看到轻量来源。
- AI 不可用时，核心保存链路不崩、不误扣关键额度、不让用户陷入无反馈状态。

### B 轨成功标准

- 至少完成 2-3 次真实语言交换复盘。
- 至少有一次对方点击感谢，或把收到的某条表达 / 修正加入自己的候选词。
- 若用户只把它当个人笔记、对方没有参与，或内容不能进入学习闭环，则不继续扩展大功能。

## User Stories

1. As a closed beta learner, I want RemeMate to keep my daily review and writing flow reliable, so that I can trust it as my language memory system.
2. As a learner, I want Bark settings to be saved and testable, so that I know reminders can reach my device.
3. As a learner, I want a failed Bark test to show a clear error, so that I can fix the address instead of guessing.
4. As a learner with due words, I want to receive a review reminder, so that I return before forgetting words.
5. As a learner importing or collecting words, I want non-critical AI failures not to destroy my original input, so that I can retry later.
6. As a reader, I want “加入学习” to keep me in the reader and confirm the word entered candidates, so that reading is not interrupted.
7. As a reader, I want a lightweight “去审核” entry after adding words, so that I can review candidates when ready.
8. As a candidate reviewer, I want reading candidates to show source document and original sentence, so that I can remember where the word came from.
9. As a word-library user, I want word detail to show reading source when available, so that the word stays connected to real context.
10. As a closed beta tester, I want soft issues to be collected instead of immediately changing behavior, so that the product stays stable during testing.
11. As a language-exchange learner, I want to create a language partner record, so that I can organize exchange notes around a real person.
12. As a learner, I want to create a SessionPad for one partner, so that each exchange has a structured recap.
13. As a learner, I want a “帮自己记” column, so that expressions I learned from my partner can enter my own learning loop.
14. As a learner, I want a “帮他记” column, so that I can record corrections and useful expressions for my partner.
15. As a learner, I want private partner notes to stay private, so that sensitive relationship context is not accidentally shared.
16. As a learner, I want to choose which “帮他记” items go into a feedback packet, so that sharing is deliberate and item-level.
17. As a partner, I want to receive a stable feedback packet, so that later edits to the sender's private pad do not change what I received.
18. As a partner, I want to click “感谢”, so that I can acknowledge the effort without starting a chat thread.
19. As a partner, I want to add a received expression or correction to my own candidate review, so that feedback becomes my learning material.
20. As a learner, I want unclaimed partner records before my partner registers, so that I can record real exchanges first.
21. As a partner, I want to log in before seeing feedback packets, so that my received learning material belongs to my account.
22. As a system owner, I want SessionPad to avoid guest access, so that privacy, ownership, and candidate adoption stay clear.
23. As a closed beta observer, I want to count completed recaps, sent packets, thanks, and adoptions, so that SessionPad is judged by behavior rather than vibes.
24. As a developer, I want each slice to use existing service-layer patterns, so that RLS and multi-user isolation stay consistent.
25. As a developer, I want SessionPad tests to assert ownership boundaries, so that users cannot see or mutate other users' pads or packets.

## Implementation Decisions

### A 轨：日常复习 + 输出闭环补强

1. **Bark 不从零做。** 当前已有设置页、URL 校验、保存、测试发送、用户设置字段和相关测试。下一步补的是可用闭环：真实调用点、失败记录/提示、幂等。
2. **Bark 发送逻辑应从 `words` 服务中逐步抽出或包一层通知服务。** 设置仍可由现有 settings 路由保存；发送调用点不要散落在路由模板里。
3. **首个真实 Bark 调用点优先选复习提醒。** 它最贴近三个月目标。每日摘要和导入完成可以作为后续调用点，不抢第一版。
4. **Bark 必须保留 SSRF 防护和二次校验。** 当前 `_validate_push_url` 的安全口径不能倒退。
5. **阅读收词只做去向感和来源感。** 加入候选后默认留在阅读器；候选审核和词库详情显示 `来自《文档名》` + 原文句子。
6. **阅读收词不扩展成阅读器。** 不做 EPUB/OCR/章节/书签/统计/回到原文位置。
7. **AI 降级作为主线稳定性原则处理。** 涉及造句、三行日记、文本抽词时，保存和原始内容保留优先于批改/抽词质量。

### B 轨：SessionPad 小切片验证

1. **入口归属：`我的 → 语言伙伴 → 复盘`。** 不放进广场，不放进词库入口，不伪装成聊天。
2. **必须登录。** 反馈包、感谢、采纳、候选词入库都绑定真实用户关系；不做 guest 链接。
3. **允许未绑定伙伴。** 用户可先创建伙伴档案；但对方看反馈包、感谢、采纳时必须绑定真实 RemeMate 账号。
4. **首版保持一人一张信纸。** 不做共同编辑，不做同步文档，不做 WebSocket。
5. **数据结构围绕四个核心概念：语言伙伴、复盘信纸、复盘条目、反馈包。**
6. **复盘条目必须分栏。** `帮自己记` 可以进入自己的候选词；`帮他记` 可以进入反馈包；两者不能混用。
7. **私人伙伴笔记默认私有且不能进入反馈包。** 任何共享都必须是条目级选择。
8. **反馈包是快照。** 发送后稳定存在，后续修改原始信纸不改变已发送包。
9. **收到反馈包后的动作只做查看、感谢、采纳到候选词。** 不做已读/忽略/评论/回复线程。
10. **AI 总结不进首个最小闭环。** 可以预留后续，但第一版不能依赖 AI 才能保存、推送或采纳。
11. **成功指标要在系统内可观察。** 至少能统计：复盘创建数、反馈包发送数、感谢数、采纳数。

## Proposed Development Slices

### Slice 0：收口当前文档与分支

- 审核并提交当前文档更新。
- 确认 `master` 工作区干净后再开功能分支。
- 建议分支名：`closed-beta-dual-track-plan` 只用于文档；实现分支另开。

验收：

- 文档明确双轨制、SessionPad 成功标准、登录要求和不做范围。
- 不包含业务代码改动。

### Slice A1：Bark 可用闭环 v1

- 保留现有设置页保存和测试发送。
- 建立统一通知发送服务或最小包装层。
- 增加复习提醒调用点。
- 记录幂等键，避免重复推送。
- 明确失败行为：不影响复习，不让页面 500，必要时记录日志。

验收：

- 用户能保存 Bark 地址，发送测试，看到成功/失败。
- 有到期复习内容时，可以触发一次复习提醒。
- 私网/localhost Bark URL 仍被拒绝。

### Slice A2：阅读收词去向感 + 来源感

- 阅读器中点击加入学习后，保持在阅读器。
- 给用户轻提示：已加入本篇候选词。
- 提供轻量去候选审核入口。
- 候选审核页对阅读来源显示来源文档和原文句子。
- 词库详情页显示轻量来源。

验收：

- 用户不会被加入动作打断阅读。
- 阅读候选审核时能看到来源。
- 首页复习卡不显示来源。

### Slice A3：AI 不可用体验审查

- 只审核心流程：造句、三行日记、文本抽词。
- 明确哪些失败应保存原始内容，哪些失败应返回友好提示。
- 修硬 bug；软体验入 BACKLOG。

验收：

- AI 不可用不导致 500。
- 不出现“用户以为正在批改但实际无结果”的悬空状态。
- 不因失败误扣关键额度。

### Slice B1：语言伙伴基础

- 创建、查看、编辑语言伙伴。
- 支持未绑定伙伴档案。
- 预留绑定真实账号的状态，但不做公开邀请链接。

验收：

- 用户只能看到自己的伙伴。
- 未绑定伙伴不会让对方看到任何内容。
- 伙伴页可以进入复盘列表。

### Slice B2：复盘信纸 v1

- 围绕一个伙伴创建复盘。
- 两栏结构：帮自己记 / 帮他记。
- 支持保存条目。
- 私人伙伴笔记只存在帮自己记侧，不可分享。

验收：

- 用户能完成一次真实语言交换复盘记录。
- `帮自己记` 与 `帮他记` 在数据和 UI 上明确分离。
- AI 不可用不影响保存。

### Slice B3：反馈包 v1

- 从 `帮他记` 条目中选择内容。
- 发送给已绑定真实账号的伙伴。
- 生成快照包。
- 收件人可查看。

验收：

- 未绑定伙伴不能接收反馈包。
- 发送后修改原复盘，不改变已发送反馈包。
- 发送者不能把 `帮自己记` 或私人笔记误发出去。

### Slice B4：感谢与采纳

- 收件人点击感谢。
- 收件人把某条表达 / 修正加入自己的候选词审核。
- 系统记录感谢和采纳，用于闭测成功判断。

验收：

- 至少能完成：发送反馈包 → 对方感谢。
- 至少能完成：发送反馈包 → 对方采纳到候选词。
- 采纳进入候选审核，不直接写入词库。

### Slice B5：闭测观察面板或最小统计

- 不做复杂 analytics。
- 只提供管理员可查的最小行为计数：复盘数、反馈包数、感谢数、采纳数。

验收：

- 能判断是否达到 2-3 次真实复盘 + 至少一次感谢/采纳。
- 不暴露用户私密复盘内容。

## Testing Decisions

### 测试原则

- 测外部行为，不测模板内部实现细节。
- 服务层优先，路由集成补关键用户路径。
- 权限/隔离/发送/采纳相关测试必须覆盖多用户边界。
- 文档和纯 CSS 不跑全量；服务层、数据库、权限、AI 降级变更跑相关测试 + 必要时全量。

### A 轨测试接缝

- Bark 设置与测试：沿用 `test_settings_language.py` 风格，mock HTTP 请求，断言保存、拒绝私网 URL、发送失败提示。
- Bark 真实调用点：新增通知服务测试，mock 发送，断言幂等与不阻断主流程。
- 阅读收词：沿用 `test_reading_lookup_candidate.py`、`test_reading_routes.py`，断言加入候选后页面状态、候选来源、词库详情来源。
- AI 降级：沿用 `test_write.py`、`test_intake.py`、`test_llm.py`，断言不可用时保存/提示/额度行为。

### B 轨测试接缝

- 伙伴基础：新增 partner/service 集成测试，断言用户只能管理自己的伙伴。
- 复盘信纸：服务层测试两栏条目保存、私有字段不可分享。
- 反馈包：集成测试发送者/收件人权限，断言快照不可被原文修改影响。
- 感谢与采纳：集成测试收件人点击感谢、采纳进入候选审核，不直接入词库。
- RLS/多用户：对 SessionPad 新表必须有 RLS 或等价隔离测试；至少覆盖跨用户读取/修改失败。

## Out of Scope

本计划明确不做：

- SessionPad guest 免登录。
- 聊天室、小组交换、公开分享链接。
- WebSocket、实时协作、共同编辑。
- 已读、忽略、评论、回复线程。
- AI 自动决定是否保存、推送、入库。
- 完整阅读器路线：EPUB、OCR、章节、书签、阅读统计。
- Daily Task Card v2 / Bingo。
- 广场重社交化。
- 新增更多收词方式。
- 大规模 UI 重做。

## Risk Review

- **测试面膨胀**：SessionPad 会引入新表和权限边界，必须分 B1-B5 切片，不应一次性实现。
- **隐私误发**：私人伙伴笔记必须从数据模型上排除反馈包。
- **关系绑定复杂**：闭测版可先用管理员创建账号 + 用户手动绑定，避免公开邀请链接。
- **AI 脆弱性**：AI 总结不进入最小闭环，避免外部 API 影响验证。
- **Bark SSRF 风险**：现有 URL 校验必须保留，发送前仍要二次校验。
- **产品跑偏**：若 SessionPad 没有感谢/采纳行为，不扩展成社交或协作。

## Further Notes

建议开发顺序：

1. 先提交本计划和当前方向文档。
2. 开小分支做 A1 Bark。
3. 开小分支做 A2 阅读收词来源感。
4. 视闭测硬 bug 情况做 A3。
5. 另开独立分支做 B1-B2 SessionPad 基础。
6. B1-B2 真机可用后，再继续 B3-B4 反馈包和感谢/采纳。

推荐第一轮不要同时开发 A 轨和 B 轨，以免测试面和心智负担叠加。A1/A2 是闭测主线补强；B1-B4 是特色验证，应该单独分支、单独验收。
