# Practice 浏览器语音控制短计划

> 日期：2026-09-05
> 分支：`feature/practice-voice-controls`（从 `master@83fc2b5` 新建）
> 状态：用户已验收，`0fc53f4` 已合并本地 master；未 push、未部署生产。

## 验证记录（2026-09-05）

- 新云机 Practice 集成 49 passed，相关单元 24 passed，Node voice 与 JS 语法检查通过。
- 功能全量 871 passed / 8 failed；基线 `83fc2b5` 为 870 passed / 相同 8 failed；不是全绿。
- 用户使用 8894 预览验收通过。该预览与 8892 共享 staging 数据库，只隔离代码和进程。
- 操作遗留、测试账号及后续边界见 [HANDOFF](../HANDOFF.md)。

## 目标

让用户在 Practice 开始页主动选择当前学习语言可用的浏览器 voice、试听并调整语速；偏好按语言保存在浏览器本地，答题页播放时复用。继续使用客户端 `speechSynthesis`，不改变 Practice 题目、评分或额度语义。

## 已确认 seams

| Seam | 观察面 | 本轮覆盖 |
| --- | --- | --- |
| A. 浏览器偏好接口 | `practice.js` 导出的 voice/rate 纯函数 | voice 与语速按语言保存；损坏数据、越界语速和已消失 voice 安全回退 |
| B. HTTP 页面契约 | `/practice` 开始页 HTML 与现有 Practice 页面 | 有可练习题时输出 voice 选择、语速选择和试听控件；不改变无 voice 阻断逻辑 |
| C. 播放用户行为 | 页面控件经 `practice.js` 调用浏览器 `speechSynthesis` | 用户选择即时持久化；试听与答题播放使用所选 voice/rate；只在用户点击后播放 |

不测试私有 helper，不 mock 内部协作者，不增加数据库侧偏好断言。

## 切片与验收

每个切片执行一条 RED → 最小 GREEN，再进入下一条。

### Slice 1 — 按语言保存安全语速

- 默认语速 `1.0`，允许范围 `0.7–1.2`。
- localStorage key 按语言前缀隔离。
- 非数字、损坏或越界值回退/钳制到安全值。
- 现有 voice 存储格式保持兼容。

### Slice 2 — 开始页 voice 与语速控件

- 匹配 voice 加载后，以现有稳定排序填充选择框。
- 恢复已保存 voice；voice 已消失时回退首选 voice 并更新本地偏好。
- 用户更改 voice 或语速时立即保存。
- 无匹配 voice 时维持现有状态提示、重试按钮和禁止开始行为。

### Slice 3 — 试听与答题播放

- 开始页提供试听按钮；只在 click 路径调用 `speak()`。
- 试听和题目播放都使用当前语言已保存的 voice 与 rate。
- 法语、日语、中文偏好互不覆盖。

## 非目标

- 云端或服务端 TTS
- 数据库迁移、用户设置表、跨设备同步
- 新语言或 Practice 页面重设计
- 自动播放、生产部署、push
- Review Story 或 SEO 工作

## 测试

- `node tests/unit/test_practice_voices.js`
- `pytest tests/unit/test_practice_voices.py --noconftest -q`
- Practice 相关集成测试
- `git diff --check`
- 按仓库风险规则决定是否运行全量 `pytest -q`

## 完成定义

三条 seams 的目标行为都有回归覆盖；法语、日语、中文现有 voice discovery 与 Practice HTTP 流程保持通过；未进行 push 或部署。
