# Practice V2 日语优先短计划

> 日期：2026-08-29
> 分支：`feature/practice-v2-japanese`（从当前 `master` ahead 3 新建，不改写已有 commits）
> 状态：用户已确认 TDD seams 与切片路径，本文件是实施契约。
> 依据：[docs/research/2026-08-29-practice-v2-japanese-dictation.md](../research/2026-08-29-practice-v2-japanese-dictation.md)、[docs/BACKLOG.md](../BACKLOG.md)

## 目标

在不改变法语听写行为的前提下，让当前学习语言为 `ja` 的用户可以完成一轮最多 5 题的语境听写：精确唯一子串挖空、严格字形判定、浏览器 `ja` voice 发现与本地持久化。

## 已确认 seams

只在这三处观察行为，不测私有 helper、不 mock 内部协作者。

| Seam | 观察面 | 本轮覆盖 |
| --- | --- | --- |
| A. service 公共行为 | `prompt_parts`、`normalize_answer`、`get_eligible_items` / `get_start_state` / `start_session` / `submit_answer` | 按 `language_code` 入池、唯一挖空、答案归一 |
| B. HTTP 用户行为 | `/practice` 起止、答题、反馈 HTML | 日语用户可开始/答题/反馈；模板动态 `lang` |
| C. 浏览器契约 | 页面 data 属性 + `practice.js` 可导出的 voice 纯函数 | 输出目标 locale 与持久化配置；BCP47 前缀（连字符/下划线）；`voiceURI`/`name`/`lang` 回退；禁止自动播放 |

真实音质、Nanami/Kyoko 是否好听：tencent-new 人工矩阵，本轮不自动化。

## 非目标

- 中文（`zh-CN` / `zh-TW`）一律不做
- 云端 TTS、fugashi、pykakasi、任何新依赖
- 数据库迁移、用户设置表、跨设备同步 voice
- 汉字读音判对、平片互认、促音/小假名/长音宽松
- 自动播放、`speak()` 放在非 click 路径
- push、部署、改 staging 服务、动生产数据、改写已有 3 个 master commits

## 切片与验收

每个切片：先写 **一个** 经公开 seam 失败的测试并展示 RED，再最小实现到 GREEN，再写下一条。不批量预写测试，不做无关重构。

### Slice 1 — 语言策略与精确唯一子串挖空

- 法语继续 `\w` 边界（现有 `ß cible` 回归保持）。
- 日语：NFC 后精确子串恰好一次则挖空；0 次或 ≥2 次不挖（`prompt_parts` 返回整句 + 空 after）；入池同样要求恰好一次。
- `get_eligible_items` / `get_start_state` / `start_session` / `record_voice_unavailable` 允许 `ja`，其它语言仍关闭。
- 验收：`今日は学校に行きます。` + `学校` → `今日は` / `に行きます。`；同一目标出现两次不入池；法语边界用例仍绿。

### Slice 2 — 日语 NFKC 答案判定

- `submit_answer` / `normalize_answer` 按 `language_code` 分支。
- 日语：NFKC + 去空白 + 去掉明确标点（**保留** `ー`）。半角片假名 ≡ 全角。
- 不宽松：汉字≠读音假名；平≠片；`っ`≠`つ`；`ゃ`≠`や`；`ー` 不展开成 `おう`/`おお`。
- 法语 `casefold` + 空白折叠保持不变。
- 验收：`ｺｰﾋｰ` 对 `コーヒー` 为真；`がっこう` 对 `学校` 为假。

### Slice 3 — HTTP / 模板动态 lang

- 日语用户 GET `/practice` 看到可开始（有合格例句时），POST start → 题目 → 答题 → 反馈 → 完成。
- 题目/反馈/完成句的 `lang` 与 voice locale 随会话语言：`ja` → `ja-JP`，`fr` → `fr-FR`。
- 开始页对 `ja` 不再走「未开放」分支。文案去掉「仅法语」硬编码，改为中性听写文案（i18n 键集合不变或仅改值）。
- 验收：集成测试覆盖日语 1 题会话；法语现有 HTTP 测试仍绿。

### Slice 4 — JS voice discovery

- 页面输出 `data-practice-voice-lang`（`ja` / `fr`）与默认 BCP47。
- 过滤 `/^ja([-_]|$)/i` 与法语同等的 `/^fr([-_]|$)/i`。
- 稳定排序后选择；`localStorage` 存 `{voiceURI, name, lang}`；回退：URI → name+lang → lang 前缀 → 第一条匹配。
- 只在播放按钮 click 里 `speak()`；不在 `voiceschanged`/超时里自动朗读。
- 验收：Node 跑纯函数测试 + HTTP 断言 data 属性。无浏览器音质断言。

## 测试运行

- 纯 unit（不连库）：本地 `pytest tests/unit/test_practice.py --noconftest -q`（避开会清库的 autouse fixture）。
- 需要数据库的目标/全量：tencent-new 隔离目录 + `rememate_test`（端口 55432），不覆盖 `rememate-test` / `rememate-practice-dictation` 上的未知改动，不碰 `rememate_staging`、不下 staging 服务。
- 完成后：相关测试、`git diff --check`、tencent-new `pytest -q`。全绿再按逻辑 commit。不 push、不部署。

## 完成定义

日语切片全绿；法语回归全绿；研究报告与本计划已提交；人工 TTS 矩阵列为剩余工作后停下等待指令。
