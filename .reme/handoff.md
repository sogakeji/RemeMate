# Current handoff

> handoff@6281293 · phase: sentence scheduling fix deployed and production verified · checked: 2026-08-17

- 当前状态：修复分支 `fix/sentence-writing-schedule-refresh` 已推送，发布锚点为 `6281293`；生产 `/srv/rememate` 的 `master` 已部署同一提交。本地 `master` 与 `origin/master` 仍为 `7479d44`，本轮未 merge。
- 产品界面仅支持简体中文/英语，AI 支持中文/英文/法语/日语/韩语/西班牙语，阅读器仅支持中文/英语/法语/日语，德语/俄语仅保留历史兼容并从新入口隐藏。
- 生产迁移：已升级至 `e8f9a0b1c2d3`；`flask doctor --strict`、服务 active、内网 `/healthz` 200、公网 HTTPS `/healthz` 200，部署后的错误日志为空。
- 数据保全：本次发布前 PostgreSQL dump 与 Git bundle 已生成并验证，备份目录为 `/home/ubuntu/rememate-deploy-backups/20260817-081832-pre-6281293`；发布前后业务表行数记录一致，未触碰 `.env`、`.venv`、数据库内容或 `/srv/rememate-data`。
- 生产 `.env` 的 `OPEN_REGISTRATION_ENABLED="true"` 已获得对外公测批准，本次未修改；注册邮件配置已通过 `flask doctor --strict`，公开注册入口 HTTPS 冒烟返回 200。
- 造句保存后单词调度问题已修复：保存成功调用现有 SRS `q=5` 并写入 `write` 来源 `review_logs`，下一次 `/write` 推荐切换。新云机造句集成 30 passed，与相邻回归合计 44 passed、1 warning；真实 HTTP provider 流程通过，临时账号已清理。
- AI 真实复测：一键填充/例句/笔记六语种全通过；造句批改六语种全通过；复习小故事英文、日文、韩文、西班牙文通过，中文/法文在有界重试后仍有 `invalid_schema`，韩文存在首次失败后重试成功的波动。生产已按明确批准发布，但暂不能宣称短故事六语种稳定可用。
- 下一动作：按 [docs/BACKLOG.md](../docs/BACKLOG.md) 的“Review Story 多语言稳定性二次优化”建立独立修复切片；先补细分错误码、单 provider 重试、脱敏观测和 fake-provider 回归，再重跑六语种 staging smoke。造句修复尚未合并到 `master`。
- 工作树纪律：保留现有用户改动，不 reset、stash、覆盖或合并；修改项目文件前先运行 `git status --short --branch`，并将当前 HEAD 与本 handoff 锚点比较。推送、部署和生产操作必须有明确授权。
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
