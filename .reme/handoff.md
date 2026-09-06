# Current handoff

> handoff@ce81a2a · phase: D02 已部署，等待真实观察数据 · checked: 2026-09-07

- 当前状态：本地 `master@ce81a2a`、`origin/master@ce81a2a`、生产 `/srv/rememate@ce81a2a`；工作树仅有本次部署记录文档待提交。
- 用户明确批准并已完成：提交 D02、fast-forward 合并 master、push origin、部署生产。
- 已部署链：Practice 语音控制 `0fc53f4` → 修剪 `12ad2e5` → D01 `bf256d4` → D02 `ce81a2a`。
- D02：固定 dispatch 聚合、独立 `/admin/observation`、相邻 UTC 滚动 7 日窗口、Practice completed/跨日 repeat；不返回身份、正文、个人轨迹或钻取。
- 验证：onlytest 全量 910 passed / 16 warnings；迁移检查 clean；Chromium/Playwright 1536×900 与 390×844 目检通过；GitHub Actions `34065885381` 全部通过。
- 生产备份：`/home/ubuntu/rememate-backups/deploy-20260906T230334Z-83fc2b5-to-ce81a2a`，含数据库 dump、部署前 Git bundle 与状态。
- 生产验证：migration `e9f0a1b2c3d4` single head；strict doctor 全 OK；服务 active/enabled；内外 healthz 200；匿名 observation 302；聚合服务结构检查和部署后日志检查通过。
- `.env`、`.venv`、用户数据与 `/srv/rememate-data` 未修改；部署 bundle 临时文件已删除。
- 测试云机仍为 `onlytest`（Tailnet `100.120.97.112`）；staging 8892/PG 55432 active，旧测试机服务停止且数据保留。
- 下一动作：提交并 push 本次部署记录文档；之后等待 D02 真实聚合数据，不提前选择 D03/D04。
- 权威规格：[AGENTS.md](../AGENTS.md)
- 当前计划：[D02](../docs/plans/2026-09-06-d02-learning-observation.md)
- 待办：[docs/BACKLOG.md](../docs/BACKLOG.md)
- 详细交接：[docs/HANDOFF.md](../docs/HANDOFF.md)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
