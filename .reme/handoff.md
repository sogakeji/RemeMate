# Current handoff

> handoff@e699f88 · phase: 生产已部署 e699f88（/write 目标词轮换修复）并验证 · checked: 2026-08-20

- 当前目标：本地 `master` 与生产 `/srv/rememate` 已对齐 `e699f88`；/write 目标词轮换修复已上线。
- 当前阶段：`/write` 目标词修复（含 grok 审查后的重做：回退策略 + backfill + 索引 + 测试）已部署生产。生产此前在 `4ee4cb6`，本次从 bundle 快进 6 个提交至 `e699f88`（含 `e4901dd` 初版与 `e699f88` 重做版；初版未单独部署过）。
- 生产验证：备份 pg_dump + release.bundle + status.txt 于 `/home/ubuntu/rememate-deploy-backups/20260820-20260820-130421-pre-e699f88/`；`flask db upgrade` 至 `c1d2e3f4a5b6`（新增 `ix_output_entries_writerecent` 索引）；`flask backfill-write-scheduling` dry-run candidates=3 → apply 3 → 幂等 0；`flask doctor --strict` 13 项全 OK；服务重启后 active；内网与公网 HTTPS `/healthz` 200；真实数据模拟：shinypig88 法语目标词首位由 météorologique(24) 变为 repérer(25)→freiner(26)→…；错误日志为空；`.env`、`/srv/rememate-data` 未触碰，业务表行数不变（users 8 / words 213 / output_entries 3 / push_log 0）。
- 测试环境：以后测试一律在 tencent-new（159.75.35.39）跑，其 `/home/ubuntu/rememate-test` 为 repo 副本 + venv，PostgreSQL 16 集群 `rememate_test`（端口 55432，dev 密码 dev_app_pw/dev_dispatch_pw），已从空库迁移到 head `c1d2e3f4a5b6`。生产机不再用于跑测试。
- 已知既有失败（与本次无关）：unit `test_public_content.py` 2 条（fixture 缺 zh/qa.yaml）、`test_review_story_handoff.py::test_story_handoff_rejects_expired_ready_run`、`test_review_stories.py::test_orchestrate_failed_attempt_requires_explicit_single_retry`。
- 下一动作：按 [docs/BACKLOG.md](../docs/BACKLOG.md) 的"Review Story 多语言稳定性二次优化"建立独立修复切片（细分错误码、单 provider 重试、脱敏观测、fake-provider 回归），再重跑六语种 staging smoke；或先清理上述既有失败测试。
- 阻塞项：无。本地与生产已对齐。
- 权威规格：[AGENTS.md](../AGENTS.md)
- 当前计划：[docs/plans/2026-08-14-public-seo-content.md](../docs/plans/2026-08-14-public-seo-content.md)
- 详细进度：[docs/PROGRESS.md](../docs/PROGRESS.md) · 部署状态：[docs/HANDOFF.md](../docs/HANDOFF.md)
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
