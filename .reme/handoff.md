# Current handoff

> handoff@bf256d4 · phase: D02 实现与验证完成，待提交决策 · checked: 2026-09-06

- 当前状态：`feature/d02-learning-observation@bf256d4`；D01 已提交 `bf256d4`，D02 改动未提交，不要丢弃。未 merge、push 或部署。
- D02 已按用户确认口径实现：Practice completed + 跨 UTC 日 repeat；独立 `/admin/observation`；两个相邻 UTC 滚动 7×24 小时窗口。
- D02 隐私边界：固定 dispatch 聚合只返回日期、整数和可空比率；页面不返回身份、正文、个人轨迹或钻取；匿名重定向、普通用户 403；dispatch 失败安全降级。
- D02 验证：onlytest 独立 PostgreSQL 16 目标 14 passed；Asia/Shanghai D02 8 passed；迁移 fresh/往返/metadata clean；全量 910 passed / 16 warnings；Chromium/Playwright 1536×900 与 390×844 目检通过；无 migration。
- D01 验证：配置与 CLI 22 passed；原 8 节点 8 passed；Asia/Shanghai 认证 3 passed；全量 902 passed / 16 warnings；临时容器与 volume 清理为零。
- 测试云机：`onlytest`（Tailnet `100.120.97.112`，公网 `118.25.16.25`）；staging 8892 与 PG 55432 active。D01/D02 测试均使用自有随机端口 tmpfs PostgreSQL，不连接共享 staging 数据库。
- 旧机 `159.75.35.39` 的 8892、8894 与 PG 55432 已停止，数据保留；8894 preview 未迁移。
- 已知 staging doctor 差异仍是数据库 `e9f0a1b2c3d4`、staging 代码 head `c1d2e3f4a5b6`，不得宣称 staging strict doctor 全绿。
- 用户最新指令：继续下一步；D02 短计划三项选择均按推荐项确认，随后完成实现与验证。
- 下一动作：检查 D02 最终 diff，由用户决定是否提交/合并。没有部署与真实数据前，不选择 D03/D04。
- 权威规格：[AGENTS.md](../AGENTS.md)
- 当前计划：[D02](../docs/plans/2026-09-06-d02-learning-observation.md)
- 已提交前序：[D01](../docs/plans/2026-09-05-d01-test-release-guards.md)
- 待办：[docs/BACKLOG.md](../docs/BACKLOG.md)
- 详细交接：[docs/HANDOFF.md](../docs/HANDOFF.md)
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
