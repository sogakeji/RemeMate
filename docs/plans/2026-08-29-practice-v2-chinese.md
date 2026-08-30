# Practice V2 中文短计划

> 日期：2026-08-29
> 分支：`feature/practice-v2-chinese`（从 `master` `950aa25` 新建，不改写已有 commits）
> 状态：用户已确认 TDD seams、默认产品路径与切片；本文件是实施契约。
> 依据：[docs/research/2026-08-29-practice-v2-chinese-dictation.md](../research/2026-08-29-practice-v2-chinese-dictation.md)、日语计划 [2026-08-29-practice-v2-japanese.md](./2026-08-29-practice-v2-japanese.md)

## 目标

在不改变法语、日语听写行为的前提下，让当前学习语言为 `zh` 的用户可以完成一轮最多 5 题的语境听写：精确唯一子串挖空、拒绝明显真子串、严格字形判定、浏览器 `zh` voice 发现（默认 `zh-CN`）与本地持久化。

## 已确认 seams

只在这三处观察行为，不测私有 helper、不 mock 内部协作者。

| Seam | 观察面 | 本轮覆盖 |
| --- | --- | --- |
| A. service 公共行为 | `prompt_parts`、`normalize_answer`、`target_occurs_uniquely`、`get_eligible_items` / `get_start_state` / `start_session` / `submit_answer` | 按 `language_code` 入池、唯一挖空、答案归一 |
| B. HTTP 用户行为 | `/practice` 起止、答题、反馈 HTML | 中文用户可开始/答题/反馈/完成；模板动态 `lang=zh`，voice locale=`zh-CN` |
| C. 浏览器契约 | 页面 data 属性 + `practice.js` 可导出的 voice 纯函数 | 输出中文 voice 配置；发现 `zh-CN`、`zh_CN`、`zh`；稳定排序；已存 `voiceURI`/`name`/`lang` 回退；禁止自动播放 |

真实音质、Xiaoxiao/Tingting 是否好听：tencent-new 人工矩阵，本轮不自动化。

## 非目标

- 简繁互转、拼音/注音判对、同音字、儿化剥离
- 云端 TTS、jieba、OpenCC、扩大 `pypinyin` 使用面、任何新依赖
- 数据库迁移、用户设置表、跨设备同步 voice
- 把 `cmn-*` / `yue-*` 当作默认中文 voice
- 自动播放、`speak()` 放在非 click 路径
- push、部署、改 staging 服务、动生产数据、连接 tencent-old
- 改写已有日语 commits；amend；动 8892；启 8893

**停止条件：** 若实施中发现必须做简繁选择或 schema migration，停下来汇报。当前研究结论：不必须。

## 默认产品路径

- `current_language=zh`
- TTS 默认 `zh-CN`
- 字形严格：NFKC 折全半角，不简繁互转，不接受拼音
- 无空格精确子串唯一定位；长度为 1 且邻接 Han 视为明显真子串并拒绝
- `中国`∈`中国人` 这类长度 ≥2 的复合词真子串：V1 接受（与日语 `日本`∈`日本人` 同类），不引入分词器
- 保留 `ja`/`fr` 行为

## 切片与验收

每个切片：先写 **一个** 经公开 seam 失败的测试并展示 RED，再最小实现到 GREEN，再写下一条。不批量预写测试，不做无关重构。

### Slice 1 — 中文精确唯一子串挖空与入池

- 法语继续 `\w` 边界（`ß cible` 回归保持）。
- 日语继续 NFC 精确子串恰好一次（`今日は学校に行きます。` 回归保持）。
- 中文：NFC 后精确子串恰好一次则挖空；0 次或 ≥2 次不挖（`prompt_parts` 返回整句 + 空 after）；长度为 1 且左右任一侧为 Han 则拒绝。
- `get_eligible_items` / `get_start_state` / `start_session` / `record_voice_unavailable` 允许 `zh`。
- 验收：`今天我去学校上课。` + `学校` → `今天我去` / `上课。`；`校` 不入池；同一目标出现两次不入池；`ja`/`fr` 仍绿。

### Slice 2 — 中文 NFKC 判定

- `submit_answer` / `normalize_answer` 按 `language_code` 分支。
- 中文：NFKC + 去空白 + 去掉明确中文标点（见研究 §5.2）。全角 `３`≡`3`，全角 `Ａ`≡`A`。
- 不宽松：拼音、繁体对简体、`花` vs `花儿`、`三` vs `3`、同音字。
- 标点/空白：测试钉死剥离后相等或 `EmptyAnswerError`。
- 法语 `casefold` 与日语 `ー`/促音行为保持不变。
- 验收：`学校` 对 `学校` 为真；`xuexiao` 为假；`學校` 为假；仅 `。` 为空答案。

### Slice 3 — HTTP / 模板动态 zh / zh-CN

- 中文用户 GET `/practice` 看到可开始（有合格例句时），POST start → 题目 → 答题 → 反馈 → 完成。
- 题目/反馈/完成句的 `lang` 与 voice locale：`zh` → `zh-CN`（`ja`→`ja-JP`，`fr`→`fr-FR` 不变）。
- 开始页对 `zh` 不再走「未开放」分支。
- 验收：集成测试覆盖中文 1 题会话 + 一组 5 个唯一例句可开始；日语/法语 HTTP 仍绿。

### Slice 4 — JS voice 最小扩展

- 页面输出 `data-practice-voice-lang="zh"` 与 `data-practice-voice-locale="zh-CN"`。
- 在现有通用函数上加中文样例：过滤 `zh-CN`、`zh_CN`、`zh`；排序偏好精确 `zh-CN` 再 `localService`；回退 URI → name+lang → lang → 第一条。
- 不复制 voice 逻辑，不新增自动播放路径。
- 验收：Node 纯函数测试 + HTTP 断言 data 属性。无浏览器音质断言。

## 测试运行

- 纯 unit（不连库）：本地 `pytest tests/unit/test_practice.py tests/unit/test_practice_voices.py --noconftest -q`；`node tests/unit/test_practice_voices.js`。
- `git diff --check`。
- 需要数据库的目标/全量：tencent-new **新**隔离目录 `/home/ubuntu/rememate-practice-zh-v2` + `rememate_test`（端口 55432）。不覆盖 `rememate-test` / `rememate-practice-dictation` 上的未知改动，不碰 `rememate_staging`、不下 8892 staging 服务、不启 8893。
- 相关 Practice 套件后 `python -m pytest -q`。准确对比已知 5 个非 Practice 失败；若无新失败再启 8894 中文预览。
- 安全 CLI 建独立中文测试账号与 5 个唯一例句（`flask create-user` + 词服务 `add_word`，不直接写 DB）。
- 本机隧道。不 push、不部署。

## 完成定义

中文切片全绿；`ja`/`fr` 回归全绿；研究报告与本计划已提交；88894 预览与账号已就绪后停下等待真机验收。

## 5 个预览例句（唯一子串、长度 ≥ 2）

| 词 | 例句 |
| --- | --- |
| 学校 | 今天我去学校上课。 |
| 咖啡 | 早上喝了一杯咖啡。 |
| 音乐 | 她喜欢听音乐。 |
| 火车 | 我们坐火车去北京。 |
| 朋友 | 我和朋友看电影。 |
