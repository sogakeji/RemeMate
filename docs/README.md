# RemeMate 文档地图

本目录同时保留当前参考文档和历史文档。整理时只修剪内容，不移动文件。

## Agent 读取规则

1. 恢复工作先读 [`../.reme/handoff.md`](../.reme/handoff.md)，再读本文件和
   [`HANDOFF.md`](./HANDOFF.md)。`HANDOFF.md` 只提供当前快照，不是过程日志。
2. 带日期的历史过程、旧测试数字和已完成切片默认跳过；只有当前任务明确涉及对应历史时才读取。
3. [`PROGRESS.md`](./PROGRESS.md) 是历史进度日志，仅用于追溯，不用于判断当前状态。
4. [`BACKLOG.md`](./BACKLOG.md) 只记录未完成或延期事项；已完成事项不在 backlog 保留。
5. `arch/`、`design/`、`strategy/`、`wayfinder/` 和 `research/` 是参考资料，不等同于当前实现状态。
6. 当前事实以代码、根目录 [`AGENTS.md`](../AGENTS.md)、`.reme/handoff.md`、
   [`HANDOFF.md`](./HANDOFF.md) 和 [`BACKLOG.md`](./BACKLOG.md) 为准。

## 当前参考

- [`HANDOFF.md`](./HANDOFF.md)：当前状态、验证结果、阻塞和下一步。
- [`BACKLOG.md`](./BACKLOG.md)：未完成工作的简要清单。
- [`deploy-closed-beta.md`](./deploy-closed-beta.md)：闭测部署规则和检查项。
- [`dev-setup.md`](./dev-setup.md)：本地开发与测试环境说明。
- [`THIRD_PARTY.md`](./THIRD_PARTY.md)：第三方依赖和许可记录。
- `arch/`、`design/`、`strategy/`、`wayfinder/`：架构、设计、策略和路径参考。
- `research/`：研究资料；结论是否仍适用需结合当前代码和日期判断。
- [`PROGRESS.md`](./PROGRESS.md)：仅在需要追溯历史时读取。

## 历史或过时内容

以下文件保留原位置，不作为当前状态来源，agent 默认跳过：

- [`bug_audit_2026-07-02.md`](./bug_audit_2026-07-02.md)
- [`plans/2026-07-07-daily-task-card.md`](./plans/2026-07-07-daily-task-card.md)
- [`plans/2026-07-09-closed-beta-dual-track.md`](./plans/2026-07-09-closed-beta-dual-track.md)
- [`superpowers/plans/2026-07-03-lute-reading-mvp.md`](./superpowers/plans/2026-07-03-lute-reading-mvp.md)
- [`superpowers/specs/2026-07-03-lute-reading-mvp-design.md`](./superpowers/specs/2026-07-03-lute-reading-mvp-design.md)
- [`recovery-validation-2026-07-22.md`](./recovery-validation-2026-07-22.md)
- [`rs1-validation-2026-07-23.md`](./rs1-validation-2026-07-23.md)
- [`archive/HANDOFF.full-2026-07-08.md`](./archive/HANDOFF.full-2026-07-08.md)

这些文档只有在任务明确要求复盘对应日期、方案或验证记录时才读取。`PROGRESS.md` 虽然也是历史
内容，但因其承担统一进度日志职责，单独按“历史追溯”规则处理。
