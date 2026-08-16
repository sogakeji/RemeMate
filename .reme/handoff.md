# Current handoff

> handoff@4a579315 · phase: production deployment verified · checked: 2026-08-16

- 当前目标：完成语言支持收敛；保留已完成的 AI 语言功能修复；下一阶段处理 Review Story 多语言稳定性二次优化。
- 当前状态：本地 `master` 与生产 `/srv/rememate` 均已对齐 `4a579315`；产品界面仅支持简体中文/英语，AI 支持中文/英文/法语/日语/韩语/西班牙语，阅读器仅支持中文/英语/法语/日语，德语/俄语仅保留历史兼容并从新入口隐藏。
- 生产迁移：已升级至 `e8f9a0b1c2d3`；`flask doctor --strict`、服务 active、内网 `/healthz` 200、公网 HTTPS `/healthz` 200，部署后的错误日志为空。
- 数据保全：迁移前 PostgreSQL `rememate` 已生成并验证备份，备份目录为 `/home/ubuntu/rememate-deploy-backups/20260816-225055-pre-4a57931`；迁移前后业务表行数记录一致，未触碰 `.env`、`.venv`、数据库或 `/srv/rememate-data`。
- 生产原有代码工作树已按本地权威版本更新；更新前的 tracked/untracked 改动已保存在上述备份目录，未纳入当前版本的登录初始化文件也未写入仓库。
- 生产 `.env` 原有 `OPEN_REGISTRATION_ENABLED="true"`，本次未修改；闭测默认应为关闭，是否调整需单独确认，不能将其视为本次部署变更。
- AI 真实复测：一键填充/例句/笔记六语种全通过；造句批改六语种全通过；复习小故事英文、日文、韩文、西班牙文通过，中文/法文在有界重试后仍有 `invalid_schema`，韩文存在首次失败后重试成功的波动。生产已按明确批准发布，但暂不能宣称短故事六语种稳定可用。
- 下一动作：按 [docs/BACKLOG.md](../docs/BACKLOG.md) 的“Review Story 多语言稳定性二次优化”建立独立修复切片；先补细分错误码、单 provider 重试、脱敏观测和 fake-provider 回归，再重跑六语种 staging smoke。
- 工作树纪律：保留现有用户改动，不 reset、stash、覆盖、merge、push 或部署；修改项目文件前先运行 `git status --short --branch`，并将当前 HEAD 与本 handoff 锚点比较。
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
