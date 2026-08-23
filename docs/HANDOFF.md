# RemeMate HANDOFF

> 当前快照：2026-08-23 · `master@ccd4e45` · 生产 `ccd4e45` · migration `e9f0a1b2c3d4`

## 读取规则

- 本文件只保留当前状态、下一阶段和仍会影响工作的踩坑记录。
- 已完成过程与旧验证数字见 [`docs/PROGRESS.md`](./PROGRESS.md)；待办只看
  [`docs/BACKLOG.md`](./BACKLOG.md)。
- 实际 Git、数据库和服务状态优先于文档快照。

## 当前状态

- 法语语境听写 Practice 已合并、推送并部署生产；`PRACTICE_ENABLED=true`，生产迁移为单一 head
  `e9f0a1b2c3d4`。
- 用户已用合成词库和本人词库完成人工验收：5 题选择正确、UI 通过；浏览器
  `speechSynthesis` 音质较差，作为下阶段优化项。
- 发布前备份、migration upgrade、`flask doctor --strict`、服务/HTTPS/日志与数据保留检查均通过；
  生产仍为法语限定，不影响 SRS 或 `review_logs`。

## 下一阶段

1. 先优化 Practice：语音选择与音质、多语言扩展、上线反馈修复；当前仍只支持法语。
2. 同步修复 AI 稳定性与额度语义：造句修改/批改未完成时，不应消耗用户的已完成 AI 用量上限。
3. Review Story 多语言优化后排，待前两项稳定后再启动。

具体范围与强制项见 [`docs/BACKLOG.md`](./BACKLOG.md)。

## 保留的踩坑记录

- `ProductionConfig` 必须从环境显式读取 `PRACTICE_ENABLED`；默认关闭，发布时才设置为 `true`。
- `practice_sessions` 使用 FORCE RLS；含 `blocked` 数据的 downgrade 必须先临时取消 FORCE、转换为
  `abandoned`，随后恢复 FORCE，不能直接添加旧状态约束。
- app 角色未设置 `app.current_user_id` 时查询 RLS 表会得到 0 行；数据保留检查应使用 dispatch 角色，
  不能据此误判生产数据丢失。
- `tests/conftest.py` 会清空 `rememate_test`；导入人工验收数据后不要继续在同一数据库运行 pytest。

部署与安全边界见 [`docs/deploy-closed-beta.md`](./deploy-closed-beta.md) 和根目录
[`AGENTS.md`](../AGENTS.md)。
