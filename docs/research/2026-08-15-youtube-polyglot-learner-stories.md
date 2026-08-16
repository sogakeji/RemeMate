# YouTube 普通人多语言学习故事调研

> 研究日期：2026-08-15。只做研究，不改代码、不部署、不提交。
> 目标：为公开 SEO 文章找可核验的普通人学习故事，而不是语言教师或机构的授课内容。

## 方法与边界

### 收录标准

- 发布者在视频或频道简介中把自己写成自学者、学生、上班族、旅行者、移民/旅居者或生活向创作者。
- 视频是个人经历（journey / vlog / “how I learned”），不是课程广告或机构招生片。
- 至少能用 YouTube 一手来源核验：视频页、频道 About、视频描述/章节。部分条目另有字幕转写。

### 排除标准

排除教授、语言学家、语言教师、培训机构，以及以专家授课为主的频道。检索中反复出现、本次**不收录**的例子：

| 排除对象 | 原因 | 核验来源 |
| --- | --- | --- |
| Olly Richards / StoryLearning | 自称教过数万学生，并卖语言课程 | [How to Learn a Language from Zero in 2026](https://www.youtube.com/watch?v=YgVrAb7_8OU) 字幕片段：teaching tens of thousands of students |
| Steve Kaufmann / LingQ | 语言学习公司联合创始人，专业教学向 | [频道](https://www.youtube.com/channel/UCez-2shYlHQY3LfILBuDYqQ) |
| GO! Billy Korean、Canguro English、Learn English with Bob the Canadian | 以授课为主 | 频道名与视频定位 |
| Victor Talking Academy、Ling Learn Languages、90 Day Korean | 培训机构或付费辅导 | 视频描述中的 mentorship / academy |
| Lýdia Machová TEDx | 职业语言导师 | [TED](https://www.youtube.com/watch?v=o_XVt5rdpFY) |
| Veronika's Language Diaries | 频道现卖 Language Mastery Program，已偏教练 | [视频描述](https://www.youtube.com/watch?v=fNmaKxUvvi8) |

### 来源层级

1. **一手**：YouTube oEmbed、YouTube Innertube `player` / `browse` 返回的标题、作者、描述、章节、频道 About。
2. **一手转写**：公开字幕转写站上的完整或长摘录，仅在能打开原文时使用。
3. **搜索引擎索引的 YouTube 字幕片段**：只当补充，并标明“索引字幕，未独立下载完整字幕”。
4. **二手访谈/播客**：只用来核对身份，不单独当作方法证据。

无法从上述来源核验的内容标为 **未核验**，不编造。

### 技术限制

- 本机没有 `yt-dlp`。YouTube 网页对未登录抓取常返回 401；`timedtext` 无签名无法拉字幕。
- 描述、章节、频道 About 通过 YouTube 官方 Innertube 取得，可作为一手。
- 多数视频的**完整口播字幕未能直接下载**。方法栏只写描述/章节/已读转写里明确出现的内容。

---

## 一览

| # | 视频 | 频道 | 普通人类型 | 一手核验 |
| --- | --- | --- | --- | --- |
| 1 | [Chinese polyglot speaking in 7 languages](https://www.youtube.com/watch?v=MWj8pxhxrv0) | Zoe.languages | 社会学博士生 / 成人自学者 | oEmbed + player 描述 + 频道 About |
| 2 | [How do I study languages on a busy day?](https://www.youtube.com/watch?v=y4VrWc0PM3M) | Zoe.languages | 同上，忙碌日学习 vlog | player 描述 |
| 3 | [How to study languages consistently with a full-time job](https://www.youtube.com/watch?v=AF21PyR9ohU) | Zoe.languages | 同上，把学习嵌进忙日程 | player 描述 |
| 4 | [How I Learned English from Zero to FLUENT](https://www.youtube.com/watch?v=dYikKyL4lIA) | a-tekt | 赴日建筑硕士生 / 自学者 | oEmbed + player + 频道 About |
| 5 | [How I Study Korean (with a full time job)](https://www.youtube.com/watch?v=HJDttYLrbB4) | delancey days | 注册营养师 / 上班族 | oEmbed + player + 频道 About |
| 6 | [How I Learned Fluent Mandarin Chinese \| 100% Self taught](https://www.youtube.com/watch?v=wVNEXPuKJrE) | smolbiskit | 自学创作者 | oEmbed + player + 频道 About |
| 7 | [How I Learned Fluent Mandarin Chinese \| Through TV Shows](https://www.youtube.com/watch?v=OkKTgm9XxEg) | smolbiskit | 同上 | player 描述 |
| 8 | [how I learned English by myself in a lazy way](https://www.youtube.com/watch?v=HGQLckoU_3I) | baobaopearly | 台湾创作者 / 自学者 | oEmbed + player + 频道 About |
| 9 | [Taiwanese Polyglot Speaking in 6 Languages](https://www.youtube.com/watch?v=DS0OSbjFedo) | baobaopearly | 同上 | player 描述 |
| 10 | [How I learned English by myself for free without studying](https://www.youtube.com/watch?v=NQlFIrSZiIE) | Ruri Ohama | 拍摄时为医学生；后来卖过语言课 | oEmbed + player；身份见播客 |
| 11 | [how I LEARNED A LANGUAGE by myself WITHOUT STUDYING it](https://www.youtube.com/watch?v=7YX7PAdo4B0) | Ruri Ohama | 同上的方法更新版 | player + 完整字幕转写 |
| 12 | [How I Learned English by Watching YouTube](https://www.youtube.com/watch?v=oMx5oZQlkt4) | Wannaspeak by Veroniq | 波兰全职旅行者；后来做英语陪练 | oEmbed + player + 频道 About |
| 13 | [How I Learned Languages - Spanish, ASL, Korean, Chinese](https://www.youtube.com/watch?v=FB_6Kx2OiD4) | kate reads | 读书博主 / 英语专业学生 | oEmbed + player + 频道 About |
| 14 | [How I Learn Any Language in 24 Hours](https://www.youtube.com/watch?v=r3wiEHX8QdU) | Xiaomanyc 小马在纽约 | 街头采访创作者；18 岁前只会英语 | oEmbed + player + 频道 About |
| 15 | [How To Start Learning Japanese For Beginners](https://www.youtube.com/watch?v=kHwY4PV-YFU) | Maddie's Days | 加拿大旅日生活博主 | oEmbed + player + 频道 About |
| 16 | [How I Learned Japanese in One Year](https://www.youtube.com/watch?v=PgSER61GiYU) | K.D.Wilson | 移居日本的美国人 | oEmbed + player 描述 |
| 17 | [How I passed German B1 from A1 in 6 months (With a full time job)](https://www.youtube.com/watch?v=bN0CVTsVyMg) | Charlene Cong, CFA | 香港到瑞士的金融从业者 / 移民 | player 描述 + 频道 About + 索引字幕 |
| 18 | [How I Learn Multiple Languages While Working a 9-5](https://www.youtube.com/watch?v=EvPPn_76NN0) | Mattheos Drivas | 上班族；后来在做语言 App | player 描述 + 频道 About |
| 19 | [How I Learned 6 Languages by 21](https://www.youtube.com/watch?v=GSb82LcT0ek) | Mattheos Drivas | 同上，分语种自述 | player 描述 |
| 20 | [How I'd Learn a Language From Scratch in 2026](https://www.youtube.com/watch?v=DeytEWM_nI4) | Mattheos Drivas | 同上，五步法 | player 描述 |
| 21 | [how to learn languages when you have work or school?](https://www.youtube.com/watch?v=qR6fOm1IlkQ) | İclal | 19 岁学生（米兰 / 伊斯坦布尔） | player 描述 + 频道 About |
| 22 | [How to learn any languages from TV shows](https://www.youtube.com/watch?v=rcYXV9Fy9Xk) | Nate - のと | 日语母语自学者（英语 / 台语） | player 描述 + 频道 About |
| 23 | [How I Study 3 Languages at Once](https://www.youtube.com/watch?v=lRGT4AHahhs) | Aneli | 生活向创作者，同时学法/韩/日 | player 描述 + 频道 About |

以上 23 条视频、16 个频道，均用 YouTube oEmbed 或 Innertube `player` 核验过标题与作者，不是搜索摘要里的死链。

---

## 逐条记录

### 1–3. Zoe.languages（社会学博士生）

**代表视频**

- 标题：Chinese polyglot speaking in 7 languages (subtitles)
- 频道：[Zoe.languages](https://www.youtube.com/@zoe.languages)
- URL：<https://www.youtube.com/watch?v=MWj8pxhxrv0>
- 发布：2021-11-01；约 206 万次观看（Innertube `player`，2026-08-15 读取）
- 相关：
  - [How do I study languages on a busy day?](https://www.youtube.com/watch?v=y4VrWc0PM3M)（2021-12-07，约 24 万次）
  - [How to study languages consistently with a full-time job: the tiny habits method](https://www.youtube.com/watch?v=AF21PyR9ohU)（2022-06-15，约 17 万次）

**背景，以及为何算普通人**

频道 About 原文：*I'm Zoe, a language learner, sociologist, and creator who has learned 7 languages as an adult.* 语言列表标为中、法、德、黎巴嫩阿拉伯语、意、土、波斯、英。首支视频描述写这是她的第一条 YouTube 视频，并说自己仍在学、各语水平不同，能对话即算“会说”。忙碌日 vlog 描述写白天要工作，用洗碗、做饭、走路等空隙学。tiny habits 视频描述还链到 *A day in the life of a polyglot PhD student in sociology*。

她不是语言学教授或语言学校教师，主业是社会学研究者/学生。后来 Instagram 简介出现 *Founder of @thelanguagemind*，频道也提供免费指南下载——这是**后期产品化**，不改变 2021–2022 这些视频里的学生身份。是否收费授课：**未在本次 YouTube About 中核验**。

**视频里明确出现的方法**（只记一手文字）

来自首支视频描述：

- 用 7 种语言讲自己的学习故事；自称至少中级、能对话才算“会说”。
- 章节：中文、法语、阿拉伯语、土耳其语、波斯语、德语。各语具体怎么学，**完整口播未下载，标未核验**。

来自忙碌日 vlog 描述（作者自写）：

- 用“夹缝时间”（washing, cooking, walking）学习。
- 当天安排：早上 3 小时阿拉伯语，晚上 2 小时土耳其语。
- 有时早上 2 小时阿语 + 1 小时德语，晚上 1 小时土语 + 1 小时波斯语。
- 时间按精力灵活调整。

来自 tiny habits 视频描述：

- 明确基于 BJ Fogg《Tiny Habits》和 James Clear《Atomic Habits》。
- 章节：没时间还能不能学；Fogg 行为模型；Ability；Prompt。

搜索引擎索引的该频道字幕（[take notes 视频](https://www.youtube.com/watch?v=h3PQM_WS5eA)）出现过 *I'm Zoe, a PhD student in sociology in France and now in Germany who speak seven languages*。这是索引字幕，不是本次下载的完整稿。

**可转成 SEO 文章的主题**

- 读博/上班时怎么把语言嵌进夹缝时间
- “会说一门语言”的普通人标准：能对话，而不是门门母语
- 小习惯（prompt + 降低难度）比大计划更可持续
- 同时维持多语时按精力轮换，而不是平均分配

---

### 4. a-tekt（赴日建筑学生）

**视频**

- 标题：How I Learned English from Zero to FLUENT
- 频道：[a-tekt](https://www.youtube.com/@a-tekt)
- URL：<https://www.youtube.com/watch?v=dYikKyL4lIA>
- 发布：2024-12-01；约 1.1 万次观看；1.59K 订阅（视频页）

**背景**

频道 About：*Hi :) I’m passionate about design, creativity and growth. As a curious learner…* 关键词含 `masters degree`、`architecture`、`Japan`、`living abroad`。视频描述写从零英语到能出国留学，标签 `#selftaught`。这是设计/建筑学生的自学故事，不是语言教师。

职业履历细节（学校名、是否全职工作）：**未核验**。

**明确提到的方法**（描述与章节）

- 章节：Grammar Books；Building Vocabulary；Immersion。
- 描述强调自学、没有昂贵课程或家教——此句来自搜索引擎索引字幕（*most of it was selftaught I didn't have expensive courses or tutors*），完整字幕未下载。
- 描述含 italki 联盟链接。她是否真用过 italki：**描述未写“我用了”，只放了链接，标未核验**。

**SEO 主题**

- 为留学而自学英语：语法书、词汇、沉浸各管什么
- 小频道普通人的零到流利，而不是网红速成
- 词表之后必须有 immersion，否则无法开口

---

### 5. delancey days（注册营养师，朝九晚五）

**视频**

- 标题：How I Study Korean (with a full time job) 🇰🇷 Language Learning Vlog
- 频道：[delancey days](https://www.youtube.com/@delanceydays)
- URL：<https://www.youtube.com/watch?v=HJDttYLrbB4>
- 发布：2025-05-05；约 6600 次观看

**背景**

频道 About：*My name's Delancey. I make slice of life content about my language learning journey (Korean + Mandarin) and my experience building a cozy home with my Chinese boyfriend.* 标签含 `#dietitianlife`、`#registereddietitian`。视频标题和描述写 busy 9-5 job。她是上班的注册营养师，在学韩语和普通话，不是韩语老师。

**明确提到的方法**（描述与章节）

- 挑战：工作周每天至少学韩语 30 分钟。
- 工具：Anki；Talk To Me in Korean vlog 播放列表；Pinterest 词汇板；DiDi's Korean Culture Podcast。
- 流程章节：目标 → 学习工具 → 家教准备 → 家教课与复盘 → 通勤学 → 词汇 → TTMIK → 语法 → 口语。
- 标签含 `#italkiteacher`，说明她有家教课；家教平台是否就是 italki：**未在描述正文写死**。

**SEO 主题**

- 全职工作每天 30 分钟韩语：真实一周，而不是理想作息
- Anki + 语法课 + 家教，上班族怎么拆任务
- 营养师/普通上班族学韩语，不是语言专业学生

---

### 6–7. smolbiskit / Emi（自学普通话创作者）

**视频**

- 标题：How I Learned Fluent Mandarin Chinese | 100% Self taught 🇨🇳
- 频道：[smolbiskit](https://www.youtube.com/@smolbiskit)
- URL：<https://www.youtube.com/watch?v=wVNEXPuKJrE>
- 发布：2025-11-20；约 14.6 万次观看
- 相关：[How I Learned Fluent Mandarin Chinese | Through TV Shows](https://www.youtube.com/watch?v=OkKTgm9XxEg)（2025-12-14）

**背景**

频道 About：*Hey guys! I’m smolbiskit also known as Emi, I do language related videos :)* 分类是 Entertainment，不是教学机构。描述只放社交账号和资源链接，没有教师资质或学校。适合记为自学创作者。是否另有全职工作：**未核验**。

**明确提到的方法**

- 标题自称 100% self taught。
- 描述列出：Chinese tones 的 TikTok；YouTuber Kelly Yang；Chinative Playlist；播客 *Learning Chinese Through Stories*；播客《旅歐三小事》。
- 姊妹视频标题写明 *Through TV Shows*，并链到 WayV *Dream Plan* 综艺播放列表。
- 搜索引擎索引字幕（同条视频）：*The first thing I did was learn Chinese tones...*。完整字幕未下载。
- 描述有 FluentU 联盟链接。她是否把 FluentU 当作主方法：**描述未陈述，标未核验**。

**SEO 主题**

- 先声调，再剧/综艺：自学普通话的顺序
- 用目标语播客和综艺当输入，而不是只背词表
- “100% 自学”到底用了哪些免费公开资源

---

### 8–9. baobaopearly / Pearly Wong（台湾创作者）

**视频**

- 标题：how I learned English by myself in a lazy way without studying (advice from a polyglot)
- 频道：[baobaopearly](https://www.youtube.com/@pearlywong)（显示名 baobaopearly）
- URL：<https://www.youtube.com/watch?v=HGQLckoU_3I>
- 发布：2023-05-24；约 94 万次观看
- 相关：[Taiwanese Polyglot Speaking in 6 Languages: my language learning journey](https://www.youtube.com/watch?v=DS0OSbjFedo)（2023-05-31；章节：日语、客家话、法语、普通话、英语、阿拉伯语）

**背景**

频道 About：*Films for those still figuring it out*。分类 People & Blogs / Education。另一支视频标题自称 Taiwanese Polyglot。2026 年生活更新视频标题/摘要写她长期靠艺术谋生、经济困难（[It's been a while...](https://www.youtube.com/watch?v=NRHHuCtp7wk) 搜索摘要）。她不是语言学校教师。

JForrest English 对她的访谈字幕（二手，仅作身份补充）：英语是第一门外语，后来还有法语、日语、阿拉伯语、西班牙语；约五岁开始被动接触英语。

**明确提到的方法**（英语视频章节，作者自写）

1. a zero-stress start
2. an entertaining method
3. tips on choosing which video to watch
4. involve your emotion
5. 是否查生词（章节：do I look up new words?）
6. best way to improve speaking skill
7. great way to improve your writing skill
8. challenging but very effective method
9. important mindset / my motivation

姊妹视频 [how to learn languages in a LAZY way](https://www.youtube.com/watch?v=uZ0o4rvl6_Q) 章节：very entertaining method；the best method if you are a busy person；weird but effective method；a method that calm your mind。

各步骤的具体做法（看什么、写什么、挑战是什么）：**完整字幕未下载，标未核验**。不要把章节标题脑补成操作手册。

**SEO 主题**

- “懒人学英语”：先降低压力，再用自己爱看的视频
- 台湾普通人的六语故事：日语 / 客家话 / 法语 / 普通话 / 英语 / 阿语
- 查词还是不查词：输入时要不要停下来
- 忙人的“娱乐即输入”，以及它和写作/口语输出怎么配

---

### 10–11. Ruri Ohama（拍摄时为医学生；后来卖过课）

**视频**

- 标题：How I learned English by myself for free without studying
- 频道：[Ruri Ohama](https://www.youtube.com/@ruriohama)
- URL：<https://www.youtube.com/watch?v=NQlFIrSZiIE>
- 发布：2021-02-19；约 276 万次观看
- 相关（有完整字幕转写）：[how I LEARNED A LANGUAGE by myself WITHOUT STUDYING it](https://www.youtube.com/watch?v=7YX7PAdo4B0)（2022-05-24，约 51 万次）

**背景，以及边界**

2021 年这条是她早期爆款。RealLife English 播客介绍她是 *Turkish-Japanese Youtuber, med student, and polyglot*（[BB 22](https://podcasts.apple.com/gb/podcast/bb-22-she-went-from-beginner-to-fluent-in-just-9-months/id600128442?i=1000546240720)）。搜索索引的评论摘要也写 *Judy, a first-year medical student from Turkey*。四语视频 [Polyglot speaking FLUENTLY in 4 languages](https://www.youtube.com/watch?v=UIsCnqTSYUs) 列出日、土、英、德。

**后来变化（必须写明）**：她上线过 Teachable 课程 [How to learn any language](https://ruri-ohama-s-school.teachable.com/p/how-to-learn-any-language-language-learning-masterclass)；当前频道 About 已转向 ADHD / Kaizen 生产力，链到 <https://ruriohama.com>。因此她**不能**再被写成“现在仍是纯粹的普通医学生”。收录的是 2021–2022 的学生/创作者阶段故事，并标明后来卖过语言课。

**2022 更新视频里明确说到的方法**（[pickscribe 转写](https://pickscribe.com/v/7YX7PAdo4B0)，已通读）

- 学校英语课输入太多、输出太少；她没上国际学校。
- 引用川崎洋《输入词典》《输出词典》：她认同后期输入:输出约 3:7；但入门阶段输入更重要。建议至少到 A2 再用这套“不学习”法。
- 目标要具体：她当年只想听懂 James Charles 的视频，不在乎正式语法。
- 步骤（她口播）：
  1. 选自己爱看的内容，优先母语者生活 vlog，或 Netflix / 剧 / 歌。
  2. 常速 + 字幕，每天至少 1 小时，当习惯。
  3. 去字幕再看；每看完用目标语向自己复述，先不查词典；日常自言自语（甚至对着镜子讲化妆步骤）。
  4. 阅读，包括童书；每章再用自己的话总结。
  5. 把视频加速到 1.25–1.5，适应母语者语速。
  6. 坚持一年以上。
- 缺点：自学难以得到可靠反馈，错音会固化；她举了 *foreign / purpose* 的错读，是观众纠正的。她因此推荐 italki 找母语者（该段是赞助，但她同时说自己当年不知道有这类平台）。

2021 原视频的描述现已被 ADHD 产品链接覆盖，**原描述里的方法列表已不可见**。

**SEO 主题**

- 学校英语为何“学了不会说”：输入过多、输出过少
- 用 YouTube 生活 vlog 当教材：从带字幕到去字幕到自言自语
- 先定一个很小的目标（看懂某个创作者），而不是“学好英语”
- 自学最大的坑：没有人纠正发音
- 写作时必须加注：讲述者后来卖过课，故事仍可用，不要写成“隐藏的语言老师”

---

### 12. Wannaspeak by Veroniq（波兰全职旅行者）

**视频**

- 标题：How I Learned English by Watching YouTube (School Failed Me)
- 频道：[Wannaspeak by Veroniq](https://www.youtube.com/@wannaspeakbyveroniq)
- URL：<https://www.youtube.com/watch?v=oMx5oZQlkt4>
- 发布：2025-07-02；约 2.3 万次观看

**背景**

视频描述：*I'm a full-time traveler, and I used this method while exploring the world.* 频道 About：*Hi, I’m Weronika. I was born and raised in Poland, and I travel full-time as a digital nomad. I learned English and Spanish through real life (moving countries, working, meeting people).* 索引字幕也有 *my name is Veronica. I am from Poland. And I learned English on my own watching...*

**后来变化**：频道 About 现提供 90 天英语陪练（*Transform your speaking confidence in English in 90 days with personalized coaching*）。收录的是她的旅行者自学故事，并标明她后来做陪练。

**明确提到的方法**（视频描述，作者自写）

- 不靠背语法、不做课本练习；靠看 YouTube 上的真实内容和真实对话。
- 自称 7 步，章节为 STEP 1–7（1:16 学校为何没用；2:33 YouTube 为何有效）。
- 描述概括：选自己喜欢的内容；选择想要的口音；主动听；更自然地开口，不过度想语法。
- 7 步的逐条操作：**描述未展开，完整字幕未下载，标未核验**。

**SEO 主题**

- “学校教英语失败了”：旅行者改用 YouTube 真实内容
- 把英语变成日常生活的一部分，而不是一门课
- 选口音、主动听、少做语法操练——适合旅行/数字游民

---

### 13. kate reads（读书博主）

**视频**

- 标题：How I Learned Languages - Spanish, ASL, Korean, Chinese
- 频道：[kate reads](https://www.youtube.com/@murakamireads)
- URL：<https://www.youtube.com/watch?v=FB_6Kx2OiD4>
- 发布：2019-05-23；约 1600 次观看

**背景**

频道关键词：booktube、romance、fantasy、classics、`english degree`、writer。这是读书/文学频道上的一条个人语言经历，不是语言教学频道。英语专业不等于语言教师；她讲的是自己学西班牙语、手语、韩语、中文的经过。

**明确提到的方法**（描述）

- *This is how I PERSONALLY learned languages and my tips on how to learn!*
- 用过 Duolingo，但声明那是很久以前，若产品已变她不知情。
- 后来改用 ChineseSkill，没有再回去。
- 西语 / ASL / 韩语各自怎么学：**完整字幕未下载，标未核验**。

**SEO 主题**

- 读书人怎么旁路学四门语言：App 只是其中一段
- Duolingo 用腻之后换专项 App（ChineseSkill）
- 小频道、非语言网红的真实路径，适合写“普通人而不是 polyglot 名人”

---

### 14. Xiaomanyc 小马在纽约（街头采访创作者）

**视频**

- 标题：How I Learn Any Language in 24 Hours
- 频道：[Xiaomanyc 小马在纽约](https://www.youtube.com/@xiaomanyc)
- URL：<https://www.youtube.com/watch?v=r3wiEHX8QdU>
- 发布：2020-02-11；约 209 万次观看

**背景**

频道 About：*Until the age of 18 I grew up speaking exclusively English, and then I got the chance to learn Mandarin and live in Beijing for a year...* 他是街头采访/文化创作者，不是教授或语言学校。18 岁前单语、赴北京一年后扩展到多种语言，符合“创作者 / 旅居者”。

**后来变化**：About 现链到 <https://www.streetsmartlanguages.com/>；本视频描述也有 beginner Chinese course 和西班牙语平台联盟链接。他已是职业语言内容创作者并卖课。收录的是 2020 年这条方法自述，不要写成“隐藏的普通上班族”。

**明确提到的方法**（视频描述）

- 24 小时内练到能进行**基本对话**，他写明 *This definitely isn't fluency*。
- 跳过北京学中文的前史可从 3:42 开始。
- 多年用免费间隔重复工具 [Anki](https://apps.ankiweb.net/) 记单词和句子。
- 方法灵感来自 [All Japanese All The Time](http://www.alljapaneseallthetime.com/blog/)。
- 另有旧频道 [ariinbeijing](https://www.youtube.com/user/ariinbeijing)。

Facebook 转载短视频摘要出现 *write everything into Anki the way that the word or the...*，那是另一条短视频，不能直接当成这条 11 分钟片的逐字稿。

**SEO 主题**

- “24 小时学会一门语言”的诚实版本：只是能开场对话，不是流利
- Anki 记的是短语，不是孤立单词
- 街头开口之前，先用间隔重复把常用句装进脑子
- AJATT 式沉浸如何被一个非日语学习者挪用

---

### 15. Maddie's Days（加拿大旅日生活博主）

**视频**

- 标题：How To Start Learning Japanese For Beginners | Self Study Resources
- 频道：[Maddie's Days](https://www.youtube.com/@MaddiesDays)
- URL：<https://www.youtube.com/watch?v=kHwY4PV-YFU>
- 发布：2024-08-05；约 80 万次观看

**背景**

频道 About：*Hello~ My name is Maddie and I'm a girl from Canada living in Japan. I love to draw and make things...* 内容是 DIY、绘画、动漫、咖啡馆、旅行。她另有视频 *My Experience Studying at a JAPANESE Language School*，说明后来上过语言学校，但本条是自学资源分享，身份仍是旅日生活博主，不是日语教师。

**明确提到的方法**（描述、章节、资源列表）

- 章节：日语书写系统；词汇和语法；听与说；阅读；Keep a Schedule。
- 口语：italki。
- 阅读：Rikaikun；*Remembering the Kanji* 1/2。
- 词汇：JLPT N5/N4 Tango；Anki；Memrise。
- 语法：JapaneseTest4U N5；Genki 1 课本+练习册。
- 声明这些是她日语路上亲自用过的资源（含联盟链接）。

**SEO 主题**

- 从假名到 Genki 到 Anki：旅日生活博主的自学清单
- 想看懂漫画/动漫，自学顺序怎么排
- 语言学校之前，普通人在家能先做完哪几步
- 固定时间表（Keep a Schedule）比找“最好的 App”更重要

---

### 16. K.D.Wilson（移居日本的美国人）

**视频**

- 标题：How I Learned Japanese in One Year
- 频道：[K.D.Wilson](https://www.youtube.com/@KDWil)
- URL：<https://www.youtube.com/watch?v=PgSER61GiYU>
- 发布：2025-10-17；约 9000 次观看

**背景**

描述：*I’m K.D.Wilson. I'm an American who has somehow made his way to Japan. I share advice on all things related to Japan from a foreign perspective.* 他是旅日/移居内容创作者，不是日语教师。描述另有 *Work with me to move to Japan* 咨询链接——这是移居咨询，不是语言培训机构。

**明确提到的方法**（描述）

- 一开始什么都试：teachers, tutors, textbooks, apps；有效，但后来失去动力。
- 转机是 *a better reason to learn: real conversations*。
- 把练习变成游戏，让学习重新有趣。
- 具体教材名、每天多久、是否影子跟读：**描述未写，标未核验**。
- 描述有“Best Japanese book I've ever used”联盟链接，书名需点开 Amazon 才能确认，本次**未打开该链接核验书名**。

**SEO 主题**

- 教材和 App 都试过之后，真正让人坚持下来的是真实对话
- “一年日语”广告标题下的诚实版本：先失去动力，再找到理由
- 移居者学日语：动机从考试转到生活

---

### 17. Charlene Cong（香港到瑞士的金融从业者）

**视频**

- 标题：How I passed German B1 exam from A1 in just 6 months (With a full time job)
- 频道：[Charlene Cong, CFA🇨🇭](https://www.youtube.com/@CharleneCong)
- URL：<https://www.youtube.com/watch?v=bN0CVTsVyMg>
- 发布：2025-02-22；约 1.0 万次观看

**背景**

频道 About：苏黎世投资教练、前 JPMorgan，主业是理财教育（FinFit / VISION Academy），不是语言教师。视频描述写她分享自己过德语 B1 的经历。索引字幕：*to Switzerland from Hong Kong in 2022*；前两年在瑞士上班。符合移民 + 上班族。

后来她离开企业做投资教练，那是金融课，不是语言培训。频道里德语内容是个人考试故事，不是德语学校。

**明确提到的方法**（描述、章节、索引字幕）

- 章节：My journey；Intensive Course；Self-Created Pressure；Obsession；Tools I used。
- 描述自称三点关键，并列出工具：Slow German Podcast、Preply、自己的 OneDrive 笔记。
- 索引字幕：加入强化班，*two hours per day Monday to Friday*，持续四周。完整口播未下载；强化班校名、作业量、口语考试细节 **未核验**。
- Preply 链接带推荐参数。她是否长期用家教：**描述列为工具，具体课时未写**。

**SEO 主题**

- 全职工作从 A1 到 B1：强化班 + 播客 + 家教怎么拼
- 移民过语言考试：自己给自己加压，而不是等“有空再学”
- 金融从业者学德语，故事重点是考试和生活，不是成为 polyglot

---

### 18–20. Mattheos Drivas（上班族，后来做语言 App）

**代表视频**

- 标题：How I Learn Multiple Languages While Working a 9-5 (just copy me)
- 频道：[Mattheos Drivas](https://www.youtube.com/@MattheosDrivas)
- URL：<https://www.youtube.com/watch?v=EvPPn_76NN0>
- 发布：2026-07-19；约 18 万次观看
- 相关：
  - [How I Learned 6 Languages by 21 (you can too)](https://www.youtube.com/watch?v=GSb82LcT0ek)（2025-07-26，约 64 万次）
  - [How I'd Learn a Language From Scratch in 2026](https://www.youtube.com/watch?v=DeytEWM_nI4)（2026-08-09）

**背景**

9-5 视频描述：*I work a full time 9-5, and over the past few years I've still managed to learn six languages.* 频道 About：*learning languages & documenting the process*；梦想是去当地用当地语言交流。他不是教授或语言学校教师。

**后来变化**：描述和 6 语视频都推广他自己在做的 App Speakeasy（<https://learnspeakeasy.com>）。收录的是上班族作息和分语种自学故事，必须写明他后来在做语言产品。

**明确提到的方法**（三支视频的作者自写描述）

9-5 作息（EvPPn_76NN0）：

- 秘诀是 *consistent pockets of time layered into the day you already have*。
- 早上输入：健身房听播客、喝咖啡时阅读。
- 空档用目标语思考。
- 工作日偷塞闪卡。
- 晚上两段专注学习，含一节真实的 italki 粤语课。
- 章节：Pre Work Studying；At Work；Post Work Studying。

分语种（GSb82LcT0ek）：

- 通用四点：少纠结语法和字母，先找和生活相关的短语并开口；常听歌并逐行翻译；大量看目标语内容并记下生词；每天一点、保持连贯。
- 西班牙语：Dreaming Spanish、Spanish After Hours、Spotify 歌单。
- 粤语：@5minutecantonese、@cantobritt、书 *Cantonese For Everyone*（Chow Bun Ching）。
- 葡萄牙语：书 *Tudo bem Vamos aprender Português*、Spotify 歌单。
- 普通话：Shuoshuo、Grace、Rita 等频道；HSK 系列“对有些人有用，对我个人没用”。
- 章节含 Greek（是否Heritage：**描述未写死，标未核验**）。

五步法（DeytEWM_nI4）：

1. Find your WHY
2. Learn your starter phrases
3. Learn the basics — WITH structure
4. Go from learner → speaker（immersion + speaking practice）
5. Actually go use it

他写当天从零越南语练到真实对话。一天能到什么程度，只有作者自述，没有第三方核验。

**SEO 主题**

- 朝九晚五学六语：上班前 / 班上 / 下班后怎么切
- 先生活短语和歌，语法往后放
- HSK 课本对有的人没用：换 YouTube 频道
- “从学习者变成说话的人”：沉浸还要加上开口
- 写作须注明：讲述者后来在做 Speakeasy

---

### 21. İclal（19 岁学生）

**视频**

- 标题：how to learn languages when you have work or school?
- 频道：[İclal](https://www.youtube.com/@iclaliano)
- URL：<https://www.youtube.com/watch?v=qR6fOm1IlkQ>
- 发布：2024-09-08；约 5.2 万次观看

**背景**

描述自评：19 years old；living in milan/istanbul；语言列表 turkish, french, english, italian, spanish, german, russian, dutch, swedish。频道 About：*i talk a lot (in many languages)*。People & Blogs，不是语言学校。各语水平、是否学校必修：**除列表外未核验**。

视频有 Lingoda 赞助（描述写明 *this video is sponsored by Lingoda*）。她是学生创作者接赞助，不是 Lingoda 教师。

**明确提到的方法**（章节，作者自写）

- set priorities
- create a learning habit
- lingoda | back to school（赞助段）
- optimise your free time
- connect language learning & responsibilities
- passive learning
- don't be a perfectionist

各节具体做法：**完整字幕未下载，标未核验**。不要把章节标题写成操作步骤。

**SEO 主题**

- 上学或打工时学语言：先排优先级，再养成习惯
- 把学习和已有责任绑在一起，而不是另开一整块时间
- 被动输入 + 不要完美主义
- 引用时标明 Lingoda 是赞助，不是她的亲身主方法（除非口播另有说明，本次未核验）

---

### 22. Nate - のと（用剧自学的日语母语者）

**视频**

- 标题：How to learn any languages from TV shows | 10+ years of experience in 10 mins
- 频道：[Nate - のと](https://www.youtube.com/@natenoto)
- URL：<https://www.youtube.com/watch?v=rcYXV9Fy9Xk>
- 发布：2024-03-02；约 3.9 万次观看

**背景**

频道 About：*I love learning languages by myself with Netflix and YouTube.* 母语日语；英语为第二语言且 *Never lived there*；正在学台湾华语；在香港住过约 10 个月；大学有韩语课但不说。他是自学者，不是语言教师。

索引字幕：*I'm a native Japanese speaker and I acquired English...*

**明确提到的方法**（描述与章节）

- 用 Netflix、YouTube 等剧集学任何语言。
- 章节：Why from TV shows（利弊）；How to choose content；How I actually learn from TV shows；How to review your study；How I shadow the script；When you REALLY don't understand；Summary。
- 影子跟读（shadow the script）是章节标题里明确出现的方法。
- 选片标准、复盘步骤、听不懂时怎么办：**描述未展开，完整字幕未下载，标未核验**。

**SEO 主题**

- 没住过英语国家，靠剧和 YouTube 习得英语
- 看剧不是“当背景音”：选片、复盘、跟读剧本
- 听不懂时停下来做什么（章节有，细节待补字幕）

---

### 23. Aneli（同时学三语的生活向创作者）

**视频**

- 标题：How I Study 3 Languages at Once! | Polyglot Language Learning Tips & Routine
- 频道：[Aneli ⋆.𐙚 ̊](https://www.youtube.com/@Nelsdigitaldiary)
- URL：<https://www.youtube.com/watch?v=lRGT4AHahhs>
- 发布：2025-02-07；约 5.2 万次观看

**背景**

频道 About 只有 *Make yourself at home*。分类 People & Blogs。视频写她同时学法语、韩语、日语，并分享日程和资源。没有教师资质或学校。职业、是否在校：**未核验**。当作生活向自学创作者。

**明确提到的方法**（描述自列要点）

- daily language study routine breakdown
- 做一份真能执行的 schedule
- 网上学语言的资源（具体名单：**描述未列出，标未核验**）
- 保持动力、避免 burnout

**SEO 主题**

- 同时学三语：先有日程，再谈资源
- 防 burnout，而不是再加一本教材
- 素材较弱，适合当补充案例，不宜当方法主证据

---

## 跨样本里反复出现、且能引用一手文字的方法

这些是多条记录**各自用自己的描述/转写**提到的，不是把专家理论安到普通人头上。

| 模式 | 谁明确写到 | 适合的 SEO 角度 |
| --- | --- | --- |
| 用自己爱看的视频/剧当输入 | Ruri（vlog）、Pearly（entertaining method）、Veroniq（YouTube）、smolbiskit（TV shows）、Xiaoma（AJATT 灵感）、Nate（Netflix/YouTube）、Mattheos（看内容并记生词） | 词表失败之后看什么 |
| 夹缝时间和小习惯 | Zoe（洗碗走路；Tiny Habits）、delancey（每天 30 分钟）、Pearly（busy person 章节）、Mattheos（班前/班上/班后）、İclal（habit / free time） | 上班族/学生怎么学 |
| Anki / 闪卡 | delancey、Xiaoma、Maddie、Mattheos（工作日偷塞闪卡） | 记的是句子还是单词 |
| 输出：自言自语、家教、真实对话 | Ruri（对镜子说）、delancey（italki 课）、K.D.Wilson（real conversations）、Mattheos（italki 粤语）、Charlene（Preply）、Nate（shadow the script） | 为什么能听不能说 |
| 学校输入过多、输出过少 | Ruri 转写、Veroniq 标题 *School Failed Me* | 和“为什么背单词没用”同一问题 |
| 先定很小的生活目标 | Ruri（看懂 James Charles）、K.D.Wilson（真实对话）、a-tekt（留学）、Mattheos（Find your WHY）、Charlene（过 B1） | 目标不是“成为 polyglot” |
| 移民/考试压力 | Charlene（强化班 + 自己加压）、K.D.Wilson（移居后才找到理由） | 为生活过关，不是为当网红 |

与仓库已挂 slug `why-word-lists-fail` 最贴的素材：Ruri / Veroniq 的“学校失败”、Xiaoma 的“Anki 记短语不是流利”、smolbiskit / Nate 的剧集输入、Zoe 的“能对话就算会说”、Mattheos 的“HSK 对我没用”。不要把他们写成 RemeMate 用户，也不要承诺产品里没有的功能。

---

## 写作时不要用的人

检索里热度很高、但不符合“普通人”标准：

- 职业 polyglot / 课程公司：Olly Richards、Steve Kaufmann、Benny Lewis、Luca Lampariello、Mikel Hyperpolyglot（未核验其是否卖课，但频道定位是 hyperpolyglot 教学，本次不收）。
- 语言教师频道：Billy Korean、Canguro English、Bob the Canadian、Japanese Ammo with Misa 等。
- 已明确卖系统课或做语言教练的频道：Veronika's Language Diaries（Language Mastery Program）；Lindie Botes（频道描述自称 language coach，并联合创办 AI 语言导师 Lingolette，[Become a polyglot in 2025](https://www.youtube.com/watch?v=uIF4GMnqG6w)）；Lina Vasquez（频道 About 写 language learning strategies + personal development coaching）；Matthew Alberto / Speakada（描述写曾在 Fluent Forever 工作，现做 Speakada）。
- Ruri、Xiaoma、Veroniq、Mattheos **可以引用自学/上班故事**，正文必须写后来卖课、陪练或自做语言 App。

---

## 未决 / 未核验

- 绝大多数视频的**完整口播字幕**未能用 `yt-dlp` 或无签名 `timedtext` 下载。方法细节若只存在于口播、不在描述里，一律标未核验。
- Zoe 首支视频里每门语言的具体学法；Pearly 各“Step”的操作细节；a-tekt 用过哪些语法书；smolbiskit 是否全职工作；kate 的西语/ASL/韩语路径；K.D.Wilson 的“最好的日语书”书名；İclal 各章节的具体做法；Nate 选片与复盘细则；Aneli 的资源名单；Charlene 强化班校名；Mattheos 的希腊语是否为家庭语言。
- Ruri 2021 原视频描述已被 ADHD 产品覆盖，无法从当前描述恢复当年方法列表。
- The Language Mind、Street Smart Languages、Wannaspeak 陪练、Ruri Teachable 的现行价格与教学内容：本次只确认链接存在，未逐页审计。
- 订阅数、观看数会变；文中数字是 2026-08-15 Innertube / 视频页快照。

---

## 一手来源清单

### YouTube 视频页（oEmbed 或 Innertube `player`）

- https://www.youtube.com/watch?v=MWj8pxhxrv0
- https://www.youtube.com/watch?v=y4VrWc0PM3M
- https://www.youtube.com/watch?v=AF21PyR9ohU
- https://www.youtube.com/watch?v=dYikKyL4lIA
- https://www.youtube.com/watch?v=HJDttYLrbB4
- https://www.youtube.com/watch?v=wVNEXPuKJrE
- https://www.youtube.com/watch?v=OkKTgm9XxEg
- https://www.youtube.com/watch?v=HGQLckoU_3I
- https://www.youtube.com/watch?v=DS0OSbjFedo
- https://www.youtube.com/watch?v=uZ0o4rvl6_Q
- https://www.youtube.com/watch?v=NQlFIrSZiIE
- https://www.youtube.com/watch?v=7YX7PAdo4B0
- https://www.youtube.com/watch?v=UIsCnqTSYUs
- https://www.youtube.com/watch?v=oMx5oZQlkt4
- https://www.youtube.com/watch?v=FB_6Kx2OiD4
- https://www.youtube.com/watch?v=r3wiEHX8QdU
- https://www.youtube.com/watch?v=kHwY4PV-YFU
- https://www.youtube.com/watch?v=PgSER61GiYU
- https://www.youtube.com/watch?v=bN0CVTsVyMg
- https://www.youtube.com/watch?v=EvPPn_76NN0
- https://www.youtube.com/watch?v=GSb82LcT0ek
- https://www.youtube.com/watch?v=DeytEWM_nI4
- https://www.youtube.com/watch?v=qR6fOm1IlkQ
- https://www.youtube.com/watch?v=rcYXV9Fy9Xk
- https://www.youtube.com/watch?v=lRGT4AHahhs

### YouTube 频道 About（Innertube `browse` / `channelMetadataRenderer`）

- https://www.youtube.com/@zoe.languages
- https://www.youtube.com/@a-tekt
- https://www.youtube.com/@delanceydays
- https://www.youtube.com/@smolbiskit
- https://www.youtube.com/@pearlywong
- https://www.youtube.com/@ruriohama
- https://www.youtube.com/@wannaspeakbyveroniq
- https://www.youtube.com/@murakamireads
- https://www.youtube.com/@xiaomanyc
- https://www.youtube.com/@MaddiesDays
- https://www.youtube.com/@CharleneCong
- https://www.youtube.com/@MattheosDrivas
- https://www.youtube.com/@iclaliano
- https://www.youtube.com/@natenoto
- https://www.youtube.com/@Nelsdigitaldiary

### 字幕转写

- https://pickscribe.com/v/7YX7PAdo4B0 （Ruri 2022 更新视频，已通读）

### 身份补充（二手，不单独当方法证据）

- RealLife English BB 22：https://podcasts.apple.com/gb/podcast/bb-22-she-went-from-beginner-to-fluent-in-just-9-months/id600128442?i=1000546240720
- Ruri 后来的课程页：https://ruri-ohama-s-school.teachable.com/p/how-to-learn-any-language-language-learning-masterclass
- Xiaoma 后来的课程站：https://www.streetsmartlanguages.com/
