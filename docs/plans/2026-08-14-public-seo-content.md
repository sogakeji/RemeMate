# 公开 Q&A / Blog 与 SEO 内容短计划

> 日期：2026-08-14
> 状态：SEO1 已完成开发并在新云机 staging 验证；当前待提交、审核和合并，正式环境未部署。
> 依据：用户 2026-08-14 获客决策、grilling（Q1–Q4 = A/A/A/`why-word-lists-fail`）、同日 SEO1 开发批准及 staging 验证；`docs/BACKLOG.md`、`docs/strategy/2026-07-09-three-month-focus.md`、现有公开 Landing。

## 目标

给未登录访问者增加可被搜索引擎收录的 Q&A 页和 Blog，使 RemeMate 不再只有一张 Landing 可被检索。首版用仓库内静态文章支撑持续写作，而不是先做编辑后台。

成功标准（工程可验收，不是流量承诺）：

- 未登录可打开中英文 Q&A、Blog 列表和那篇已挂上的文章，无需账号。
- 每页有独立 title、meta description、canonical；Q&A 输出 `FAQPage` JSON-LD，文章输出 `Article` JSON-LD。
- `/robots.txt` 与 `/sitemap.xml` 只列出允许收录的公开页；已登录产品页默认 `noindex`。
- 未登录 Landing 增加 Q&A / Blog 文字入口，不重做 Landing 布局、不改 Hero / 视频 / 标题断行。
- 首版先各一页占位：中英各一份 Q&A、中英配对的一篇 Blog。占位可预览但 `noindex`、不进 sitemap；用户写好正文后只改内容文件，不改路由。

流量（展示、点击、收录）是上线后的观察指标，不是本计划的工程完成条件。

## 已确认的问题

当前公开面几乎只有 `/` 的 Landing：

- 无 description / canonical / Open Graph；
- 无 `robots.txt`、`sitemap.xml`；
- 无 Q&A、无文章列表、无文章页；
- Landing 用页内 `data-zh` / `data-en` 切换，同一 URL 两种语言，不适合作为文章的长期 SEO 模型。

写作本身不能提高收录；必须先有稳定 URL、可抓取 HTML 和站点地图。

## 已裁定

1. **静态内容，不做 CMS。** 文章和问答住在仓库里，随代码发布。无数据库、无后台编辑、无用户投稿、无评论。
2. **首版中英双语，一页一语。** 中文和英文是成对的独立 URL，不在同一内容 URL 上用 JS 切语言。Landing 维持现有页内双语切换，只加入口。
3. **无前缀是英文，中文加 `/zh`。** `hreflang x-default` 指向英文 URL。Landing 继续停在 `/`。
4. **Landing 只加入口。** 各一个 Q&A、一个 Blog 文字链接；`href` 跟随 Landing 当前语言（英文去无前缀，中文去 `/zh/...`）。不重做 Landing，不改 Hero / 视频 / 标题断行。
5. **先各一篇占位。** 先挂上 Q&A 页和 1 篇 Blog（中英各一份），正文由用户稍后替换。不在本轮写满题库，也不先做 3 篇文章。
6. **占位可预览，暂不收录。** 占位页 `published: true`、HTTP 200，但 `noindex` 且不进 sitemap。用户替换正文并打开收录标记后，才进入 sitemap 并去掉 `noindex`。
7. **首版只服务获客，不服务登录后产品。** 不改复习、词库、SessionPad、注册模型。
8. **产品页不参与内容索引。** `/`、开放注册时的 `/register` 与 `/login` 可收录；词库、复习、阅读、写作、广场、伙伴、设置、admin、token 链接、`/healthz` 一律 `noindex`。Q&A / Blog 按第 6 条的收录标记决定。
9. **不引入前端框架。** 公开内容用服务端渲染的轻量模板；可新增小型 Markdown 依赖，不把 Markdown 渲染做成通用用户内容管道。

## 路由

| 页面 | 英文 | 中文 |
| --- | --- | --- |
| Q&A | `/qa` | `/zh/qa` |
| Blog 列表 | `/blog` | `/zh/blog` |
| Blog 文章 | `/blog/<slug>` | `/zh/blog/<slug>` |
| robots | `/robots.txt` | 同左 |
| sitemap | `/sitemap.xml` | 同左 |

canonical 使用已有 `PUBLIC_BASE_URL`。首篇 slug 固定为 `why-word-lists-fail`。

## 内容模型

新增只读模块 `public_content`（名称可在实现时微调），作为 Q&A / Blog 的唯一读取入口。路由只做 URL、404 和模板，不扫目录、不解析 front matter。

建议接口：

```python
list_published_posts(locale) -> list[PostSummary]
get_published_post(locale, slug) -> Post | None
get_qa_page(locale) -> QaPage
iter_indexable_urls() -> list[IndexableUrl]
```

仓库布局：

```text
content/
  zh/qa.yaml
  en/qa.yaml
  zh/blog/why-word-lists-fail.md
  en/blog/why-word-lists-fail.md
```

同一篇文章中英共用一个 `slug`，靠目录区分语言。`qa.yaml` 提供页级 title / description、`indexable`（或等价标记），以及问题、回答列表，供页面和 `FAQPage` JSON-LD 共用。

文章 Markdown 只允许很小的 front matter：`title`、`slug`、`description`、`date`、`updated?`、`published`、`indexable`。正文禁止原始 HTML；只渲染受控子集（标题、段落、列表、链接、加粗、代码）。

- 未 `published: true`：不出现在列表和 sitemap，访问其 slug 返回 404。
- `published: true` 且未 `indexable`：200，出现在列表，带 `noindex`，不进 sitemap。首版占位用这一档。
- `published: true` 且 `indexable`：200，进列表和 sitemap，可收录。

进程内缓存文件内容；测试可注入临时目录。不要按请求读盘后拼 HTML 却无测试。

### 定时公开字段

批量预置文章时保留 `date` 作为文章发布日期/内容日期，不复用它控制显示。新增独立字段 `visible_from`：

```yaml
date: 2026-08-10
visible_from: 2026-08-16
```

`visible_from` 不晚于站点业务日期时，文章才出现在 Blog 列表、可访问并可进入 sitemap；未来文章返回 404。`Article` JSON-LD 的 `datePublished` 继续使用 `date`。站点业务日期统一使用 `Asia/Shanghai`，具体实现需补定向测试。

## 页面与 SEO 契约

公开内容页使用独立轻量布局，不套登录后 `base.html` 导航。每页必须有：

- 与该页语言一致的 `<html lang>`
- 唯一 `<title>` 和 meta description
- 绝对地址 canonical
- 指向成对译文的 `hreflang`（`en`、`zh-Hans`、`x-default`→英文）
- 基本 Open Graph（title / description / type / url）
- 指向 `/`、当前语言 Q&A、当前语言 Blog 的页头或页脚链接，以及登录 / 注册（注册入口仍受 `OPEN_REGISTRATION_ENABLED` 控制）
- 一个指向成对译文的文字链接

`/robots.txt`：允许抓取公开内容；Disallow 登录后产品前缀（`/words`、`/review`、`/write`、`/reading`、`/partners`、`/square`、`/settings`、`/admin`、`/intake` 等）。不要靠 robots 充当权限。

`/sitemap.xml` 只含 `iter_indexable_urls()`：首页、当时允许收录的登录 / 注册页，以及 `indexable` 的 Q&A / Blog。首版占位不在其中。

Q&A 与文章必须是对产品事实的陈述，不承诺未做功能，不重新打开已关闭的在线词典 API，不把 SessionPad 写成聊天室或 App。占位稿只说明正文待更新，不得编造产品能力。

## 首批内容

只准备两对页面：

- Q&A：`content/en/qa.yaml` 与 `content/zh/qa.yaml`，各一个“正文待更新”问答对，`indexable: false`。
- Blog：`/blog/why-word-lists-fail` 与 `/zh/blog/why-word-lists-fail`，短占位正文，`published: true`、`indexable: false`。

后续加篇目只新增 `content/` 文件，不改信息架构。正文由人工定稿；本计划不授权批量生成站内软文。

## 切片

### SEO1：公开内容地基 + 占位页

- 新增公开内容蓝图与 `public_content` 读取模块。
- 实现上表路由。
- 给公开内容页补 SEO head；给登录后产品模板补默认 `noindex`。
- Landing 只加随当前语言切换的 Q&A / Blog 文字链接。
- 挂上中英占位 Q&A 与中英配对的 1 篇占位文章。
- 定向集成测试：未登录 200、未知 slug 404、草稿 404、占位 `noindex` 且不在 sitemap、产品页含 `noindex`、注册开关仍控制公开页上的注册入口、Landing 既有断言不回退、中英页互指 `hreflang`、Landing 中英切换后入口指向对应语言 URL。

### SEO1.1：公开内容多图支持

- 在独立 feature 分支实现 Blog 正文多图和 FAQ 条目多图；图片随代码发布，不做用户上传或 CMS。
- 图片使用受控本地路径、必填 `alt`，并校验路径越界、外链、格式和文件存在性。
- Blog 支持 cover、正文 Markdown 图片、Open Graph 与 Article JSON-LD 图片字段；FAQ 支持每个问题的多张说明图和可选 caption。
- 增加渲染、安全、路由与 noindex 行为测试；完成 staging 验证后，才进入 SEO2 正文替换。
- 详细规格见 `docs/plans/2026-08-15-public-content-images-spec.md`。

### SEO2：替换正文

- 用户提供定稿后，只改 `content/` 中的 Q&A 与那篇文章，并把 `indexable` 打开。
- 校对事实、内链和 description。

### SEO3：上线后观察（不阻塞 SEO1）

- 部署后提交 sitemap，登记 Search Console / 必应收录。
- 观察索引数、查询词、落地页；软结论记入 Backlog，不据此立刻改信息架构。

批准本计划只授权 SEO1。部署仍需另一次明确批准。

## 测试规模

- SEO1：公开路由与 sitemap / robots / noindex / hreflang 的定向集成测试；不默认全量。
- SEO2：内容替换后的标题 / description / 列表 / sitemap 断言；`git diff --check`。
- 不改 RLS、额度、迁移；不跑生产 doctor，除非进入已批准的部署。

## 不在本计划内

- 内容管理后台、富文本编辑器、评论、标签、站内搜索、RSS / 订阅产品；
- 用户生成 Blog / 广场文章做 SEO；
- Landing 重设计、SessionPad、小程序 / App；
- 独立英文站或子域；
- Google Analytics 或其他第三方统计；
- 重新启用在线词典 API；
- 为了写文章改产品语义或编造未上线能力；
- 首版写满 FAQ 题库或多篇 Blog。

## 待批准

SEO1 已完成开发和 staging 验证。当前尚未提交或合并入 `master`；正式环境部署仍需另一次明确批准。
