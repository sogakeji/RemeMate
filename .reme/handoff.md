# Current handoff

> handoff@c0499db · phase: production registration active, landing refresh queued · checked: 2026-08-10

- 当前目标：刷新生产 Landing 的过时闭测与邀请制表述，使其匹配已开放的自助注册。
- 当前阶段：生产真实邮箱注册、验证、自动登录和设密人测成功；聚合检查为 7 个完整账号、1 个已消费 registration challenge、1 封 registration sent、0 个待设密账号。
- 下一动作：按 [Backlog](../docs/BACKLOG.md) 的 Landing 下一项先确认中英文与开关两态范围，再修改 `app/templates/main/landing.html` 并做桌面/移动端检查。
- 阻塞项：无；生产注册持续开放，异常关闭条件仍以 [开放注册计划](../docs/plans/2026-08-09-open-registration.md) 为准。
- 权威规格：[开放注册短计划](../docs/plans/2026-08-09-open-registration.md)。
- 当前计划：[docs/plans/2026-08-09-open-registration.md](../docs/plans/2026-08-09-open-registration.md)（Approved）。
- 详细进度：用户确认真实生产注册成功；服务 active、settings/quota 均为 7、认证邮件 sent 且服务 error 为 0，均为会话 claim。
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
