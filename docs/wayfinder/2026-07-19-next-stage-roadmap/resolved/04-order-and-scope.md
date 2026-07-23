---
status: resolved
type: grilling
resolved_at: 2026-07-19
---

# 路线顺序与范围边界

## Question

现有 BACKLOG、短故事和语言交换收词增强应按什么顺序进入下一阶段？

## Resolution

主干顺序为：

1. 安全与数据可信度：`output_entries.word_id` 所有权约束、广场 NSFW failover、同语言生词去重。
2. 到期词短故事与复习后输出闭环。
3. SessionPad 带语境候选。
4. 闭测观察面板 v1。
5. 后续体验批次：全局不再建议、移动端阅读工具栏、CSV 星标、SSE 超时和 Landing 小修。

单词生图不做。未来若重新评估视觉记忆，只考虑由已经验证的短故事派生四格或多格漫画，
不做孤立的单词图片。

