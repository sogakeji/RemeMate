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
- 当前工作分支 `chore/pre-d01-repo-pruning@0fc53f4`；此前交接文档与本轮修剪均未提交。已删 55 张重复图片和 13 个历史脚本及配套 PDF；运行时 app/content、tests、migrations 未改。详情见 [修剪计划](./plans/2026-09-05-pre-d01-pruning.md)。

## 新云机测试与预览

- 主机：`tencent-new`；功能目录：`/home/ubuntu/rememate-practice-voice-controls`。
- 干净基线目录：`/home/ubuntu/rememate-83fc2b5-baseline`（Git archive `83fc2b5`）。
- 自动化测试只使用 `127.0.0.1:55432/rememate_test`，夹具会清库。
- Practice 集成：49 passed；相关单元：24 passed；Node voice 测试及 JS 语法检查通过。
- 全量：功能版本 871 passed / 8 failed；基线 870 passed / 相同 8 failed。未新增失败，但不得宣称全量全绿。
- 8894 预览：`rememate-practice-voice-preview.service`，临时 systemd unit，仅监听回环；最后检查 active，登录页 HTTP 200。
- 8894 使用现有 staging 环境配置和 **共享 `rememate_staging` 数据库**，与 8892 只隔离代码/进程，不隔离数据。原 `rememate-staging.service` / 8892 保持运行。
- Python 环境复用 `/home/ubuntu/rememate-test/.venv`，未安装或升级依赖；后续不要修改共享环境。
- 验收账号：`voice-preview@rememate.test`，普通用户，法/日/中文各 5 个例句，默认法语；密码已在会话交付，不记录到仓库。已验证登录 302、Practice 200、语音控件存在，用户反馈“没问题”。
- 隧道：`ssh -N -L 8894:127.0.0.1:8894 tencent-new`，访问 `http://127.0.0.1:8894`。临时服务存活状态须使用前重查。

## 尚未解决的基线失败

- 3 个认证 challenge 过期相关：account_access、password_reset_routes、registration_activation_routes。
- 2 个 Review Story receipt 相关。
- 3 个公开内容 SEO 旧 noindex 断言相关。
- 已观察测试库时区为 Asia/Shanghai，应用使用 naive UTC，部分测试用 `now()` 写入 naive 列；这是时间失败的候选解释，尚未完成对照复现，不能认定认证逻辑有漏洞或根因已确认。

## 下一阶段

- 用户已批准推荐顺序：仓库修剪 → D01 最小测试/发布收口 → D02 私有学习观察 → 再按使用情况选 D03/D04。
- D01 包含测试隔离、基线失败分类与迁移守卫；尚未编码。修剪结束后细化实施计划与测试 seam，不在本轮清理中修改测试断言。
- 本地内容单测 10 passed / 2 failed，失败仍为既有 indexable/noindex 旧断言；71 处修改文档图片引用有效。完整运行记录见修剪计划。
- Review Story 多语言、云端 TTS、新语言扩展仍不在当前实施范围。
- 合并批准不包含 push 或生产部署批准。

## 安全与操作遗留

- 云机测试过程中曾重设测试集群的 `rememate` / `rememate_dispatch` 密码；这不是纯只读操作。后续需确认共享测试连接如何恢复，不再自行重设角色密码。
- 曾误将 staging URL 传入 pytest，conftest 在导入时拒绝执行，未进入清库夹具；该错误输出含 staging 连接凭据。不要保存或转发原始日志，凭据轮换需另获批准。后续必须在调用 pytest 前验证两个 URL 的 host/port/database，且不输出密码。
- app 角色访问 RLS 表需要 `app.current_user_id`；不能把无上下文查询的 0 行当成数据丢失。
- `practice_sessions` 含 blocked 数据时，downgrade 须先临时取消 FORCE RLS、转换状态，再恢复 FORCE。
- `ProductionConfig` 显式读取 `PRACTICE_ENABLED`，默认关闭。
- 已删除的旧 FAQ 截图/探测脚本含硬编码测试凭据；删除当前文件不清除 Git 历史，是否轮换需另获批准。禁止恢复旧脚本后直接运行。`.pi/quiet-tools/` 已忽略，防止工具输出误入提交。
- 本轮修剪未连接云机或数据库，未改生产；保留用户“先不动生产”的边界。
