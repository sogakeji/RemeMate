# RemeMate HANDOFF

> 当前代码锚点：2026-09-05 · 本地 `master@0fc53f4` · 未 push / 未部署本次语音控制

## 读取规则

- 恢复从 `.reme/handoff.md` 开始；实际 Git、数据库和服务状态优先于快照。
- 本文记录当前状态和仍影响工作的注意事项；未完成工作见 [BACKLOG.md](./BACKLOG.md)。
- 本次对齐仅依据 Git 与本会话验证记录，不重新连接生产，也不把远端跟踪引用当作线上运行版本证明。

## 当前状态

- 用户已验收 Practice 语音控制，并批准合并；`0fc53f4 feat: add practice voice controls` 已 fast-forward 到本地 master。
- 本地 `origin/master` 及 `production/master` 跟踪引用停在 `83fc2b5`；本地 master ahead 1。未 push，未部署生产。
- 当前代码支持法语、日语、中文 Practice；开始页可选择声音、0.7–1.2× 语速并试听；按语言本地记忆，答题/反馈播放复用，不自动播放。
- AI 未完成批改不扣完成额度已在 `2b3d327` 合入；包含 provider 成本分离、内部重试、并发额度与脱敏测试。重复用户提交仍被视作新完成，不代表 HTTP 请求级幂等已实现。
- 已验收契约：[语音控制短计划](./plans/2026-09-05-practice-voice-controls.md)。
- 修剪及交接已按用户批准独立提交 `12ad2e5`，未合并 master；删除 55 张重复图片和 13 个历史脚本及配套 PDF，修剪提交不改 app/content/tests/migrations。
- 当前分支 `feature/d01-test-release-guards@12ad2e5`，D01 实现与验证完成但尚未提交：隔离容器运行器、配置/凭据护栏、基线失败分类、迁移/metadata 守卫和最小权限 CI 均在工作区。

## 测试云机

- 当前主机：`onlytest`；公网 `118.25.16.25`，Tailnet `100.120.97.112`；本机 SSH 别名走 Tailnet。
- 活跃测试栈已从 `tencent-new`（159.75.35.39）迁移：`/home/ubuntu/rememate-test`、独立 Python 3.12 venv、PostgreSQL 16 的 `rememate_staging` / `rememate_test` 与角色、`rememate-staging.service` / 8892。
- 新机 8892、PG 55432、tailscaled 均 active 且开机启动；服务仅监听回环。隧道：`ssh -N -L 8892:127.0.0.1:8892 onlytest`。
- 迁移后两库各 34 张 public 表的逐表行数与旧机一致；登录页和首页 HTTP 200，app/dispatch/migrate 三连接及密钥、管理员、字典检查通过。
- `flask doctor --strict` 在新旧机均只报同一迁移基线差异：数据库 `e9f0a1b2c3d4`，代码 head `c1d2e3f4a5b6`；因此不得宣称 strict doctor 全绿。
- 旧机 8892、临时 8894 和 PG 55432 已停止，数据未删除；8894 临时预览和历史测试目录未迁移。
- 用户要求继续 D01 后，`onlytest` 已安装 Docker 29.1.3、腾讯云 registry mirror 和 Node 12；D01 使用独立目录 `/home/ubuntu/rememate-d01` 与独立 venv，不修改迁入的 staging venv。
- D01 最终验证：配置/CLI 单元 22 passed；原 8 个失败节点 8 passed；Asia/Shanghai 认证过期 3 passed；迁移检查通过；全量 `902 passed, 16 warnings`。容器和 volume 均清理为零。

## D01 基线失败结论

- 3 个认证 challenge 失败是测试夹具时区错误：SQL `now()` 把 session 本地时间写入 naive UTC 列；改为绑定 `utc_now()` 后 UTC 与 Asia/Shanghai 均通过，未发现认证逻辑漏洞。
- 2 个 Review Story receipt 在新隔离环境直接通过，无产品改动。
- 3 个 SEO 失败是正式内容已从 placeholder 改为 `indexable: true` 后遗留的旧断言；只更新正式内容和 sitemap 预期，临时 catalog noindex、草稿隐藏和私有产品页 noindex 合同仍有测试。

## 下一阶段

- 用户已批准推荐顺序：仓库修剪 → D01 最小测试/发布收口 → D02 私有学习观察 → 再按使用情况选 D03/D04。
- [D01 计划](./plans/2026-09-05-d01-test-release-guards.md) 的三条 seam 已完成；工作区未提交，等待用户决定提交/合并。
- 下一产品阶段按已批准顺序为 D02 私有学习观察；开始前仍应确认短计划与范围。
- 迁入的共享 PG 55432 只承载 staging/test 历史栈；D01 pytest 一律使用运行器拥有的随机回环端口和 tmpfs，不连接共享数据库。
- 修剪相关本地内容单测的旧 SEO 失败已在 D01 按正式内容合同修正；71 处修改文档图片引用仍有效。完整运行记录见修剪与 D01 计划。
- Review Story 多语言、云端 TTS、新语言扩展仍不在当前实施范围。
- 合并批准不包含 push 或生产部署批准。

## 安全与操作遗留

- 云机测试过程中曾重设测试集群的 `rememate` / `rememate_dispatch` 密码；这不是纯只读操作。后续需确认共享测试连接如何恢复，不再自行重设角色密码。
- 曾误将 staging URL 传入 pytest，conftest 在导入时拒绝执行，未进入清库夹具；该错误输出含 staging 连接凭据。不要保存或转发原始日志，凭据轮换需另获批准。后续必须在调用 pytest 前验证两个 URL 的 host/port/database，且不输出密码。
- app 角色访问 RLS 表需要 `app.current_user_id`；不能把无上下文查询的 0 行当成数据丢失。
- `practice_sessions` 含 blocked 数据时，downgrade 须先临时取消 FORCE RLS、转换状态，再恢复 FORCE。
- `ProductionConfig` 显式读取 `PRACTICE_ENABLED`，默认关闭。
- 已删除的旧 FAQ 截图/探测脚本含硬编码测试凭据；删除当前文件不清除 Git 历史，是否轮换需另获批准。禁止恢复旧脚本后直接运行。`.pi/quiet-tools/` 已忽略，防止工具输出误入提交。
- D01 在 `onlytest` 安装了 Docker/Node，并只操作自身临时容器；未对共享 55432 执行 pytest、改角色或改数据，未连接或改动生产。保留用户“先不动生产”的边界。
