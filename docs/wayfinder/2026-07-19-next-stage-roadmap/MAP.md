# RemeMate 下一阶段产品路线 Wayfinder

## Destination

形成一份可交付给开发阶段的下一阶段路线图：明确安全前置、复习短故事、复习后输出、SessionPad
带语境候选和闭测观察面板的顺序、依赖、MVP、成功指标与停止条件。地图只解决决策，不实现功能。

## Notes

- 原规划时权威仓库为 WSL `/root/rememate`；丢盘后恢复的本地权威仓库为
  `D:\home\RemeMate` 的 `master`，当前测试闸门见 `docs/HANDOFF.md`。
- 第一性目标：用户因为自己真实遇到的词和句子被 RemeMate 帮他记住并用出来，而持续回来。
- AI 是增强层，不得成为复习、保存、候选审核或手动整理的门禁。
- 安全和数据可信度事项以 `docs/BACKLOG.md` 为唯一待办源。
- 本地图已经完成，没有开放票；恢复来源见 `RECOVERY.md`。

## Decisions so far

- [目标与判断标准](resolved/01-goal-and-evaluation.md) — 保持三个月目标，用真实使用和输出判断价值。
- [复习短故事的产品边界](resolved/02-review-story-boundary.md) — 故事是条件触发的复习后脚手架，并连接现有造句。
- [SessionPad 候选语境的定义](resolved/03-sessionpad-context-boundary.md) — AI 从伙伴反馈原文定位短语境，不另编例句。
- [路线顺序与范围边界](resolved/04-order-and-scope.md) — 先可信地基，再故事、SessionPad、观察面板和后续体验批次。
- [核验复习会话与每日选词数据](resolved/05-review-session-data.md) — 无需复习会话表；按本地日和语言聚合去重日志，使用私有幂等缓存。
- [复习评分幂等边界](resolved/06-review-grade-idempotency.md) — 以到期时间作为尝试版本，Web/Bark 锁同一词行并原子校验。
- [复习完成卡与短故事体验](resolved/07-review-story-experience.md) — 选择独立复习回执；完成卡不变，符合条件才在其下方显示。
- [多语言短故事生成契约](resolved/08-story-generation-contract.md) — 最小输入快照、逐句双语 JSON、严格锚点校验、两次尝试和安全写作交接。
- [SessionPad 带语境候选数据模型](resolved/09-sessionpad-context-model.md) — 交换来源、候选短语境和最终例句分离，统一 AI/人工降级契约。
- [SessionPad 候选审核原型](resolved/10-sessionpad-candidate-review-prototype.md) — 单候选聚焦审核，吸收缺语境空态和 AI 降级提示。
- [闭测观察合同与最终实施路线图](resolved/11-observation-and-final-implementation-roadmap.md) — 三个串行可回滚分支、隐私安全指标及测试/部署/停止门。

## Status

- 地图完成，无开放规划票文件；以下为 2026-07-27 实施状态。
- 产品下一阶段顺序为 review story、SessionPad context candidates、closed-beta observation。
- `feature/review-story-v1` 已完成 RS1 至 RS4：数据/RLS、生成契约、事务状态机、provider 编排、
  复习回执、显式写作交接、7/180 天保留清理和运维说明；GCP 最终全量 **620 passed**。
- 下一步是审查后合并并部署 Review Story；随后才能从更新后的干净 `master` 创建
  SessionPad context-candidate 分支。
- 生产仍未部署恢复修复或 Review Story；不得绕过目标环境 PostgreSQL、全量测试和 doctor 闸门。

## Out of scope

- 单词生图。未来若重开视觉方向，只考虑从短故事派生四格或多格漫画。
- SessionPad 实时协作、聊天室、免登录 guest、小组交换。
- 新收词入口、大规模 UI 重做、Daily Task Card v2。
- 用户自主开放注册；继续按 BACKLOG 触发门槛处理。

