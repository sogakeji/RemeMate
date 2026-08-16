# Current handoff

> handoff@e837205 · phase: language closure and staging AI verification · checked: 2026-08-16

- 当前目标：完成语言支持收敛；保留已完成的 AI 语言功能修复；下一阶段处理 Review Story 多语言稳定性二次优化。
- 当前阶段：`master` 上存在本轮未提交改动；产品界面仅支持简体中文/英语，AI 支持中文/英文/法语/日语/韩语/西班牙语，阅读器仅支持中文/英语/法语/日语，德语/俄语仅保留历史兼容并从新入口隐藏。
- staging 状态：新云机迁移已到 `e8f9a0b1c2d3`；`flask doctor --strict`、服务 active、内网 `/healthz` 200 及错误日志检查通过。未触碰生产环境、生产数据、环境文件或词典目录；公网 staging DNS/vhost 尚未配置。
- AI 真实复测：一键填充/例句/笔记六语种全通过；造句批改六语种全通过；复习小故事英文、日文、韩文、西班牙文通过，中文/法文在有界重试后仍有 `invalid_schema`，韩文存在首次失败后重试成功的波动。
- 自动化状态：新云机相关定向测试 **101 passed, 2 deselected**。详细进度、部署边界和复测结论见 [docs/HANDOFF.md](../docs/HANDOFF.md)。
- 下一动作：按 [docs/BACKLOG.md](../docs/BACKLOG.md) 的“Review Story 多语言稳定性二次优化”建立独立修复切片；先补细分错误码、单 provider 重试、脱敏观测和 fake-provider 回归，再重跑六语种 staging smoke。修复验收前不得宣称短故事六语种稳定可用或部署生产。
- 工作树纪律：保留现有用户改动，不 reset、stash、覆盖、merge、push 或部署；修改项目文件前先运行 `git status --short --branch`，并将当前 HEAD 与本 handoff 锚点比较。
- 建议技能：`diagnosing-bugs`（短故事输出不稳定）、`tdd`（provider/validator 回归）、`code-review`（修复切片审查）。
- 文档导航：[navigation.yaml](./navigation.yaml)
- 证据账本：[evidence.yaml](./evidence.yaml)
- 状态快照：[state.yaml](./state.yaml)
