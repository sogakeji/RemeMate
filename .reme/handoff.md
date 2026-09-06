# Current handoff

> handoff@0fc53f4 · phase: D01 前仓库修剪进行中，尚未提交 · checked: 2026-09-05

- 当前状态：`chore/pre-d01-repo-pruning@0fc53f4`；master 也在该代码锚点，未 push。工作区包含此前 handoff 对齐与本轮修剪，均未提交，不要丢弃。
- 已完成：Practice 法/日/中文代码已合入；声音选择、语速记忆与试听在新云机验收通过。AI 失败批改不扣完成额度已由 `2b3d327` 实现。
- 验证：Practice 集成 49 passed；相关单元 24 passed；全量 871 passed / 8 failed，基线 `83fc2b5` 为 870 passed / 相同 8 failed。全量并非全绿。
- 发布边界：`0fc53f4` 仅本地合并，未 push、未部署生产；远端跟踪引用不是生产运行版本的实时证明。
- 预览：新云机 `tencent-new` 的 8894 服务使用共享 staging 数据库；不是独立数据库。账号及隧道见 [docs/HANDOFF.md](../docs/HANDOFF.md)，密码不入库。
- 已批准顺序：先仓库修剪 → D01 最小收口 → D02 观察面板 → 按实际使用选 D03/D04。推荐修剪边界已获确认。
- 下一动作：收口 [修剪计划](../docs/plans/2026-09-05-pre-d01-pruning.md)，然后细化 D01 测试隔离与公开 seam；D01 尚未编码。
- 待排查：8 个基线失败；时间相关失败的时区根因尚未通过对照实验确认。
- 权威规格：[AGENTS.md](../AGENTS.md)
- 待办：[docs/BACKLOG.md](../docs/BACKLOG.md)
- 当前任务：[D01 前修剪](../docs/plans/2026-09-05-pre-d01-pruning.md)；[产品决策票](../docs/plans/2026-09-05-product-decision-tickets.md)。
- 已验收计划：[Practice voice controls](../docs/plans/2026-09-05-practice-voice-controls.md)
- 详细交接：[docs/HANDOFF.md](../docs/HANDOFF.md)
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
