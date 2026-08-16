# RemeMate HANDOFF

> 当前快照：2026-08-16 · `master` · HEAD `e837205`

## 读取规则

- 本文件只记录当前状态、当前阻塞和下一步，不作为过程日志。
- 带日期的历史过程、旧测试数字和已完成切片不作为当前事实；需要追溯时读取
  [`docs/PROGRESS.md`](./PROGRESS.md) 或任务专属文档。
- 已标记为历史/过时的文档默认跳过，只有当前任务明确涉及时才读取；权威路线以当前代码、
  `AGENTS.md`、本文件和 [`docs/BACKLOG.md`](./BACKLOG.md) 为准。

## 当前状态

- 工作树有本轮语言收敛、AI 短故事修复、测试和文档的未提交改动。保留用户改动，不执行
  reset、stash、覆盖、merge、push 或生产部署。
- 产品界面只支持简体中文、英语；AI 支持中文、英文、法语、日语、韩语、西班牙语；德语、
  俄语仅保留历史兼容并从新入口隐藏；阅读器只支持中文、英语、法语、日语。
- 新云机 staging 已应用迁移至 `e8f9a0b1c2d3`。`flask doctor --strict`、服务 active、内网
  `/healthz` 200 和错误日志检查通过；未触碰生产环境、生产数据、环境文件或词典目录。
- 公网 `staging.rememate.com` 尚未在该云机配置 DNS/vhost，内网 staging 结果不能表述为公网验证。

## 最近验证

- 六种 AI 语言的一键填充、例句、学习笔记均真实调用 provider 并通过。
- 六种 AI 语言的造句批改均通过；临时测试词条已清理。
- 复习小故事的真实 provider 复测中，英文、日文、韩文、西班牙文通过；中文、法文在有界
  重试后仍出现 `invalid_schema`，韩文观察到首次失败后重试成功的波动。短故事暂不能宣称
  六语种稳定可用。
- 新云机相关定向测试：**101 passed, 2 deselected**。

## 下一步与边界

- 下一项是 [`docs/BACKLOG.md`](./BACKLOG.md) 中的“Review Story 多语言稳定性二次优化”；
  先补失败回归和脱敏观测，再重跑六语种 staging smoke。
- 修复验收前不部署生产。生产部署必须另行获得明确批准，并执行目标环境迁移、全量测试、
  `flask doctor --strict`、服务/HTTPS/日志和数据保留检查。
- 架构与部署规则分别见 [`docs/arch/`](./arch/)、[`docs/deploy-closed-beta.md`](./deploy-closed-beta.md)
  和根目录 [`AGENTS.md`](../AGENTS.md)；不要把这些参考文档中的旧状态当作当前状态。
