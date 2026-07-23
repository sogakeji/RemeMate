---
status: resolved
type: research
resolved_at: 2026-07-20
implemented_in: e410753
---

# 复习评分幂等边界

## Question

网页双击、请求重试、旧页面重放以及 Web/Bark 交叉评分时，如何保证同一当前到期状态最多推进
一次 SRS，同时保留 lapse 10 分钟后的新合法评分？

## Resolution

卡片渲染时的 `due_date` 是天然的尝试版本，不新增幂等表或随机 token：

- Web 评分请求携带渲染时的 `expected_due_at`。
- 服务端先按 `user_id` 取得词条并锁行，再原子校验当前 `due_date` 仍与版本相同且此刻仍到期。
- 首个合法请求推进 SRS、写 `ReviewLog` 并改变到期时间；后续双击、重试或旧页请求返回无副作用结果。
- lapse 10 分钟后形成新的 `due_date`，因此是新的合法尝试。
- 只有真正应用的评分才更新“上一词”会话指针。
- 事务失败不消耗版本；回滚后相同合法请求可以重试。

Bark 保留现有签名和单次 token 语义，但同样锁定 `words` 行并检查当前仍到期。Web 与 Bark 谁先提交
谁生效，另一方无副作用，避免跨通道重复推进。

## Recovery implementation evidence

原 WSL 提交 `8c1fd62` 在丢盘后按同一契约重放为本地提交 `e410753`：

- Web 使用规范化 naive-UTC `expected_due_at`；
- Web/Bark 共用词条行锁和当前到期状态守卫；
- 过期、重复和跨通道后到请求均无副作用；
- 不新增迁移，不改变 Bark token 格式。

Windows 恢复环境没有 PostgreSQL。实现和测试已恢复，但数据库集成与全量回归仍受
`docs/HANDOFF.md` 的恢复闸门约束，不能把原提交的历史绿线当作当前环境验证结果。

