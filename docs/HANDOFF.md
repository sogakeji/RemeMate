# RemeMate HANDOFF

> 当前快照：2026-08-16 · `master` · HEAD `4a579315`

## 读取规则

- 本文件只记录当前状态、当前阻塞和下一步，不作为过程日志。
- 带日期的历史过程、旧测试数字和已完成切片不作为当前事实；需要追溯时读取
  [`docs/PROGRESS.md`](./PROGRESS.md) 或任务专属文档。
- 已标记为历史/过时的文档默认跳过，只有当前任务明确涉及时才读取；权威路线以当前代码、
  `AGENTS.md`、本文件和 [`docs/BACKLOG.md`](./BACKLOG.md) 为准。

## 当前状态

- 本地 `master` 与生产 `/srv/rememate` 已对齐 `4a579315`；生产原有代码工作树改动已先备份，
  再按本地版本更新。未触碰 `.env`、`.venv`、数据库或 `/srv/rememate-data`。
- 生产对外公测已获得批准；现有 `OPEN_REGISTRATION_ENABLED="true"` 为已授权状态，公开注册入口
  HTTPS 冒烟返回 200。
- 产品界面只支持简体中文、英语；AI 支持中文、英文、法语、日语、韩语、西班牙语；德语、
  俄语仅保留历史兼容并从新入口隐藏；阅读器只支持中文、英语、法语、日语。
- 生产数据库已应用迁移至 `e8f9a0b1c2d3`。`flask doctor --strict`、服务 active、内网
  `/healthz` 200、公网 HTTPS `/healthz` 200 和部署后错误日志检查通过。
- 迁移前 PostgreSQL 备份及生产工作树备份位于生产机
  `/home/ubuntu/rememate-deploy-backups/20260816-225055-pre-4a57931`；迁移前后业务表行数记录一致。
- 生产现有 `.env` 中 `OPEN_REGISTRATION_ENABLED="true"`，本次未修改；该配置已获对外公测批准。

## 最近验证

- 六种 AI 语言的一键填充、例句、学习笔记均真实调用 provider 并通过。
- 六种 AI 语言的造句批改均通过；临时测试词条已清理。
- 复习小故事的真实 provider 复测中，英文、日文、韩文、西班牙文通过；中文、法文在有界
  重试后仍出现 `invalid_schema`，韩文观察到首次失败后重试成功的波动。生产已按明确批准部署，
  但短故事暂不能宣称六语种稳定可用。
- 新云机相关定向测试：**101 passed, 2 deselected**。

## 下一步与边界

- 下一项是 [`docs/BACKLOG.md`](./BACKLOG.md) 中的“Review Story 多语言稳定性二次优化”；
  先补失败回归和脱敏观测，再重跑六语种 staging smoke。
- 生产部署必须保留数据库备份、迁移检查、`flask doctor --strict`、服务/HTTPS/日志和数据保留检查；
  对外公测期间继续关注注册邮件投递和异常流量。
- 架构与部署规则分别见 [`docs/arch/`](./arch/)、[`docs/deploy-closed-beta.md`](./deploy-closed-beta.md)
  和根目录 [`AGENTS.md`](../AGENTS.md)；不要把这些参考文档中的旧状态当作当前状态。
