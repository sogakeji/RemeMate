# SEO growth v2：首轮检查与下一切片

> 最终状态：S01 产品代码 `6c0d0e4` 已按批准部署；两篇英文核心文章实时测试通过，且各一次收录请求均已确认入队。下面按执行顺序保留历史状态，最终结果见末节。

## 状态与边界

- 用户批准：先检查技术 SEO、收录情况与现有内容入口，再选择小切片；不发布、不操作生产。
- 基准：`62b446be7b1503276f6f341e9d2c9ba0364aa764`；分支 `feature/seo-growth-v2`。
- `feature/public-seo-content-v1`、`feature/seo1-multi-image-content`、`seo/index-public-content` 相对 master 均无独有提交，因此从最新 master 开新分支。
- 本轮只新增本文档；不改产品代码、配置、凭据或数据。
- 检查日期：2026-09-12。线上证据为匿名 HTTPS GET 的原始 HTML/文本/XML，不是搜索引擎收录结果。

## 已核对的证据

### 线上响应

| 地址 | 结果 |
| --- | --- |
| `/` | 200；一个 H1；有 title；无 description、canonical、hreflang、OG 元信息 |
| `/robots.txt` | 200；允许公开内容抓取；声明 `https://rememate.com/sitemap.xml` |
| `/sitemap.xml` | 200；XML 可解析；35 个 URL，96 个语言 alternate 链接 |
| `/blog`、`/zh/blog` | 均 200；有 description、自引用 canonical、en/zh-Hans/x-default，无 meta noindex |
| `/qa`、`/zh/qa` | 同上，另有 JSON-LD 脚本 |
| `/blog/language-exchange-notes` 及对应中文页 | 同上，另有 JSON-LD 脚本 |
| `/blog/chatgpt-speaking-practice-that-does-not-disappear` | 200；上述基础元信息存在，另有 JSON-LD 脚本 |
| `/login`、`/register` | 200；无 meta noindex；无 description 或 canonical |
| `/zh/` | 404；目前不存在此中文首页 |
| 随机构造的不存在文章地址 | 404，未返回软 404 的 200 |

Sitemap 组成：根首页、登录、注册共 3 项；双语 FAQ 2 项；14 篇文章的双语版本共 28 项；双语博客列表 2 项。并未逐个抓取全部 35 个地址。JSON-LD 仅确认脚本存在，未做富媒体结果资格或完整 schema 验证。

### 代码与内容

- `app/templates/main/landing.html`：独立模板，未使用 public/base 的元信息；初始 HTML 为英语，中文靠 localStorage 与 JS 切换，同一个 URL。不应给不存在的中文首页添加 hreflang。
- `app/blueprints/main/routes.py`：匿名访问 `/` 渲染 landing。
- `app/templates/public/base.html`：已有 description、canonical、语言 alternate、OG 和 indexable 控制；已有导航注册入口，不能称为“没有 CTA”。
- `app/blueprints/public/routes.py`：公开页、robots、sitemap 路由已经存在。
- `app/services/public_content.py`：可见性考虑 published/visible_from；sitemap 的双语文章要求两种语言都可见且 indexable；登录与开放注册页当前明确列入 sitemap，不擅自改动此策略。
- `app/templates/public/post.html`：已有 Article JSON-LD；文章正文后没有统一的情境式下一步入口。
- `content/en/blog/`：14 篇文章，其中 11 篇带专栏排期。多个人物故事标题偏叙事，例如 “Between the Sink and the Page”；它们不如任务式标题直接表达学习问题，但这不是搜索流量差的已证实原因。
- 现有任务型内容包括语伴笔记、ChatGPT 口语练习与单词表问题，适合先维护，不需重新立项写重复文章。
- 已细读 `language-exchange-notes.md`：已有正文内链到单词表文章和首页；改进方向是可直接使用的笔记示例及更明确的下一步，而不是声称现有文章没有内链。

## 判断与优先级

1. **先补首页元信息。** 这是已证实且范围小的缺口，不等于抓取被阻止，也不能承诺增加排名。OG 用于分享展示，不当作直接排名因素。
2. **取得 Search Console 基线。** 账号是否配置、站点验证、sitemap 提交、收录/排除原因、查询曝光与点击目前未知。只请求本站报告或脱敏导出，不需要用户提供密码。不用 sitemap 可访问代替已收录结论。
3. **再选一篇现有任务型文章改善内容与入口。** 优先语伴笔记文章；搜索需求与优先语言仍需数据或用户确认，不把 front matter keywords 当成需求证据。
4. **中文独立首页单列后续切片。** 需要明确 URL、服务端语言渲染、切换行为、canonical/hreflang 与旧页面兼容；不顺带塞进元信息补齐。

暂不做：批量 AI 文章、全站重设计、第三方追踪 SDK、凭空增加关键词页、为 SEO 修改已登录产品工作流。登录页是否继续索引另行决策，不直接认定是硬 bug。

## 推荐下一实施合同（待确认）

**S01：首页基础元信息补齐**

- 只对匿名首页添加准确的英文 description、自引用绝对 canonical、OG title/description/type/url；标题保留现有产品定位，是否调整另行说明。
- URL 复用现有 `public_content.absolute_url` 与 `PUBLIC_BASE_URL` 规则，不根据不可信 Host 头拼接。
- 不添加不存在的 `/zh/` alternate，不改变现有语言切换、登录后首页、注册开关或页面布局。
- 无需新图片；不编造评分、用户量或其他结构化数据。
- 验收：匿名 HTML 有且只有一套正确元信息；配置的公开 origin 生效且缺省行为与现有公开页一致；登录用户首页仍保持原行为；现有公开页/注册开关测试不回归。
- 测试：运行首页及 public content 相关的定向集成测试，`git diff --check`；使用隔离测试配置，不接生产数据库，不读取或改动 `.env`/`.venv`。
- 不提交、不 push、不合并、不部署，除非另获授权。

## 首轮验证限制（后续 GSC 补查见下节）

- Kimi WebBridge daemon 启动后报告 `no extension connected`；未完成真实浏览器渲染、移动端或性能检查。可按 https://www.kimi.com/zh-cn/features/webbridge 连接扩展后补查。
- 未访问 Search Console；未知是否接入，无收录/曝光/点击结论。
- 未做关键词搜索量、竞品、外链或 Google 官方文档研究。
- 本轮为文档变更，只运行 `git diff --check`；未运行应用测试。

## 后续：Search Console 只读补查

用户随后授权通过 Kimi WebBridge 查看已登录浏览器。扩展已连接；安装脚本在覆盖已有二进制时失败，未强停服务。以下为 `rememate.com` 域资源的汇总，不记录 Google 账号身份或原始私有导出。

### 报告读数（2026-09-12）

- 效果：8 次点击、32 次曝光、CTR 25%、平均排名 9.7。
- 初始为 28 天；选择 3 个月后 URL 与选项更新，但图表仍显示 2026-08-13 至 2026-09-09，读数不变。由于前端交互/数据范围尚有不确定性，这组数按图表实际显示日期记录，不宣称覆盖完整三个月。
- 可见查询仅 `re mate`（0 点击、2 曝光）和 `recimate`（0 点击、1 曝光）。查询行不能解释全部总数，不据此断言全部流量都是品牌搜索。
- 网页索引：2 页已编入、20 页未编入。其中 noindex 17 页、重定向 2 页、重复且未选定规范页 1 页。
- noindex 验证已开始，开始日期 2026-09-06。前 10 条示例的上次抓取时间为 8 月 17–18 日，包括语伴笔记、单词表与人物故事的中英文页面，以及部分 www 版本。
- Sitemap：`https://rememate.com/sitemap.xml` 状态成功；2026-09-05 提交，2026-09-09 上次读取，已发现 35 页、0 视频。

### 对优先级的修正

- 主要可见瓶颈是内容收录覆盖有限、搜索曝光极少，不是已证实的标题点击率问题。32 次曝光太少，25% CTR 与平均排名不宜用于判断 SEO 已成功。
- 历史 noindex 样本的抓取时间早于现有允许索引的部署，且已启动验证；结合首轮线上 HTML，优先跟踪重新抓取与验证，而不是再次盲改 indexable。
- 35 个 sitemap 发现页与索引报告 22 个已知页来自不同报告/更新过程，不将差值直接称为 13 个故障页。
- 下一步应对首页与少量关键文章逐项做 URL 检查，核对 Google 上次抓取、当前是否允许索引、选定 canonical；区分旧状态、www 重复与真实抓取问题。
- 不需要重复提交已成功读取的 sitemap；本次未点击请求编入索引、重新验证或任何提交/设置按钮。
- S01 首页元信息补齐仍可作为小切片，但不能承诺它会解决旧 noindex 的重新抓取问题。暂不批量扩充内容。

### 尚未完成

- 效果报告的网页维度切换未得到确认结果，不报告各页点击分布。
- 尚未展开重定向/重复页示例、未逐 URL 检查，也未发起实时测试或请求编入索引。
- 本补查未修改网站、生产配置或 Search Console 设置；仍仅更新此文档。

## S01 执行与逐 URL 检查（用户已批准）

用户批准逐项检查首页与两篇核心文章，并实施首页元信息补齐。以下结果取代前述“尚未逐 URL 检查”的状态；原先汇总读数保留为检查过程记录。

### Google URL 检查

| URL（域名均为 https://rememate.com） | Google 当前报告 | 抓取与规范网址 |
| --- | --- | --- |
| `/` | 已收录 | 上次抓取 2026-09-10 02:50:32（界面显示时间，未推断时区）；Googlebot 智能手机版；允许抓取、抓取成功、允许索引；用户声明 canonical 为“无”，Google 选择“所检查的网址” |
| `/blog/language-exchange-notes` | 已发现 - 尚未编入索引 | 抓取时间、抓取许可、索引许可、声明 canonical 与 Google canonical 均为“不适用”；发现来源为 sitemap，引荐页为 `/blog/why-word-lists-fail` |
| `/blog/chatgpt-speaking-practice-that-does-not-disappear` | 已发现 - 尚未编入索引 | 上述抓取与 canonical 字段均为“不适用”；发现来源为 sitemap，未检测到引荐来源页 |

这是 Google 已存储的索引报告，不是实时抓取测试。没有点击请求编入索引或实时测试。两篇文章当前单页结果不能归为 noindex 或 canonical 冲突；它们也不代表全部 17 条历史 noindex 都已解决。“未检测到引荐来源”不能证明网站没有内链。

### 已实现

- `app/blueprints/main/routes.py`：仅匿名首页传入 canonical，复用 `public_content.absolute_url` 和 `PUBLIC_BASE_URL`；不以请求 Host 或 query 拼接。
- `app/templates/main/landing.html`：保留标题，添加 description、canonical、OG title/description/type/url。未改正文布局、语言切换或添加不存在的中文 alternate。
- `tests/integration/test_public_content_routes.py`：增加 4 组公开 origin/注册开关组合测试及 1 项已登录首页回归；确认元信息唯一、Host 不影响 canonical、无虚构 hreflang、已登录首页继续 noindex。

### 测试与环境

- 本机无 Docker，因此在 onlytest 创建独立临时目录 `/tmp/rememate-seo-s01-wRdzKO`，用 `git archive HEAD` 加本次三个文件覆盖构造测试副本。
- 临时 Python 环境位于该目录的 `test-python`。系统缺少 ensurepip，使用系统 pip 的 `--target` 安装依赖到该临时环境，没有安装系统包或修改已有虚拟环境。
- 首次依赖下载长时间未完成，终止本任务对应 pip 进程后，用命令级清华 PyPI 镜像完成安装；未修改全局 pip 配置。
- 运行 `test-python/bin/python scripts/run_isolated_tests.py -- -q tests/integration/test_public_content_routes.py tests/integration/test_home_task_card.py tests/integration/test_home_review_card.py`：**19 passed in 7.49s**。
- 运行器创建并清理自身一次性 PostgreSQL；未连接共享 staging 或生产数据库。
- `git diff --check` 通过。变更限首页路由/模板和测试，未运行全量 pytest。
- 浏览器短暂返回 `No current window`，随后重新打开任务标签并完成以上 URL 检查。

### 后续边界

当前补丁尚未提交、合并、push 或部署。先审阅并批准发布，再验证线上 canonical。两篇核心文章可另获批准后做实时 URL 测试，确认允许索引后各请求一次收录；不反复提交 sitemap，不承诺收录或排名。暂缓批量内容扩张。

## Herdr 分工验收与发布前检查

用户允许通过 Herdr 右侧子 pane 将简单实现交给 Grok。创建同目录右侧 pane，保留主 pane 焦点；Grok `seo-tests` 只获分配 `tests/integration/test_public_content_routes.py`，不操作应用代码、浏览器、SSH、配置或 Git 发布动作。

- Grok 增加空字符串 `PUBLIC_BASE_URL` 的缺省值测试（覆盖注册开启/关闭），并显式检查 canonical 和 og:url 不包含请求 query 或测试用不可信 Host。
- 主 agent 复核应用实现与实际测试 diff，确认只增加上述测试边界，没有扩展实现范围。
- Grok 提及纯空白 origin 的防御性处理；`config.py` 的生产 `optional_configured()` 已 strip 并将空值归一化，当前补丁复用既有 URL helper，因此不扩大本切片去修改共享配置逻辑。
- 将验收后的测试文件同步至原独立测试目录，重跑同一组三个定向集成测试文件：**21 passed in 7.79s**。最终 `git diff --check` 通过。
- 右侧子 pane 保留；没有另建工作区、分支或 worktree。未运行全量 pytest。

用户随后明确批准以下第 1–4 项涉及的提交、合并、push、备份部署、验证，以及两篇文章实时检查通过后各请求一次收录。批准不包含注册/密钥/依赖/数据库结构变更。执行结果另行记录。

按以下顺序执行：

1. 审阅四个交付文件，确认只有首页元信息、回归测试和本记录；确认最新工作区状态，不吸收额外用户改动。
2. 获批准后提交、合并 master、push；按仓库既有部署流程备份并发布，不引入数据库迁移或配置变更。
3. 发布后验证匿名首页 description/canonical/OG、已登录首页、公开文章和注册开关；执行目标环境 `flask doctor --strict`，验证服务、HTTPS、日志与数据保全。
4. 另获批准后，对两篇核心文章运行 Search Console 实时 URL 测试；允许抓取/索引且 canonical 正确时，各请求一次收录并记录时间。不重复提交已成功读取的 sitemap。
5. 后续复查 Google 抓取与索引状态，再决定是否需要强化首页到文章的内链或改进正文；不以短期未收录直接断言内容质量差。

## 最终发布与收录请求结果（2026-09-12）

### 发布

- 用户批准后提交 `6c0d0e4`，fast-forward 合并 master 并 push origin；生产部署前 HEAD 为 `62b446b`，master 工作区干净。
- 通过 Git bundle 部署，生产 fast-forward 至 `6c0d0e4`，没有改注册开关、密钥、依赖或数据库结构。
- 备份目录：`/home/ubuntu/rememate-backups/deploy-20260912T123211Z-62b446b-to-6c0d0e4`。包含 PostgreSQL 自定义格式 dump、可解析的 dump 目录、部署前 Git bundle、HEAD/状态及校验文件；未做隔离恢复演练，不将可解析目录称为恢复验证。
- 部署前后 `.env`、venv Python/flask 文件校验一致；migration 均为 `e9f0a1b2c3d4`。
- `flask doctor --strict` 全 OK；服务 active/enabled；生产回环 HTTPS 与外部 HTTPS `/healthz` 均返回 `{"status":"ok"}`。
- 最初 HTTP 回环请求返回预期 HTTPS 重定向 301，随后用 `--resolve rememate.com:443:127.0.0.1` 完成真正的内部 HTTPS healthz 检查。
- 部署后服务日志检查共 20 行，Traceback/ERROR/CRITICAL 标记为 0；只输出汇总，不保存敏感原始日志。
- 外部匿名 `/?source=seo-check` 为 200，canonical 与 og:url 都为 `https://rememate.com/`，description 生效，注册入口保留。
- 两篇文章 200、canonical 自引用、无 meta noindex；注册页 200；匿名 `/settings` 302。已登录首页由隔离集成测试验证，没有使用真实生产用户账号做登录冒烟。
- 定向测试最终仍为 21 passed；此次文档收口只跑 git diff --check，不重复运行全量测试。

### Google 实时检查与请求

| 英文文章路径 | 实时测试界面时间 | 结果 | 收录请求 |
| --- | --- | --- | --- |
| `/blog/language-exchange-notes` | 2026-09-12 20:35:23 | Google 检查工具智能手机版；允许抓取、抓取成功、允许索引；声明 canonical 为自身 | 本轮点击一次，Google 确认“已请求编入索引”，已加入优先抓取队列 |
| `/blog/chatgpt-speaking-practice-that-does-not-disappear` | 2026-09-12 20:39:39 | 同上，声明 canonical 为自身 | 本轮点击一次，同样确认入队 |

时间按 Search Console 界面原样记录，不推断时区。Google 选定 canonical 仍需等编入索引后确定；测试通过、请求入队均不等于已经收录。没有重复提交 sitemap、重新验证整组旧问题或请求其他 URL。任务浏览器标签保留。

下一动作是稍后复查抓取/索引状态及曝光，而不是再次提交同一请求。交接与状态快照已同步；后续 docs-only 收口提交不改变运行时代码。



