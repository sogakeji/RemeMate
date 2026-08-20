# Current handoff

> handoff@4ee4cb6 · phase: 生产已部署并验证 · checked: 2026-08-20

- 当前目标：本地 `master` 与生产 `/srv/rememate` 已对齐 `4ee4cb6`；内容去 AI 味工作完成并上线。
- 当前阶段：两轮 humanization（`03a2851` + `7d61aa9`）已部署生产并验证。生产机 tencent-old（43.156.210.229）在本次部署前实际位于 `da2a41f`（8-17 已部分部署 FAQ/SEO），本次从 bundle 快进 4 个提交至 `4ee4cb6`，纯内容 + `.reme` 变更，无代码、无迁移。
- 生产验证：部署前备份 pg_dump + release.bundle + status.txt 于 `/home/ubuntu/rememate-deploy-backups/20260820-20260820-093111-pre-4ee4cb6/`；`flask db upgrade` 无操作（head `e8f9a0b1c2d3`）；`flask doctor --strict` 12 项全 OK；服务重启后 active；内网与公网 HTTPS `/healthz` 200；`/qa`、`/blog`、4 篇中英文章冒烟 200 且已返回 humanized 正文；错误日志为空；`.env`、`.venv`、`/srv/rememate-data` 未触碰，业务表可读。
- 下一动作：按 [docs/BACKLOG.md](../docs/BACKLOG.md) 的"Review Story 多语言稳定性二次优化"建立独立修复切片（细分错误码、单 provider 重试、脱敏观测、fake-provider 回归），再重跑六语种 staging smoke。
- 阻塞项：无。本地与生产已对齐；剩余未上线内容仅为未来新提交。
- 权威规格：[AGENTS.md](../AGENTS.md)
- 当前计划：[docs/plans/2026-08-14-public-seo-content.md](../docs/plans/2026-08-14-public-seo-content.md)
- 详细进度：[docs/PROGRESS.md](../docs/PROGRESS.md) · 部署状态：[docs/HANDOFF.md](../docs/HANDOFF.md)
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
