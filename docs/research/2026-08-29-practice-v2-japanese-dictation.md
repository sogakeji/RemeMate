# Practice V2：日语优先听写与多语言扩展调研

> 研究日期：2026-08-29。只读仓库现状与官方/一手来源。本文不含实现，不 commit。
> 仓库 HEAD：`fc4a19f`。`.reme/handoff.md` 锚点仍为 `2b737d4`（Practice 法语 MVP 上线后优化）；以 Git HEAD 为准。
> 产品入口：[docs/BACKLOG.md](../BACKLOG.md) P0「语音质量与选择」「多语言扩展」；当前 Practice 仍严格限定法语。

外部事实只引用规范、浏览器引擎源码、Unicode、官方文档和可核验的开源仓库。观测性语音清单（Readium）单独标明，不是 W3C 契约。

## 1. 仓库现状（只读）

当前法语语境听写已上线，语言门闩写死在 service，客户端 TTS 无 voice 选择、无语速、无持久化。

### 1.1 语言门闩

`get_eligible_items` / `get_start_state` / `start_session` / `record_voice_unavailable` 均在 `language_code != "fr"` 时返回空或不创建会话。[app/services/practice.py](../../app/services/practice.py)

模板对非法语只展示「暂未开放」文案，不渲染开始按钮。[app/templates/practice/start.html](../../app/templates/practice/start.html)

产品语言表已含 `ja`（AI / 阅读 / 词表），阅读模块支持 `zh/en/ja/fr`。[app/services/languages.py](../../app/services/languages.py)

### 1.2 题目入池与挖空

入池条件：例句 `definition.example` 经 NFC + `casefold` 后，目标词用 `(?<!\w)…(?!\w)` 恰好出现一次。[app/services/practice.py](../../app/services/practice.py) `_contains_exactly_once`

挖空 `prompt_parts` 同样用该 Unicode `\w` 边界，且 `re.IGNORECASE`。[app/services/practice.py](../../app/services/practice.py)

Python 3 默认 Unicode 模式下，`\w` 匹配 `str.isalnum()` 为真的字符以及 `_`。平假名、片假名、汉字均属字母类，因此是 `\w`。[Python `re` 文档 `\w`](https://docs.python.org/3/library/re.html)

**对日语的直接后果：** 无空格的「今日は学校に行きます」中，`学校` 前后都是 `\w`，当前边界**不会**命中。法语词边界策略不能原样搬到日语。

### 1.3 答案判定

`normalize_answer`：NFC → 空白折叠为单空格 → `strip` → `casefold`，再与目标做全等。[app/services/practice.py](../../app/services/practice.py)

`casefold` 对假名/汉字几乎无作用。NFC **不会**把半角片假名折成全角。半角 `ｶ`（U+FF76）与全角 `カ`（U+30AB）在 NFC 下仍不相等；NFKC 才会折合。[UAX #15 Table 8](https://www.unicode.org/reports/tr15/)

词身份 `normalize_word_identity` 只用 `strip().lower()`，不做 NFC。[app/services/words.py](../../app/services/words.py)

### 1.4 客户端 TTS

[app/static/practice.js](../../app/static/practice.js)：

- `synth.getVoices()` 过滤 `/^fr([-_]|$)/i`
- 取 `voices[0]`，`utterance.lang = voices[0].lang || "fr-FR"`
- 监听 `voiceschanged`，另有 900ms 超时
- 不设 `rate` / `pitch`，不记住 `voiceURI`
- 播放前 `synth.cancel()` 再 `speak`
- 题目页 `lang="fr"` 写死在模板 [app/templates/practice/question.html](../../app/templates/practice/question.html)

无 voice 时：开始按钮禁用，POST `/practice/voice-unavailable` 记 blocked 会话（1 天幂等）。

### 1.5 测试现状

- 集成测试覆盖法语会话、voice 门闩、RLS、答题顺序。[tests/integration/test_practice.py](../../tests/integration/test_practice.py)
- 单元测试几乎只有 `prompt_parts` 对德语 `ß` 的 NFC 回归。[tests/unit/test_practice.py](../../tests/unit/test_practice.py)
- **没有**日语挖空、答案归一、voice 选择的纯函数测试。

### 1.6 阅读模块已有的日语能力（Practice 未复用）

- 日语句界：`。！？，；`。[app/services/reading/context.py](../../app/services/reading/context.py)
- CJK 相邻字之间的空格折叠。[app/services/reading/dictionary.py](../../app/services/reading/dictionary.py)、[app/services/reading/parsers.py](../../app/services/reading/parsers.py)
- 日语读音：可选 `pykakasi`（GPL-3.0，见第 6 节）。[app/services/reading/dictionary.py](../../app/services/reading/dictionary.py) `_kana`
- 已批准、**尚未作为 Practice 依赖**的日语分词：`fugashi` MIT + `unidic-lite` MIT。[docs/THIRD_PARTY.md](../THIRD_PARTY.md)
- 日语词典数据：JMdict CC BY-SA 4.0，外置，不进 git。[docs/THIRD_PARTY.md](../THIRD_PARTY.md)

Lute 风格阅读规格明确：日语分词不手写规则，优先 fugashi + unidic-lite。[docs/superpowers/specs/2026-07-03-lute-reading-mvp-design.md](../superpowers/specs/2026-07-03-lute-reading-mvp-design.md)

---

## 2. Web Speech API `speechSynthesis`（官方契约）

规范：[Web Speech API Draft Community Group Report, 2026-08-10](https://webaudio.github.io/web-speech-api/) · 源：[WebAudio/web-speech-api `index.bs`](https://github.com/WebAudio/web-speech-api/blob/main/index.bs) · WPT：[web-platform-tests/wpt `speech-api/`](https://github.com/web-platform-tests/wpt/tree/master/speech-api)

### 2.1 `getVoices` 与 `voiceschanged`

- `getVoices()` 返回当前可用 `SpeechSynthesisVoice` 列表；**哪些 voice 可用由 UA 决定**。
- 若尚无 voice，或列表尚未可知（例如服务端合成异步确定），**必须返回长度为 0 的列表**。
- `voiceschanged`：当 `getVoices()` 将返回的列表内容变化时触发。例子包括服务端列表异步到达，或本机 voice 安装/卸载。

MDN 与规范一致，并给出「先调用 `getVoices()`，若 `onvoiceschanged !== undefined` 再订阅」的示例。[MDN `getVoices()`](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/getVoices) · [MDN `voiceschanged`](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/voiceschanged_event)

当前 Practice 的 `voiceschanged` + 900ms 超时符合规范允许的空列表窗口；超时时长是项目策略，不是规范要求。

### 2.2 `voice` / `lang` / `voiceURI`

`SpeechSynthesisVoice` 只读字段：`voiceURI`、`name`、`lang`、`localService`、`default`。[规范 IDL](https://webaudio.github.io/web-speech-api/#tts-section)

- `utterance.lang`：BCP 47 标签。未设时默认文档根语言。[规范 utterance `lang`](https://webaudio.github.io/web-speech-api/#utterance-attributes) · [BCP 47 / RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html)
- `utterance.voice`：创建时必须为 `null`。`speak()` 时若已设为 `getVoices()` 返回的某个对象，UA **必须**用该 voice；若 unset/null，用 UA 默认 voice，且默认 voice **应当**支持当前 `lang`。
- `voiceURI`：规范 IDL 给出该属性；MDN 描述为该 voice 的 URI/位置标识。[MDN `SpeechSynthesisVoice.voiceURI`](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/voiceURI)

规范**没有**规定：`voiceURI` 跨浏览器稳定、跨会话稳定、或全局唯一。把 `voiceURI` 当主键是合理工程选择，但不能当成标准保证。

### 2.3 语速 `rate`

相对该 voice 的默认语速。`1` = 引擎/voice 的正常语速；`2` 两倍；`0.5` 一半。**严格禁止** `< 0.1` 或 `> 10`；具体引擎/voice 可进一步收窄（例如实际最快只有 3 倍）。[规范 `rate`](https://webaudio.github.io/web-speech-api/#utterance-attributes) · [MDN `rate`](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/rate)

听写场景常用 0.7–1.0；这是产品选择，不是规范默认。

### 2.4 其它规范事实

- `speak()` 入队；`cancel()` 清空队列并立即停止当前 utterance。
- `text` 可能有长度上限，规范举例 32,767 字符。Practice 单句远低于此。
- 错误码含 `language-unavailable`、`voice-unavailable`、`text-too-long`、`not-allowed`。
- 合成接口**不**要求 Secure Context（识别接口要求）。TTS 无麦克风权限问题。

---

## 3. Chrome / Edge / Safari / Android / iOS 的 ja-JP、zh-CN、zh-TW

规范不枚举 voice。下列为引擎源码、Chromium 缺陷、以及 Readium 对真实设备的观测清单。Readium 是一手观测文档，不是浏览器契约。

### 3.1 语言标签过滤

`lang` 多数实现返回 BCP 47，主语言小写、地区大写（`ja-JP`）。例外：

- Android 上 Samsung/Chrome 用下划线：`en_us` / 同类 `ja_JP`。[Readium WebSpeech 笔记](https://readium.org/speech/docs/WebSpeech.html)
- Firefox Android 出现三字母码如 `eng-US-f000`（同页）

当前法语过滤 `/^fr([-_]|$)/i` 已覆盖连字符与下划线。日语应同样用 `/^ja([-_]|$)/i`，不要只匹配 `ja-JP`。

中文产品码是 `zh`，voice 则是 `zh-CN`、`zh-TW`、`zh-HK`、偶发 `cmn-Hans-CN`。V2 日语切片不需要解决 `zh` 地区选择；扩展中文时必须单独做 locale 偏好。

### 3.2 各平台 ja-JP 观测（Readium `json/ja.json`）

来源：[readium/speech `json/ja.json`](https://github.com/readium/speech/blob/main/json/ja.json)（2026-08 仓库主分支）

| 环境 | 观测到的 ja-JP voice（节选） | 备注 |
| --- | --- | --- |
| Edge 桌面 | `Microsoft Nanami Online (Natural) - Japanese (Japan)`、`Microsoft Keita Online (Natural) - Japanese (Japan)` | 在线 neural，质量标 veryHigh；`pitchControl: false` |
| Chrome 桌面 | `Google 日本語` | 预装；Readium **明确标注 >14 秒 utterance 会触发 bug** |
| Windows 系统 | `Microsoft Ayumi/Haruka/Ichiro - Japanese (Japan)` | 本机；质量低于 Edge Natural |
| macOS / iOS / iPadOS | `Kyoko`、`Otoya`、`O-Ren`；Siri `Hattori`（nativeID `com.apple.ttsbundle.siri_Hattori_ja-JP_premium`） | 名称会按系统语言本地化 |
| Android / ChromeOS | `ja-jp-x-htm-network/local`、`ja-jp-x-jab-*`、`ja-jp-x-jac-*`、`ja-jp-x-jad-*` | `name` 常被本地化成「女性の声1」等，必须用 `lang` + 回退，不能只靠日文名 |

### 3.3 `voiceURI` 持久化：规范意图 vs 实现

Readium 总结（同 [WebSpeech.html](https://readium.org/speech/docs/WebSpeech.html)）：

- **理论上** `voiceURI` 最适合做标识；**实践中**多数浏览器把 `voiceURI` 设成与 `name` 相同，且**不保证唯一**。
- macOS 会**本地化** `name`，同一 voice 在中文系统与英文系统显示不同。
- Firefox 桌面用真正的 URN 作为 `voiceURI`（Firefox 特有）。
- Safari：**所有** voice 的 `default === true`，不能用来挑系统默认。
- Safari：可下载的增强版 voice **不会**出现在 `getVoices()`；装了更高质量变体后，预装项甚至可能从列表消失。
- Edge 桌面：macOS 上初次可能只露出约 18 个 Natural voice，**第一次 `speak()` 之后**列表扩到 250+。
- Chrome Android：返回的是语言/地区列表而非用户已安装的 voice；未下载的语言也会出现；选未安装语言时 Chrome 可能回退到英语。
- Edge Android：`getVoices()` 空列表，Web Speech 不可用。
- iOS 上 Chrome/Edge 均为 WebKit 壳，voice 与 Safari 相同。

**项目侧持久化建议（非规范）：** 存 `{voiceURI, name, lang}` 三元组。解析顺序：精确 `voiceURI` → `name+lang` → `lang` 前缀（`ja` / `ja-JP` / `ja_JP`）→ 列表中第一个匹配项。不要存数组下标（当前 `voices[0]` 不稳定）。

客户端 `localStorage` 足以支撑 V2；不必先做服务端用户设置表。

### 3.4 排序 / 回退

规范无质量排序。可用的工程规则：

1. 用户记住的 voice（上节三元组）
2. `lang` 精确匹配 `ja-JP`（或归一后的 `ja-JP`）
3. `lang` 前缀 `ja`
4. `localService === true` 优先于在线 Google/Edge Natural（离线可用性；Chrome 桌面 Google voice 还踩 14 秒缺陷）
5. 过滤 eSpeak / novelty / Eloquence（macOS 预装低质量包，Readium 建议滤掉）

日语学习听写：可把「女声、非 novelty」作为展示排序，**不要**当成正确性条件。

### 3.5 语速

规范允许 0.1–10，引擎可收窄。Edge Natural 的 Readium 条目写 `pitchControl: false`，但 **rate 仍为 1（可调）**。听写建议 UI 范围 0.7–1.2，步进 0.1，默认 0.9 或 1.0；超出范围 clamp 到规范区间。

### 3.6 Chrome 14 秒切断（Chromium 缺陷，非规范）

长期开放缺陷：使用 **Google 提供的（非 localService）voice** 时，单条 utterance 约 15 秒后静音，`speaking` 仍为 true，直到 `cancel()`。[Chromium 41294170](https://issues.chromium.org/41294170)（2017）· [41491635](https://issues.chromium.org/issues/41491635) · [332002367](https://issues.chromium.org/332002367)

Workaround（社区与后续工程复述）：每隔 ≤14 秒 `pause()`+`resume()`，或把文本切成短句。Practice 单句通常短于 15 秒，**日语短句切片可不做 pause/resume**；若以后朗读整段课文，必须处理。Readium 因此把 Chrome 桌面 Google voice 排在 Microsoft/Apple 之后。

2025-04 Chromium [409717085](https://issues.chromium.org/issues/409717085) 修过 Google voice 的 `onend`/`onstart` 不触发（MV3 service worker）；**14 秒切断是否随该修复消失：unknown**，实现时仍应按「Google 在线 voice 可能中途停」来测。

### 3.7 iOS / WebKit 用户手势

WebKit iOS：若文档 `requiresUserGestureForAudioPlayback()`，则设置 `RequireUserGestureForSpeechStart`；`speak()` 时若不在用户手势中则 **直接 return，无事件、无 error**。[WebKit `SpeechSynthesis.cpp`](https://github.com/WebKit/WebKit/blob/main/Source/WebCore/Modules/speech/SpeechSynthesis.cpp)

当前 Practice 只在播放按钮 `click` 里 `speak()`，符合该限制。不要在 `voiceschanged`、定时器、页面加载时自动朗读。`setTimeout` 会打断手势链。

Safari 桌面通常同步返回 voice 列表；Chrome/Edge/Firefox 桌面常异步。代码必须同时支持「首次 `getVoices()` 已有数据」和「空列表 + `voiceschanged`」。

### 3.8 zh-CN / zh-TW（后排，仅记账）

与日语同一套发现/持久化/回退即可，但：

- 产品 `zh` 对应至少 `zh-CN` 与 `zh-TW` 两套 voice，默认选哪套是产品问题。
- 简繁本身是文字系统问题，不是 TTS locale 问题；二者不要绑死。
- 最小中文切片应在日语稳定后再开。

---

## 4. 日语听写答案判定（文字系统）

听写判定的是**用户输入字符串与词库目标字符串**，不是语音识别。下列每一项都要在归一化层明确「折合 / 不折合」。

### 4.1 Unicode 正规化

[UAX #15 Unicode 17.0](https://www.unicode.org/reports/tr15/)：

| 形式 | 作用 | 对日语听写 |
| --- | --- | --- |
| NFC | 规范分解再组合。W3C 建议 Web 内容用 NFC。 | 当前 Practice 已用。半角假名**不变**。 |
| NFD | 规范分解 | 听写无额外收益。 |
| NFKC | 兼容分解再组合 | **半角片假名 → 全角**；UAX #15 原文：「halfwidth and fullwidth katakana characters will normalize to the same strings」。Table 8：`hw_ka + hw_ten` 与 `ka + ten` 在 NFKC 下都变成 `ga`。 |
| NFKD | 兼容分解 | 与 NFKC 同类，但不重组。 |

UAX #15 同时警告：NFKC/NFKD **不要盲目用于任意文本**，会抹掉排版区别。听写匹配属于「识别核心意义」的场景，对用户输入做 NFKC 是恰当的；**入库展示字符串保持 NFC/原文**。

当前 `casefold` 对日语几乎无操作。不要用 `lower()` 当假名转换。

### 4.2 平假名 / 片假名

Unicode 将二者编码为不同字母，读音对应。[Unicode 17.0 Chapter 18 East Asia](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-18/) §18.4：片假名音节与对应平假名**语音等价**，但代码点不同。NFC/NFKC **都不**把 `あ` 变成 `ア`。

听写产品选择：

- **必须（V2 最小切片）：** 用户必须打出与词条**同一套文字**。词条是 `学校` 则只接受 `学校`（加 NFKC/空白/标点折叠后）。
- **建议（随后）：** 若词条是假名，平/片假名互认（`がっこう` ≡ `ガッコウ`）。这是可测的一对一映射，不必分词器。
- **后排：** 汉字词条接受读音假名（`学校` 接受 `がっこう`）。这需要词典读音或分词+读音，错误接受同音异字的风险高。

不要把「语音上相同」直接当成「判定正确」。听写同时在练文字系统。

### 4.3 汉字与读音

汉字是语素文字，一形多音（`行` → いく / おこなう / ぎょう）。TTS 读的是整句，用户可能按听到的假名输入。

V2 最小切片：**不**把读音当正确答案。错答反馈已展示完整例句与目标词，用户可对照学习。若以后接受读音，必须：

- 读音来自词条/词典字段，而不是对任意汉字做启发式；
- 明确同音异字策略（建议：读音正确但汉字错误 → 仍判错，或单独「读音对、字形错」状态；不要 silently 判对）。

阅读模块已有 `pykakasi` 读音，但许可证是 GPL-3.0（第 6 节），Practice 判定路径**不要**新引入它。

### 4.4 长音

- 长音符号：U+30FC `ー` KATAKANA-HIRAGANA PROLONGED SOUND MARK；半角 U+FF70 `ｰ`。NFKC 将 U+FF70 → U+30FC。[Unicode 名称](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-18/) · [UAX #15 半角示例](https://www.unicode.org/reports/tr15/)
- 汉字「一」U+4E00、ASCII `-` U+002D、全角 `－` U+FF0D、波浪 `〜` U+301C **不是**长音符号。NFKC 不会把它们折成 `ー`。
- 日语正词法：和语长音多用元音字（`おお` / `とう`），外来语多用 `ー`。`コーヒー` ≠ `こーひー` ≠ `こうひい`。

**最小切片：不把 `ー` 展开成前一拍元音，也不把 `おう`/`おお` 互认。** 只做半角 `ｰ` → 全角 `ー`（随 NFKC）。

ICU `Hira-Kana` 转写会把 `ー` 展开成前一假名的元音，且是**单向、信息损失**的。[ICU `Hira_Kana.txt` 注释](https://sources.debian.org/src/qtwebengine-opensource-src/5.11.3%2Bdfsg-2%2Bdeb10u1/src/3rdparty/chromium/third_party/icu/source/data/translit/Hira_Kana.txt) 明确写：prolonged sound mark doubling is one-way。不要在 V2 默默使用该转写做判定。

### 4.5 促音

`っ` U+3063 / `ッ` U+30C3（小つ）与 `つ`/`ツ` 是不同字符。Unicode 小仮名是独立字母，不是样式变体。[Unicode §18.4 Small Kana](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-18/)

**不要**把促音折成大つ。`がっこう` ≠ `がつこう`。这是听写要练的点。

### 4.6 小假名（拗音）

`ゃゅょぁぃぅぇぉ` 及片假名对应项、`ヵヶ`、以及 Small Kana Extension（U+1B130–U+1B16F）均为独立码位。`きゃ` ≠ `きや`。

**最小切片：保持区别。** 展示层可用 IME 的 `autocorrect="off"`（题目页已关）。

### 4.7 全角 / 半角

NFKC 处理：

- 半角片假名 U+FF61–U+FF9F → 全角片假名
- 全角 ASCII（`Ａ` U+FF21 等）→ 半角 ASCII
- 半角长音 U+FF70 → U+30FC

这是日语输入最常见的「看起来一样、码位不同」。**V2 答案侧必须 NFKC。** 例句挖空侧：先 NFC 定位，避免 NFKC 改变字符长度导致偏移错位；半角混排例句视为脏数据，入池前可拒或先 NFKC 再定位（需测偏移）。

### 4.8 空白与标点

日语书面语通常不用词间空格。用户仍可能输入：

- ASCII space、NBSP U+00A0、全角空格 U+3000
- `。．、，・「」『』（）！？`

最小切片建议（判定用，不改展示）：

1. NFKC
2. 去掉 Cf 类不可见字符（阅读模块已有 `_INVISIBLE_RE`）
3. 把所有 `str.isspace()` 字符删除或折叠（日语目标词内部不应依赖空格）
4. 去掉一小段明确的标点集合：`。．、，・.,!！?？「」『』()（）[]【】…―—`
5. 不要去掉 `ー`（长音）或 `っ`

「目标含标点」的短语（少见）应在入池时拒绝，或对目标做同一套剥离后再比。

### 4.9 推荐的日语 `normalize_answer_ja`

与法语函数分离，避免破坏 `ß`/`casefold` 行为。

```
NFKC(value)
→ 删除 Cf / 阅读模块已列的不可见字符
→ 删除空白
→ 删除第 4.8 节标点集合
→ 返回
```

正确：`normalized(answer) == normalized(target)`。
**不加**平片互转、**不加**长音展开、**不加**汉字→假名。

---

## 5. 无空格语境挖空

### 5.1 为什么 `\w` 边界失败

见 §1.2 与 Python `\w` = Unicode 字母数字。日语连续文本里几乎每个字都是 `\w`，`(?<!\w)学校(?!\w)` 无法匹配「は学校に」。

`\b` 同样定义为 `\w`/`\W` 边界，同样失败。[Python `re` `\b`](https://docs.python.org/3/library/re.html)

UAX #29 词边界对 CJK 也不是「语言学词」；不要用它当挖空定位。

### 5.2 定位策略（由严到宽）

| 策略 | 做法 | V2 |
| --- | --- | --- |
| A. 精确子串恰好一次 | NFC 后 `sentence.count(target) == 1`，用第一次出现的起止偏移挖空 | **必须**（日语最小切片） |
| B. 拒绝真子串假阳性 | `日本` 在 `日本人` 中也是子串；可用「目标前后不是假名/汉字」做弱边界，或要求目标长度 ≥ 2 | **建议**（弱边界 + 最短长度） |
| C. 分词对齐 | fugashi/UniDic 切句，token 表面形或 lemma 与目标相等 | **后排**（与阅读分词对齐时再做） |
| D. 用户点选偏移 | 阅读收词已有 `selection_start/end` | Practice 词库目前没有偏移；后排 |

法语继续用 `\w` 边界，**不要**用策略 A 替换法语（会把 `chat` 从 `achat` 里挖出）。按 `language_code` 分支。

### 5.3 同形多次出现

当前法语规则：出现 ≠ 1 则整词不入池。日语短词（`の` `は` `する` `こと`）会极高频重复，入池率会崩。

最小切片建议：

- 目标长度 1 且为助词/符号：不入池（可先用长度 < 2 拒绝，或拒绝仅假名一拍）。
- 仍要求精确子串出现次数 == 1。多次出现 → 跳过该词，与法语一致。这是产品限制，不是 bug。
- **不要**在 V2 猜「哪一次」；没有阅读偏移时猜错会挖错空。

### 5.4 词 vs 短语

`Word.word` 已是用户保存的表面形，可以是词或短语。挖空应对 **整个 `target` 字符串**，不要再切。

短语 `行きたい` 在「行きたいです」中是前缀子串，策略 A 可用。`日本` vs `日本人` 是真子串问题，靠策略 B 或 C。

### 5.5 与阅读模块的关系

阅读用用户划词偏移，不靠自动分词决定「这是哪个词」。Practice 只有 `example` 文本 + `word.word`。V2 不要引入 MeCab 只为挖空；入池率不够时再加 fugashi，且必须走已批准的 MIT 依赖，而不是复制 Lute 的 natto-py 绑定。

---

## 6. 可借鉴的开源实现与许可证

政策延续 [docs/THIRD_PARTY.md](../THIRD_PARTY.md)：闭测/未来商业服务器默认拒绝 AGPL；复制实质代码必须保留版权与许可声明。下列仅作思路参考，**默认不引入其代码**。

| 项目 | 与听写/日语相关的能力 | 许可证 | 对 RemeMate |
| --- | --- | --- | --- |
| [Lute v3](https://github.com/LuteOrg/lute-v3) | 阅读学语言；日语用 MeCab + natto-py + jaconv；无 MeCab 则无法解析日语。[手册](https://luteorg.github.io/lute-manual/install/mecab.html) · [mecab_parser.py](https://github.com/LuteOrg/lute-v3/blob/master/lute/parse/mecab_parser.py) | MIT | 可参考「日语必须有分词器」的产品边界；**不要**把 MeCab 系统依赖塞进 Practice 最小切片。阅读规格已选 fugashi。 |
| [fugashi](https://github.com/polm/fugashi) | Cython MeCab 包装；`Tagger('-Owakati')` 输出空格分词。 | MIT **且** BSD-3-Clause（捆绑 MeCab）[pyproject.toml](https://github.com/polm/fugashi/blob/main/pyproject.toml) | THIRD_PARTY 已批准。用于后排挖空/词边界，不用于 V2 判定。 |
| [unidic-lite](https://github.com/polm/unidic-lite) | 小型 UniDic | MIT | 已批准。 |
| [jamdict](https://github.com/neocl/jamdict) + [JMdict](https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project) | 离线日英词典、读音 | MIT + CC BY-SA 4.0 | 已批准数据。后排「接受读音」时查读音，不要在线 Jisho。 |
| [WanaKana](https://github.com/WaniKani/WanaKana) | `toHiragana` / `toKatakana` / `isKanji`；`toHiragana('オオサカ')` → `おおさか`。[README](https://github.com/WaniKani/WanaKana) | MIT | **建议**作平片互转的算法参考或小依赖（若要做「建议」层假名互认）。纯映射，无分词。 |
| [pykakasi](https://pypi.org/project/pykakasi/) | 汉字→假名/罗马字；宣称处理 NFC。阅读模块已在用。 | **GPL-3.0-or-later**（PyPI / Debian copyright） | **不要**在 Practice 判定路径扩大使用面。THIRD_PARTY 未登记。阅读读音是既有债务，不在本调研范围扩大。 |
| [Yomitan](https://github.com/yomidevs/yomitan) | 划词查词、词典、音频 | **GPL-3.0** [LICENSE](https://github.com/yomidevs/yomitan/blob/master/LICENSE) | 可看交互，**禁止**复制代码。 |
| [Jitendex](https://github.com/Jitendex/Jitendex) | 改进版 JMdict | AGPL-3.0 | 不要引入。JMdict 原文仍是 CC BY-SA。 |
| [readium/speech](https://github.com/readium/speech) | 跨浏览器 voice 质量清单与过滤 | 文档仓库；JSON 为观测数据 | **建议**作 voice 排序/过滤的数据参考，不要当规范。 |
| Anki / 日语插件 | SRS 与听写牌；判定各插件自定 | 主程序 AGPL-3.0 | 不要复制。可借鉴「听写默认严格字形、读音另栏」的产品拆分。 |

**V2 不新增依赖。** 判定用标准库 `unicodedata`；TTS 用现有 Web Speech。平片互转若做，优先 50 行码位映射或 MIT 的 WanaKana 思路，而不是 GPL 的 kakasi。

---

## 7. 可测试性与浏览器避坑

### 7.1 必须可单测的纯函数（pytest，无浏览器）

从 `practice.js` / `practice.py` 拆出：

1. `filter_voices(voices, lang_prefix)` — `ja` 匹配 `ja-JP`、`ja_JP`、`ja`
2. `pick_voice(voices, stored)` — 三元组回退
3. `clamp_rate(x)` — [0.1, 10] 再夹到 UI 范围
4. `normalize_answer_ja` / 仍保留法语 `normalize_answer`
5. `locate_cloze(sentence, target, language_code)` — 法语 `\w` 边界；日语精确子串一次
6. 入池：日语例句无目标 / 出现两次 / `日本`∈`日本人` 的拒绝用例

这些不依赖 TTS，CI 必须绿。

### 7.2 不要在 pytest 里测的

- 真实 `speechSynthesis` 音质、某台机器有无 `Kyoko`
- 14 秒切断（需 Chrome + Google voice）
- iOS 手势策略

用一份**手工兼容矩阵**（第 9 节）在真实浏览器勾选。Headless Chrome 常常 **0 个 voice**，自动化 TTS 易假红。

### 7.3 实现避坑清单

| 坑 | 来源 | 做法 |
| --- | --- | --- |
| 首次 `getVoices()` 为空 | 规范允许；Chrome/Edge 常见 | `voiceschanged` + 超时；超时后仍空则走现有 blocked 路径 |
| 900ms 过短 | 项目现状 | Android 可加到 2–3s，或直到用户点「重试」（已有按钮） |
| `voices[0]` 不稳定 | 当前代码 | 禁止按下标持久化 |
| `voiceURI === name` 且不唯一 | Readium | 三元组 |
| macOS 本地化 name | Readium | 不要只存 name |
| Safari `default` 全 true | Readium | 忽略 `default` |
| Safari 下载 voice 不出现 | Readium | 有 Kyoko 即可开始；不要要求 Enhanced |
| Edge 列表在第一次 speak 后变长 | Readium | `voiceschanged` 持续监听，不只一次 |
| Chrome Android `ja_JP` | Readium | `[-_]` 正则 |
| Chrome Android 列出未安装语言 | Readium | `speak` 失败 / 英语回退时标 voice 不可用 |
| Edge Android 空列表 | Readium | 走 blocked，与无法语 voice 相同 |
| iOS 无手势 `speak` 静默失败 | WebKit 源码 | 只在 click 里 speak |
| Google voice ~15s 切断 | Chromium 41294170 | 短句可忽略；长文本再 pause/resume |
| `lang="fr"` 写死 | 题目模板 | 改为会话 `language_code` 的 BCP 47（`ja` → `ja-JP`） |
| 在线 dictionary API | 阅读模块 `if False` | Practice **不要**为判定去打 Jisho |
| 扩大 pykakasi | GPL-3.0 | Practice 判定不用 |

### 7.4 法语回归

日语分支必须与法语测试并存。`prompt_parts("ß cible", "cible")` 回归保留。[tests/unit/test_practice.py](../../tests/unit/test_practice.py)

---

## 8. 必须做 / 建议做 / 后排

### 必须做（日语最小切片的正确性门槛）

1. 按语言拆 TTS locale：`fr`→`fr` 前缀，`ja`→`ja` 前缀（含 `[-_]`）。
2. 日语挖空**停止使用** `\w` 边界；改为 NFC 后精确子串恰好一次，并保存起止偏移。
3. 日语答案 NFKC + 去空白 + 去明确标点；与目标全等。不接受假名替代汉字。
4. 半角片假名/半角长音随 NFKC 折合。
5. `voiceschanged` + 超时；无 ja voice 时沿用 blocked 会话，不放行无声听写。
6. `speak()` 仅在用户点击播放时调用；`utterance.lang` 用选中 voice 的 `lang` 或 `ja-JP`。
7. 题目 `lang` 属性跟会话语言走，不再写死 `fr`。
8. 纯函数测试：日语挖空正反例、NFKC 半角、促音/小假名/长音**不**误折、法语回归。
9. 不把 `日本` 从 `日本人` 里挖出：入池拒绝「目标是另一 CJK 词的真子串且无边界」（最小可用：拒绝当目标前后仍是 CJK 字母）。
10. 不引入 GPL/AGPL 新依赖；不复制 Yomitan/Anki 代码。

### 建议做（同一切片可附带，失败不阻断入池逻辑）

1. 用户可选 voice 列表（过滤 `ja`），`localStorage` 存 `{voiceURI,name,lang}`，回退链见 §3.3。
2. 语速滑条 0.7–1.2，默认 0.9 或 1.0，同样本地持久化。
3. 展示排序：记住的 voice → 精确 `ja-JP` → `localService` → 其余；过滤明显 novelty（若能用 Readium 名称列表，视为数据而非规范）。
4. 假名词条平/片互认（仅当目标不含汉字）。
5. 目标长度 < 2 的假名不入池，降低 `の`/`は` 碰撞。
6. 把 voice 过滤/选择做成无 DOM 的 JS 纯函数，便于 node 或快照测试。
7. 人工跑第 9 节浏览器矩阵并记录缺 voice 设备。

### 后排（日语切片之后，或明确新计划）

1. 汉字词条接受读音（JMdict / 已批准词典字段；不用 pykakasi 扩大 GPL 面）。
2. `ー` ↔ 元音延长、`おう`/`おお` 互认。
3. fugashi 分词挖空，处理同形多次与复合词。
4. 英语等西文 Practice（`\w` 边界大体可复用法语，另测撇号）。
5. `zh`：`zh-CN` vs `zh-TW` voice；简繁 NFKC 不够（「发/髮」等）。
6. 服务端/云端 TTS；用户设置表同步跨设备。
7. Chrome 长文本 pause/resume；整课朗读。
8. 云端 voice 质量 A/B；自动播放下一句。

---

## 9. 推荐的最小日语切片

目标：**法语行为不变**；当前语言为 `ja` 时，能用浏览器 ja voice 做最多 5 题语境听写，判定字形严格、挖空不靠空格。

范围：

1. Service：`fr` 与 `ja` 允许 Practice；其它语言仍显示未开放。
2. 入池：`ja` 用 §5.2 策略 A + 弱 CJK 边界（必须项 9）；仍要恰好一次。
3. 判定：`normalize_answer_ja`（§4.9）。
4. TTS：§8 必须项 1、5、6 + 建议项 1–2（voice/语速本地记忆）。不做云端 TTS。
5. 无新 Python 依赖。无数据库迁移（voice 偏好在浏览器）。
6. 测试：§7.1 表驱动 + 现有法语集成测试全绿 + 一组 `ja` 集成测试（造词 `学校` / 例句 `今日は学校に行きます。` / 答案 `学校` 与半角混排）。

明确不做：读音判对、分词器、中文、英语、自动播放、服务端记 voice。

---

## 10. 测试矩阵

### 10.1 pytest（每次切片必跑）

| ID | 输入 | 期望 |
| --- | --- | --- |
| J-CLOZE-1 | 句 `今日は学校に行きます。` 目标 `学校` | 挖空左右为 `今日は` / `に行きます。` |
| J-CLOZE-2 | 同上，目标 `校` | 拒绝入池（真子串，前后为 CJK） |
| J-CLOZE-3 | 句中 `学校` 出现两次 | 拒绝入池 |
| J-CLOZE-4 | 法语 `Je voudrais un café.` / `voudrais` | 行为与现网一致 |
| J-ANS-1 | 目标 `学校`，答案 `学校` | 正确 |
| J-ANS-2 | 目标 `学校`，答案 `がっこう` | 错误 |
| J-ANS-3 | 目标 `コーヒー`，答案半角 `ｺｰﾋｰ` | 正确（NFKC） |
| J-ANS-4 | 目标 `がっこう`，答案 `がつこう` | 错误（促音） |
| J-ANS-5 | 目标 `きゃ`，答案 `きや` | 错误（小假名） |
| J-ANS-6 | 目标 `コーヒー`，答案 `こうひい` | 错误（长音不展开） |
| J-ANS-7 | 目标 `ゲーム`，答案 `げーむ` | V2 错误；若启用建议层平片互认则为正确 |
| J-ANS-8 | 答案仅空白/标点 | EmptyAnswerError |
| J-VOICE-1 | lang `ja-JP`、`ja_JP`、`ja` | 均匹配 ja 过滤器 |
| J-VOICE-2 | stored URI 缺失，存在 `ja-JP` | 回退到第一条 ja |
| FR-REG | `ß cible` / `cible` | 现有单元测试仍过 |

### 10.2 手工浏览器（建议做；实现后勾选）

| 浏览器 | OS | 期望 ja voice | 必测 |
| --- | --- | --- | --- |
| Chrome | Windows | `Google 日本語` 及/或 Haruka | 发现、播放、选 voice、语速、无 voice 时 blocked |
| Edge | Windows | Nanami / Keita Natural | 同上；Natural 需联网 |
| Chrome | Android | `ja-JP` 或 `ja_JP` 列表 | 下划线 lang；未下载日语包时的回退 |
| Safari | iOS | Kyoko / Otoya | **必须**点播放才出声；不要自动朗读 |
| Safari | macOS | Kyoko 等 | `getVoices` 同步；`default` 全 true 时仍能选 |
| Chrome | macOS | Google 日本語 + 系统日语 | URI 持久化跨刷新 |
| Edge | Android | 空列表 | 走 blocked，不开始会话 |

每台设备记录：`name`、`lang`、`voiceURI`、`localService`。不要把某次机器上的名字写进代码常量，除非作为排序提示列表。

### 10.3 不做自动化的

真实发音是否像日语、Nanami vs Kyoko 音质、14 秒 bug（除非以后朗读长文）。

---

## 11. 未知项

- Chrome 409717085 修复后，Google voice 14 秒切断在当前稳定版是否仍复现：**unknown**，矩阵里用 Google 日本語试一条略长句即可。
- 某 OEM Android 的 ja voice 名称全集：Readium 只覆盖 Pixel 类 vanilla Android。
- Siri 高质量日语 voice 是否经 Web Speech 露出：Readium 记 Hattori nativeID，但整体称 Siri 最高质量往往**不**经 Web Speech。[Readium WebSpeech macOS](https://readium.org/speech/docs/WebSpeech.html)
- 用户词库日语例句有多少能满足「精确子串恰好一次 + 非真子串」：**unknown**，切片落地后应用真实词库算入池率，低于可用再开 fugashi。
- `zh` 默认 `zh-CN` 还是跟随 UI/系统 locale：**未定**，不在本切片。

---

## 12. 结论

法语 Practice 的 `\w` 挖空、NFC+`casefold` 判定、`voices[0]` TTS，都不能直接开日语。

日语 V2 最小正确集是三件事：**(1) 按 `ja` 前缀发现并记住 voice；（2) 无空格子串挖空；（3) NFKC 级字形匹配，不把读音当对。** 浏览器差异用回退链和 blocked 会话消化，而不是假定 Nanami/Kyoko 一定存在。分词、读音判对、中文 locale、云端 TTS 全部后排。
