# RemeMate HANDOFF

> 当前快照：2026-08-20 · `master` · 以实际 Git HEAD 为准 · 生产 `e006076`

## 读取规则

- 本文件只记录当前状态、当前阻塞和下一步，不作为过程日志。
- 带日期的历史过程、旧测试数字和已完成切片不作为当前事实；需要追溯时读取
  [`docs/PROGRESS.md`](./PROGRESS.md) 或任务专属文档。
- 已标记为历史/过时的文档默认跳过，只有当前任务明确涉及时才读取；权威路线以当前代码、
  `AGENTS.md`、本文件和 [`docs/BACKLOG.md`](./BACKLOG.md) 为准。

## 当前状态

- 实际生产工作树 `/srv/rememate` 为干净的 `master@e006076`；本地 `master` 是其快进后代，无分叉。
- `e006076` 已包含 Bark 每两小时提醒、正文防剧透及每日到期词轮换；对应部署与验证证据见
  [`.reme/evidence.yaml`](../.reme/evidence.yaml)。
- 本地在生产基线上新增的提交仅涉及 REME checkpoint、handoff 与 `.pi` 验证工具；尚未部署这些提交，
  也未改动生产 `.env`、`.venv`、数据库或 `/srv/rememate-data`。
- 生产数据库迁移 head 为 `c1d2e3f4a5b6`；Bark timer 已安装并启用。运行状态的历史验证以证据账本为准，
  需要发布时必须重新执行部署检查，不能把旧快照当作当前实时健康检查。

## 最近验证

- Bark 每日轮换在 tencent-new 定向测试 17 passed，unit + write 284 passed；生产手动运行确认会跳过当天已推词。
- Bark 定时推送首次生产实跑 `sent=1`，重复运行 `duplicates=1`，验证幂等。
- Review Story 中文、法文仍存在 `invalid_schema` 波动，尚不能宣称六语种稳定可用。

## 下一步与边界

- 先将本地 `master` 安全推送至 `origin/master`；生产保持 `e006076`，除非另行明确批准部署。
- 后续按 [`docs/BACKLOG.md`](./BACKLOG.md) 处理“Review Story 多语言稳定性二次优化”：先补失败回归和
  脱敏观测，再重跑六语种 staging smoke。
- 生产部署必须保留数据库备份、迁移检查、`flask doctor --strict`、服务/HTTPS/日志和数据保留检查。
- 架构与部署规则分别见 [`docs/arch/`](./arch/)、[`docs/deploy-closed-beta.md`](./deploy-closed-beta.md)
  和根目录 [`AGENTS.md`](../AGENTS.md)；不要把这些参考文档中的旧状态当作当前状态。
