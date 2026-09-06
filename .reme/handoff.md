# Current handoff

> handoff@12ad2e5 · phase: D01 实现与验证完成，待提交决策 · checked: 2026-09-06

- 当前状态：`feature/d01-test-release-guards@12ad2e5`；修剪已单独提交，未合并 master（仍为 0fc53f4）、未 push。D01 改动未提交，不要丢弃。
- 已完成：Practice 法/日/中文代码已合入；声音选择、语速记忆与试听在新云机验收通过。AI 失败批改不扣完成额度已由 `2b3d327` 实现。
- D01 验证：onlytest/Python 3.12 上配置与 CLI 单元共 22 passed；原 8 个基线节点 8 passed；Asia/Shanghai 认证 3 passed；迁移 fresh/往返/metadata 通过；全量 902 passed / 16 warnings。临时容器和 volume 清理为零。
- 发布边界：`0fc53f4` 仅本地合并，未 push、未部署生产；远端跟踪引用不是生产运行版本的实时证明。
- 测试云机：活跃测试栈已从 `tencent-new`（159.75.35.39）迁到 `onlytest`（Tailnet 100.120.97.112，公网 118.25.16.25）；8892 与 PG 55432 在新机 active，旧机对应服务已停止但数据保留。8894 临时预览未迁移。
- 已批准顺序：先仓库修剪 → D01 最小收口 → D02 观察面板 → 按实际使用选 D03/D04。推荐修剪边界已获确认。
- 用户最新指令：继续完成 D01；实现和验证已完成，未提交、未合并、未 push。
- 下一动作：检查最终 diff 后由用户决定是否提交/合并；之后按已批准顺序为 D02 短计划，不应直接扩展产品范围。
- D01 实现：双 URL fail-closed/脱敏/禁隐式 `.env`；一次性 PostgreSQL 16 tmpfs 运行器；UTC/Asia-Shanghai 回归；single-head、fresh upgrade、最后一版往返、metadata drift 与 CI 守卫。
- 原 8 失败结论：2 个 Receipt 直接通过；3 个认证为 SQL `now()` 测试夹具时区错误，改绑定 `utc_now()`；3 个 SEO 为正式内容 indexable 后的旧断言，只修测试合同。
- 权威规格：[AGENTS.md](../AGENTS.md)
- 待办：[docs/BACKLOG.md](../docs/BACKLOG.md)
- 已完成待提交：[D01](../docs/plans/2026-09-05-d01-test-release-guards.md)；[修剪记录](../docs/plans/2026-09-05-pre-d01-pruning.md)；[产品决策票](../docs/plans/2026-09-05-product-decision-tickets.md)。
- 已验收计划：[Practice voice controls](../docs/plans/2026-09-05-practice-voice-controls.md)
- 详细交接：[docs/HANDOFF.md](../docs/HANDOFF.md)
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
