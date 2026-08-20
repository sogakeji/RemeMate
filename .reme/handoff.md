# Current handoff

> handoff@d583df7 · phase: Bark 推送节奏与正文修复已部署 · checked: 2026-08-20

- 当前目标：本地 `master` 与生产 `/srv/rememate` 已对齐 `7daee60`；Bark 复习提醒定时推送已上线并真实推送验证。
- 当前阶段：Bark 定时推送功能（TDD，codex 实现 / grok 审查与测试 / 负责人统筹）已合并到 master 并部署生产。生产此前在 `e699f88`，本次快进 17 个提交至 `7daee60`（dispatch/runner.py + systemd 单元 + 部署文档 + notifications.py 可选 user_id 参数 + 测试）。
- 生产验证：备份 pg_dump + bundle 于 `/home/ubuntu/rememate-deploy-backups/20260820-20260820-165647-pre-bark/`；无新迁移（head `c1d2e3f4a5b6`）；`flask doctor --strict` 全 OK；服务重启 active；`rememate-bark.timer` 已安装并 enable，每 15 分钟触发；真实生产密钥（.env 的 SECRET_KEY/PUBLIC_BASE_URL/DISPATCH_DATABASE_URL）下 systemd 服务手动跑：`users=1 sent=1`，push_log 写入 `4:review:159:2026-08-20`（shinypig88 / biographie，含复习链接）；重跑 `sent=0 duplicates=1` 幂等；公网 `/healthz` 200；错误日志为空。
- 审查与测试记录：grok 初审 1 BLOCKER + 4 MAJOR（单事务回滚、temp-view 隔离、幂等提交、测试缺口、systemd）→ codex 返工（显式 user_id 参数 + 每用户独立事务 + 去掉 temp-view + systemd flock/RuntimeDirectory/After postgresql + 补跨用户/回滚/日界/payload/systemd 契约测试）→ tencent-new 重测 7/7 passed、全量回归无新增失败 → 真实推送验证（bark-real 测试用户收到 bonjour 通知）。
- 测试环境：tencent-new `/home/ubuntu/rememate-test` + PostgreSQL 55432 `rememate_test`（dev 密码），测试由 grok 执行。
- Bark 推送两个修复已上线：①timer 节奏从每 15 分钟改为每 2 小时整点（OnCalendar 00,02,...,22:00）；②推送正文移除释义/例句防剧透（build_review_reminder_payload 只留通用提醒+待复习数）。真实频率根因：用户每点一次链接评分，下一个到期词在下一个心跳即被推（16:57/17:00/17:15 连续 3 条）。已部署生产并验证（timer 下次触发 18:00；payload 测试断言无"房子"；幂等重跑 duplicates=1 无重复推）。
- 下一动作：观察 Bark 新节奏（每 2 小时整点）与新正文（无翻译）表现；或按 BACKLOG 处理 Review Story 多语言稳定性切片。
- 阻塞项：无。
- 权威规格：[AGENTS.md](../AGENTS.md)
- 当前计划：[docs/plans/2026-08-14-public-seo-content.md](../docs/plans/2026-08-14-public-seo-content.md)
- 详细进度：[docs/PROGRESS.md](../docs/PROGRESS.md) · 部署状态：[docs/HANDOFF.md](../docs/HANDOFF.md)
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
