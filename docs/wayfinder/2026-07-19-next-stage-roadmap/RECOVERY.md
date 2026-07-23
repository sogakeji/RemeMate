# Wayfinder recovery provenance

该目录于 2026-07-22 在 WSL2 虚拟磁盘丢失后恢复。恢复只涉及文档和历史原型资产，不代表功能已经
实现或部署。

## Evidence

- `01`–`04` 与初始 `MAP.md`：来自仍存在的 `outputs/wayfinder-staging` 原文件。
- `05`–`11`：依据同一 Codex 任务的完整 turn/file-change 记录恢复；其中 `08`、`10`、`11` 的原始
  新文件 diff 仍可读取，其他决议由已确认问答、提交摘要和现存补丁交叉重建。
- `artifacts/review-story-experience.html`：原短故事 A/B/C 静态原型的字节副本。
- `artifacts/verify-review-story-prototype.js`：原 Chrome 自动检查脚本。
- SessionPad 候选审核一次性 HTML 在方案确认后按原计划删除，未进入 Git，无法逐字恢复；
  `resolved/10-sessionpad-candidate-review-prototype.md` 保留完整状态与布局契约。

## Authority

- 产品与实施决策以 `MAP.md` 和 `resolved/` 为权威。
- `artifacts/` 仅供历史审计，不是生产模板，也不应直接移植。
- 当前代码/部署状态仍以 `docs/HANDOFF.md` 为权威；尤其要遵守 2026-07-22 丢盘恢复测试闸门。

