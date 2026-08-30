# Practice V2：中文听写与多语言扩展调研

> 研究日期：2026-08-29。只读仓库现状与官方/一手来源。本文不含实现。
> 仓库 HEAD：`950aa25`（master 已发布日语切片）。`.reme/handoff.md` 锚点仍为 `2b737d4`；以 Git HEAD 为准。
> 产品入口：[docs/BACKLOG.md](../BACKLOG.md) P0「多语言扩展」；日语切片已合入 master。
> 默认产品路径（用户已确认）：`current_language=zh`，TTS 默认 `zh-CN`，字形严格，不接受拼音、不简繁互转，NFKC 只折全半角，无空格精确子串唯一定位并防明显真子串，保留 `ja`/`fr` 行为。

外部事实只引用规范、浏览器引擎源码/缺陷、Unicode、官方文档和可核验的开源仓库。Readium 语音清单是一手观测，不是 W3C 契约。

**是否必须做简繁选择或 migration：否。** 产品语言码已是 `zh`；简繁是字形问题不是 schema 问题。本轮不停止。

---

## 1. 仓库现状（只读）

日语切片已把 Practice 从法语-only 扩到 `{fr, ja}`。中文仍被语言门闩挡住。

### 1.1 语言门闩

`PRACTICE_LANGUAGES = frozenset({"fr", "ja"})`。[app/services/practice.py](../../app/services/practice.py)

`get_eligible_items` / `get_start_state` / `start_session` / `record_voice_unavailable` 均在 `language_code not in PRACTICE_LANGUAGES` 时返回空或不创建会话。

开始页模板只对 `fr`/`ja` 渲染开始按钮，其它语言走「暂未开放」。[app/templates/practice/start.html](../../app/templates/practice/start.html)

产品语言表已含 `zh`（AI / 阅读 / 词表）。[app/services/languages.py](../../app/services/languages.py) UI `html lang` 在中文界面已是 `zh-CN`。[app/templates/base.html](../../app/templates/base.html)

**不需要 migration。** `users.current_language` / `word_lists.language_code` 已存 `zh`。TTS 地区是页面 `data-practice-voice-locale` 与 JS 排序问题，不是新列。

### 1.2 题目入池与挖空

法语：NFC + `casefold` 后 `(?<!\w)…(?!\w)` 恰好一次。

日语：NFC 后精确子串恰好一次；`_japanese_unique_span` 用 `str.find` 两次。0 次或 ≥2 次不挖、不入池。

**日语没有实现「日本 ∈ 日本人」拒绝。** 研究文档曾列为必须项，落地测试只覆盖「出现两次」与「唯一子串」。中文切片要补「明显真子串」，且不得改变日语现网行为。

Python `\w` 含汉字，法语边界不能用于中文连续文本。与日语同一原因。[Python `re` `\w`](https://docs.python.org/3/library/re.html)

### 1.3 答案判定

日语：`NFKC` + 去掉 `_JA_PUNCTUATION` + 删除空白。不接受假名替代汉字。

法语：NFC + 空白折叠 + `casefold`。

中文目前会走法语分支，`casefold` 对汉字无操作，全角 `３` 也不会变成 `3`。

词身份 `normalize_word_identity` 仍是 `strip().lower()`，不做 NFC/NFKC。[app/services/words.py](../../app/services/words.py) Practice 判定不得改词身份。

### 1.4 客户端 TTS

[app/static/practice.js](../../app/static/practice.js) 已是按前缀的通用函数：

- `matchesLang`：`/^${prefix}([-_]|$)/i`
- `filterByLang(voices, wantedLang)`，`wantedLang` 来自 `data-practice-voice-lang`（产品码 `ja`/`fr`）
- `sortVoices(..., wantedLocale)`，精确 locale 优先，再 `localService`，再 `name`
- `pickVoice`：`voiceURI` → `name+lang` → `lang` → 排序后第一条
- `localStorage` 键 `rememate.practice.voice.${prefix}`
- 只在播放按钮 `click` 里 `speak()`；`voiceschanged` + 900ms 超时；禁止自动播放

给 `zh` + locale `zh-CN` 时，现有 JS **已经**能匹配 `zh-CN` / `zh_CN` / `zh` / `zh_CN_#Hans`。中文切片应测这些契约，不复制一套 voice 逻辑。

### 1.5 阅读模块已有的中文能力（Practice 判定不得扩大使用面）

- 句界 `。！？，；`。[app/services/reading/context.py](../../app/services/reading/context.py)
- CJK 相邻字之间的空格折叠，范围 `[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]`。[app/services/reading/parsers.py](../../app/services/reading/parsers.py) · [dictionary.py](../../app/services/reading/dictionary.py)
- 中文读音：可选 `pypinyin`（MIT，阅读注音用）。[requirements.txt](../../requirements.txt)
- 在线 dictionary API 仍 `if False`，Practice 不要打开。

阅读用划词偏移，不靠自动分词决定词界。Practice 只有 `example` + `word.word`。

---

## 2. Web Speech API 与中文 locale

规范：[Web Speech API Draft, 2026-08-10](https://webaudio.github.io/web-speech-api/) · [MDN `getVoices()`](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/getVoices) · [MDN `SpeechSynthesisVoice`](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice) · [BCP 47 / RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html)

日语研究 §2 的契约全部成立，此处只补中文差异。

### 2.1 产品码 `zh` vs voice `lang`

BCP 47：`zh` 是 ISO 639-1 宏语言；地区 `zh-CN` / `zh-TW` / `zh-HK`；书写 `zh-Hans` / `zh-Hant`。规范不枚举 UA 返回哪些 voice。

Chrome 扩展 TTS 文档把 `zh-CN` 列为语言-地区示例。[Chrome `tts` API `lang`](https://developer.chrome.com/docs/extensions/reference/api/tts)

### 2.2 浏览器实际返回的 `lang`（一手观测 + Chromium 缺陷）

| 环境 | 实测/缺陷记录的 `lang` | 现有 `/^zh([-_]|$)/i` |
| --- | --- | --- |
| Chrome 桌面 | `zh-CN`、`zh-TW`、`zh-HK`（「普通话（中国大陆）」「國語（臺灣）」「粤語（香港）」） | 全匹配 |
| Chrome Android / Clank | `zh_CN_#Hans`、`zh_TW_#Hant`、`zh_HK_#Hans`/`zh_HK_#Hant`、`yue_HK_#Hant` | `zh_*` 匹配；`yue_*` **不匹配** |
| 下划线 | `zh_CN`（与日语 `ja_JP` 同类） | 匹配 |

来源：[Chromium 40739658](https://issues.chromium.org/issues/40739658)（Clank 返回非严格 BCP 47，含 `#Hans`/`#Hant`）；桌面对照同缺陷描述。

**`yue-HK` 默认排除是正确的：** 粤语朗读汉字不是普通话听写。V1 不把粤语当中文 voice。

Readium 目录用 ISO 639-3 `cmn-CN` 作 catalog id，`altLanguage` 才是 `zh-CN`。[readium/speech `json/cmn.json`](https://github.com/readium/speech/blob/main/json/cmn.json) · [`json/yue.json`](https://github.com/readium/speech/blob/main/json/yue.json)

V1 **不**把 `cmn-*` 当作 `zh` 前缀。若某 UA 真把 `voice.lang` 设成 `cmn-CN`，会被当成无中文 voice 走 blocked。Chrome 桌面/Android 的一手记录是 `zh-CN` / `zh_CN_#Hans`，不是 `cmn-CN`。人工矩阵需记下实际 `lang`。

### 2.3 默认选哪套 locale

产品码只有 `zh`。默认 `zh-CN`：

1. 页面 `data-practice-voice-locale="zh-CN"`
2. `sortVoices(..., "zh-CN")` 精确匹配优先，因此 `zh-CN` 压过 `zh-TW`/`zh-HK`
3. 无 `zh-CN` 时回退到其它已过滤的 `zh*`（含繁体地区），再 `localService`，再 `name`

这不是简繁转换，只是 voice 地区偏好。用户记住的 `{voiceURI,name,lang}` 仍优先。

### 2.4 各平台观测（Readium，非规范）

Mandarin catalog：[cmn.json](https://github.com/readium/speech/blob/main/json/cmn.json)

| 环境 | 普通话 voice（节选） | `altLanguage` |
| --- | --- | --- |
| Edge 桌面 | Xiaoxiao / Xiaoyi / Yunxi / Yunjian Natural | `zh-CN` |
| Chrome 桌面 | `Google 普通话（中国大陆）`；另有台湾、香港 Google voice | `zh-CN` / `zh-TW` / `zh-HK` |
| Windows | Huihui / Yaoyao / Kangkang | `zh-CN` |
| macOS / iOS | Tingting、Yu-shu、Li-Mu 等；名称会本地化 | `zh-CN` |
| Android | `cmn-CN-x-ccc-*` 等 nativeID；`altLanguage` `zh-CN` | `zh-CN` |

香港粤语在 [yue.json](https://github.com/readium/speech/blob/main/json/yue.json)：Sinji、HiuMaan、`Google 粤語（香港）`。V1 不选它们作默认。

Chrome 桌面 Google voice 仍有约 14 秒切断。[Chromium 41294170](https://issues.chromium.org/41294170) Practice 单句通常短于此。

iOS：无用户手势则 `speak()` 静默失败。[WebKit `SpeechSynthesis.cpp`](https://github.com/WebKit/WebKit/blob/main/Source/WebCore/Modules/speech/SpeechSynthesis.cpp) 现有 click-only 路径保持。

### 2.5 回退链（沿用日语，不改算法）

1. 已存 `{voiceURI, name, lang}`
2. 精确 `voiceURI`
3. `name+lang`
4. `lang` 全等（`zh-CN` 与 `zh_CN` 在这一步不相等，与日语 `ja-JP`/`ja_JP` 相同）
5. 排序后第一条 `zh*`（精确 `zh-CN` 已在 sort 里提前）

不要按下标持久化。不要自动播放。

---

## 3. 简繁策略（产品，不是 TTS locale）

Unicode 把多数简繁对编码为**不同统一汉字**，不是兼容分解。本机实测 NFKC：

| 对 | NFKC 后相等？ |
| --- | --- |
| 发 U+53D1 / 髮 U+9AEE | 否 |
| 国 / 國 | 否 |
| 里 / 裡 | 否 |
| 台 / 臺 | 否 |
| 为 / 為 | 否 |
| 儿 / 兒 | 否 |

[UAX #15](https://www.unicode.org/reports/tr15/)：NFKC 做兼容分解。简繁不是兼容映射。OpenCC 才做简繁与地区词。[OpenCC Apache-2.0](https://github.com/BYVoid/OpenCC)

**V1：不引入 OpenCC，不互转，不按 UI locale 猜简繁。** 词条是什么字形，答案就必须是什么字形。TTS 用 `zh-CN` 读整句；若词库是繁体，发音可能不理想，这是已知限制，用人工矩阵记录，不因此开 migration。

后排（非本切片）：用户可选 `zh-TW` voice；或词表级 `script` 字段。两者都不是必须，本轮不做。

---

## 4. 无空格挖空与明显真子串

### 4.1 精确唯一子串

与日语相同：NFC 后 `sentence.count(target) == 1`（实现上两次 `find`），用该跨度挖空。0 次或 ≥2 次：整句不挖、不入池。

法语继续 `\w` 边界。不要用策略 A 替换法语。

### 4.2 为什么不能「前后不是汉字」一刀切

中文书面语几乎全是 Han。若要求左右都不是汉字，则「今天去学校。」里的 `学校` 也会被拒（`去` 是汉字）。日语因有假名助词，同一规则碰巧能挖 `学校`；中文没有这条缝。这就是日语落地最终没做 CJK 弱边界的原因。

UAX #29 词边界对 CJK 也不是语言学词。不要用它挖空。

### 4.3 V1「明显真子串」

可测、无分词器：

**唯一精确子串成立之后，若目标长度为 1 且该跨度任意一侧仍是 Han（阅读模块同一范围 `\u3400-\u9fff\uF900-\uFAFF`），则拒绝入池、不挖空。**

| 句 | 目标 | 结果 |
| --- | --- | --- |
| `今天我去学校上课。` | `学校` | 入池；左右 `今天我去` / `上课。` |
| `学校的附近还有一所学校。` | `学校` | 拒绝（两次） |
| `今天我去学校上课。` | `校` | 拒绝（长度 1，左侧 `学` 为 Han） |
| `中国人很多。` | `中国` | **入池**（长度 2；与日语 `日本`∈`日本人` 同类，V1 不猜复合词） |

单字词只有贴在标点/拉丁/句首句尾且另一侧不是 Han 时才入池。这是产品限制。不要用 jieba 猜「哪一次」。

### 4.4 多次出现

与法语/日语一致：出现 ≠ 1 则跳过。不要猜第几次。

---

## 5. 答案判定

听写比的是用户输入与词库目标字符串，不是语音识别。

### 5.1 Unicode 正规化

[UAX #15](https://www.unicode.org/reports/tr15/)：NFC 不折半角/全角；NFKC 将半角片假名与全角 ASCII 折合。本机实测：

| 输入 | NFKC | 产品 |
| --- | --- | --- |
| `３` | `3` | 视为同一答案 |
| `Ａ` | `A` | 视为同一答案 |
| U+3000 表意空格 | ASCII space | 再删空白 |
| `，` U+FF0C | `,` | 随标点剥离 |
| `①` | `1` | NFKC 额外折合；**不是**全半角。测试不把它当正确性要求，也不为它关 NFKC |
| `三` vs `3` | 不相等 | 不互认 |
| 简繁对 | 不相等 | 不互认 |

产品「NFKC 只折全半角」的含义：用 NFKC 解决全半角，**不要**指望它做简繁。实现沿用日语整串 `unicodedata.normalize("NFKC")`，测试钉住全半角与不简繁。入库展示仍保持原文/NFC。

挖空侧先 NFC 再定位，避免 NFKC 改变长度导致偏移错位。

### 5.2 空白与标点（测试钉死）

判定用，不改展示：

1. NFKC
2. 删除空白（含 ASCII、NBSP、U+3000）
3. 删除中文标点集合（日语集合 + 中文引号/书名号/冒号分号）：
   `。．、，·・.,!！?？：；「」『』""''（）()[]【】《》〈〉…―—～〜`
4. 不删除汉字、拉丁字母、阿拉伯数字、`儿`

仅空白/标点 → `EmptyAnswerError`。目标含标点的短语极少；入池用同一套剥离后再比，或随唯一子串自然处理。测试用无标点目标。

### 5.3 拼音默认不允许

拼音是拉丁转写，不是汉字。NFKC 不会把 `xuexiao` / `xuéxiào` / `ㄒㄩㄝ` 变成 `学校`。

阅读模块的 `pypinyin`（MIT）只用于阅读注音。[PyPI pypinyin MIT](https://pypi.org/project/pypinyin/) Practice 判定路径**不要**调用它。同音字（`行`/`形`）字形不同则判错。

### 5.4 儿化

`花` ≠ `花儿`。不要剥 `儿`/`爾`。`儿` vs `兒` 是简繁，也不互认。

### 5.5 异体字

统一汉字不同码位即不同答案。不要 Unihan `kTraditionalVariant` / `kZVariant`。OpenCC 后排。

### 5.6 数字与拉丁

- 全角数字 `３` ≡ `3`（NFKC）
- 汉字数字 `三` ≢ `3`
- 词条/例句中的拉丁（`iPhone`、`WiFi`）走精确子串；不 `casefold`（中文分支无 `casefold`）。测试钉：目标 `iPhone` 时 `iphone` 为错，除非另开拉丁策略（本轮不开）

### 5.7 推荐的 `normalize_answer` 中文分支

与日语函数分离，避免破坏 `ー` 保留与法语 `ß`/`casefold`。

```
NFKC(value)
→ 删除中文标点集合
→ 删除空白
→ 返回
正确：normalized(answer) == normalized(target)
```

不加拼音、不加简繁、不加儿化剥离、不加同音字。

---

## 6. IME composition 与移动端避坑

规范：[UI Events `compositionstart` / `isComposing`](https://www.w3.org/TR/uievents/#compositionstart) · [Key events during composition](https://www.w3.org/TR/uievents/#keys-composition)

- composition 期间 `keydown`/`keyup` 的 `isComposing` 必须为 true。
- 退出 composition 的那次 `keydown` 仍为 `isComposing: true`。
- 历史实现：IME 中 `keyCode === 229`（Windows VK_PROCESSKEY）。`keyCode` 已 deprecated，新代码用 `isComposing`；Safari 曾在确定键上把 `isComposing` 提前打成 false（[WebKit 165004](https://bugs.webkit.org/show_bug.cgi?id=165004)）。

**当前 Practice 用原生 `<form>` POST，没有 JS 拦截 Enter。** 浏览器通常不会把 IME 确定键当成提交。V1 不要新增「按 Enter 提交」的 keydown 逻辑。若以后加，必须 `event.isComposing || event.keyCode === 229` 则 return。

题目页已有 `autocomplete="off"`（form）、`spellcheck="false"` `autocapitalize="off"` `autocorrect="off"`。`lang="{{ voice_locale }}"` 在中文会话会变成 `zh-CN`，有助于 IME 提示。不要改成 `type="search"`。不要在 `input`/`compositionupdate` 上做即时判分。

移动端：

- iOS `speak()` 必须在 click 里（已满足）
- Android `zh_CN` / `zh_CN_#Hans`（现有前缀正则覆盖）
- 900ms voice 超时沿用；无 voice 走 blocked
- 候选栏遮挡输入：不做特殊 CSS，人工矩阵记录
- Edge Android：Readium 记空列表 → blocked

---

## 7. 开源实现与许可证

政策延续 [docs/THIRD_PARTY.md](../THIRD_PARTY.md)。**V1 不新增依赖。**

| 项目 | 相关能力 | 许可证 | 对 RemeMate |
| --- | --- | --- | --- |
| [OpenCC](https://github.com/BYVoid/OpenCC) | 简繁/地区词 | Apache-2.0 | **不引入。** V1 不互转。 |
| [jieba](https://pypi.org/project/jieba/) | 中文分词 | MIT | 后排复合词挖空；V1 不用。 |
| [pypinyin](https://pypi.org/project/pypinyin/) | 汉字→拼音 | MIT | 阅读已用。Practice 判定不用。 |
| 阅读模块 Kaikki/Wiktionary `zh` | 词典 | CC BY-SA | 已批准外置数据。不要为听写打在线 API。 |
| CC-CEDICT | 汉英词典 | CC BY-SA 4.0 | 不引入本切片。 |
| [Lute v3](https://github.com/LuteOrg/lute-v3) | 阅读；中文常靠分词 | MIT | 可参考「无分词则无词界」；不要把 jieba 塞进最小切片。 |
| [readium/speech](https://github.com/readium/speech) | voice 观测 JSON | 观测数据 / CC0 谱系 | 排序参考，不是规范。 |
| Anki | 听写插件自定判定 | 主程序 AGPL-3.0 | 不复制。 |

判定用标准库 `unicodedata`；TTS 用现有 Web Speech。

---

## 8. 必须做 / 建议 / 后排

### 必须做

1. `PRACTICE_LANGUAGES` 加入 `zh`；其它语言仍关闭。
2. 中文挖空：NFC 精确子串恰好一次；长度 1 且邻接 Han 则拒绝。
3. 中文答案：NFKC + 去空白 + 去明确标点；不接受拼音/简繁/同音字。
4. `voice_locale("zh") == "zh-CN"`；模板 `lang` 与 data 属性随会话。
5. JS：证明现有前缀过滤接受 `zh-CN`/`zh_CN`/`zh`；排序偏好 `zh-CN`；三元组回退；click-only `speak()`。
6. 法语、日语回归全绿。
7. 无新依赖、无 migration、不改 env、不 push、不部署。

### 建议（失败不阻断入池）

1. 人工浏览器矩阵记录各机 `name`/`lang`/`voiceURI`。
2. 题目 `lang="zh-CN"` 以提示 IME。
3. 若日后加 Enter 提交，带 `isComposing` 守卫。

### 后排

1. OpenCC 简繁互认或用户选脚本。
2. jieba/词对齐处理 `中国`∈`中国人` 与同形多次。
3. 拼音/注音判对。
4. `cmn-*` voice 别名；粤语 `yue` 作为独立学习语言。
5. 云端 TTS；用户设置表同步 voice。
6. 服务端按 `zh-TW` 选默认 locale。

---

## 9. 推荐的最小中文切片

目标：法语、日语行为不变；`current_language=zh` 时用浏览器中文 voice 做最多 5 题语境听写；字形严格；挖空不靠空格。

范围：

1. Service：允许 `zh`；入池用 §4.1+§4.3；判定用 §5.7。
2. HTTP：中文用户可开始/答题/反馈/完成；`lang=zh`，`voice-locale=zh-CN`。
3. JS：现有通用函数 + 中文样例测试。无新 voice 实现副本。
4. 无新 Python 依赖。无数据库迁移。

明确不做：简繁转换、拼音判对、云 TTS、其它新语言、自动播放、改 staging/生产。

---

## 10. 测试矩阵

### 10.1 pytest（每次切片必跑）

| ID | 输入 | 期望 |
| --- | --- | --- |
| ZH-CLOZE-1 | `今天我去学校上课。` / `学校` | `今天我去` / `上课。` |
| ZH-CLOZE-2 | 同上 / `校` | 拒绝（明显真子串） |
| ZH-CLOZE-3 | 句中 `学校` 两次 | 拒绝 |
| ZH-CLOZE-4 | 日语 `今日は学校に行きます。` / `学校` | 仍绿 |
| ZH-CLOZE-5 | 法语 `ß cible` / `cible` | 仍绿 |
| ZH-ANS-1 | 目标 `学校`，答案 `学校` | 正确 |
| ZH-ANS-2 | 目标 `学校`，答案 `xuexiao` / `xuéxiào` | 错误 |
| ZH-ANS-3 | 目标 `学校`，答案 `學校` | 错误（繁体） |
| ZH-ANS-4 | 目标 `咖啡`，答案全角混排若仅全半角差异 | 按 NFKC 后全等则为正确 |
| ZH-ANS-5 | 目标 `花`，答案 `花儿` | 错误 |
| ZH-ANS-6 | 目标 `3` 或词内全角 `３` | `３`≡`3`；`三`≢`3` |
| ZH-ANS-7 | 答案仅空白/中文标点 | EmptyAnswerError |
| ZH-VOICE-1 | `zh-CN`、`zh_CN`、`zh` | 均匹配 zh 过滤器 |
| ZH-VOICE-2 | 同时有 `zh-CN` 与 `zh-TW`，wanted `zh-CN` | 精确 `zh-CN` 优先 |
| FR/JA-REG | 现有单测与集成 | 仍过 |

### 10.2 手工浏览器（实现后勾选，本轮自动化不做音质）

| 浏览器 | OS | 期望 | 必测 |
| --- | --- | --- | --- |
| Chrome | Windows | Google 普通话 / Huihui | 发现、播放、无自动朗读、IME 确定不误提交 |
| Edge | Windows | Xiaoxiao Natural | 同上；Natural 需联网 |
| Chrome | Android | `zh_CN` 或 `zh_CN_#Hans` | 下划线与 `#Hans`；未下载中文包时的回退 |
| Safari | iOS | Tingting 等 | 必须点播放；IME 候选 |
| Safari | macOS | 系统中文 voice | `default` 全 true 时仍能选 |
| Edge | Android | 空列表 | blocked |

### 10.3 不做自动化的

真实发音是否像普通话、Xiaoxiao vs Tingting 音质、14 秒 bug、简繁朗读是否「好听」。

---

## 11. 未知项

- 某 OEM Android 是否把 `voice.lang` 设成 `cmn-CN`：**unknown**。矩阵记录；若出现再开 `cmn` 别名，不在 V1 猜测。
- 用户中文词库有多少能满足「唯一子串 + 非单字真子串」：**unknown**，落地后算入池率。
- Chrome 409717085 之后 Google voice 14 秒切断是否仍在：**unknown**，同日语。

---

## 12. 结论

中文不能用法语 `\w` 挖空，也不能把日语「邻接非 CJK」弱边界原样搬过来。最小正确集是：**(1) 按 `zh` 前缀发现 voice，默认排序 `zh-CN`；(2) 无空格唯一子串挖空，并拒绝长度为 1 的 Han 真子串；(3) NFKC 级字形匹配，拼音和简繁都不算对。** 产品语言已是 `zh`，不需要 migration，也不需要本轮做简繁选择。`ja`/`fr` 必须原样保留。
