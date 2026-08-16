# SEO1.1：公开 Blog 图片支持范围与规格

> 日期：2026-08-15
> 状态：已批准在独立 feature 分支实现；尚未发布或部署。
> 关联计划：[公开 Q&A / Blog 与 SEO 内容短计划](./2026-08-14-public-seo-content.md)

## 1. 背景

SEO1 当前的受控 Markdown 只渲染标题、段落、列表、链接、粗体和行内代码。它拒绝原始 HTML，也不识别 Markdown 图片语法。因此，放在 `content/` 下的文章配图不会显示；生成的 `<img>` 也会被内容校验拒绝。

文章配图是 SEO1 内容发布的必需能力，必须在正式内容上线前完成。

## 2. 目标

让仓库内的静态 Blog 文章可以安全地引用一张或多张随代码发布的本地图片，并满足：

- 图片可在英文和中文文章页稳定显示；
- 图片不会成为用户上传或任意文件读取入口；
- 图片有必填、可审查的 `alt` 文本；
- 图片 URL 可被 canonical 页面正常抓取，但不单独进入 sitemap；
- 图片路径不会受 `../`、绝对路径、协议 URL 或 HTML 注入影响；
- 文章仍由服务端渲染，不引入前端框架和 CMS；
- 图片不存在、格式不允许或元数据错误时，构建/加载测试明确失败，而不是静默输出坏链接。

## 3. 非目标

本切片不做：

- 用户上传、后台媒体库、数据库图片、CDN 或图片处理服务；
- 评论、头像、画廊、轮播、灯箱、视频和音频；
- 外链图片、远程图片代理或动态图片抓取；
- 自动裁剪、压缩、WebP 转换或响应式图片生成；
- sitemap 中的独立图片条目或 Google Images 专项优化；
- 直接允许文章写原始 `<img>` HTML；
- 借图片支持扩展 Markdown 为任意 HTML。

## 4. 内容与文件模型

### 4.1 推荐文件布局

图片与文章按 slug 共址，但不放在 `content/` 内容文本目录中：

```text
app/static/public/blog/<slug>/cover.webp
app/static/public/blog/<slug>/figure-1.webp
content/en/blog/<slug>.md
content/zh/blog/<slug>.md
```

英文和中文版本共用同一组图片；如果确实需要语言专属图片，再使用：

```text
app/static/public/blog/<slug>/en/figure-1.webp
app/static/public/blog/<slug>/zh/figure-1.webp
```

本切片要求支持多图：Blog 可有一张可选 cover 图和正文内多张说明图；FAQ 的每个问题可有零张或多张说明图。

### 4.2 Front matter

文章增加可选字段：

```yaml
image: public/blog/why-word-lists-fail/cover.webp
image_alt: A quiet desk with a notebook opened to a page of remembered words
```

约束：

- `image` 必须是相对于 `app/static/` 的相对 POSIX 路径；
- 只允许落在 `public/blog/<slug>/` 目录内；
- 必须与文章 slug 匹配；
- 不允许 `..`、反斜杠、前导 `/`、`http://`、`https://`、`data:` 或 `javascript:`；
- `image_alt` 必须是非空纯文本，渲染前进行 HTML escape；
- `image` 与 `image_alt` 必须成对出现；
- 文件必须存在，且扩展名仅允许 `.jpg`、`.jpeg`、`.png`、`.webp`；
- SVG 第一版不允许，避免脚本和外部引用风险；
- 文章没有配图时可以省略两个字段，不显示空的图片容器。

### 4.3 Blog 正文图片

Blog 正文支持受控 Markdown 图片语法：

```markdown
![A notebook beside a cup of tea](public/blog/why-word-lists-fail/figure-1.webp)
```

约束：

- 图片路径必须落在该文章 slug 的静态目录内；
- `alt` 必填且为纯文本；
- 可出现多张图片；
- 不允许原始 HTML、外链图片或协议 URL；
- 图片渲染为带 `loading="lazy"` 的 `<img>`，cover 仍单独使用 `loading="eager"`。

### 4.4 FAQ 图片

`qa.yaml` 的每个 FAQ item 增加可选 `images` 列表：

```yaml
- question: How do I import a word list?
  answer: Start from the word list screen and choose the supported import action.
  images:
    - src: public/qa/import-word-list/step-1.webp
      alt: The word list screen with the import action highlighted
      caption: Open the import action from the word list screen.
```

约束：

- `images` 可为空或包含多项；
- 每项必须有 `src` 和 `alt`，`caption` 可选；
- 路径必须落在 `public/qa/<stable-key>/` 下；
- 每张图片复用与 Blog 相同的路径、扩展名和安全校验；
- FAQ 图片不改变 `FAQPage` JSON-LD 的问答文本结构。

## 5. 页面与 SEO 行为

- Blog 文章页在标题/描述附近渲染 cover 图；无图文章保持现有布局。
- 图片使用 `alt`，不把文件名当作 alt 的替代品。
- 图片使用 `loading="eager"` 仅限 cover；如果加入正文图片，正文图默认 `loading="lazy"`。
- 图片 URL 使用 Flask `url_for('static', filename=...)` 生成，不手拼部署域名。
- Open Graph 增加 `og:image` 和对应的绝对 URL；只有存在 cover 图时输出。
- 可选增加 `twitter:card=summary_large_image`，但不能因缺图输出无效 URL。
- `Article` JSON-LD 在有 cover 图时增加 `image` 数组；没有图片时保持合法 JSON-LD。
- 图片不单独进入 `/sitemap.xml`；文章是否进入 sitemap 仍完全由 `published` / `indexable` 控制。
- `noindex` 占位文章即使有图片，图片也不改变文章的收录状态。

## 6. 安全与失败策略

加载内容时统一校验图片元数据和路径：

1. 解析 front matter；
2. 校验路径为允许的 slug 子路径；
3. 校验扩展名；
4. 解析为 `app/static/` 下的真实路径并确认未越界；
5. 确认文件存在；
6. 传给模板前只传校验后的静态 URL。

任何违反约束的文章都抛出 `PublicContentError`，并在测试中覆盖。不能把不安全路径降级成普通文字或继续发布。

## 7. 验收标准

### 内容与渲染

- 带合法 cover 的英文文章返回 200，并出现正确的 `<img src>`、`alt` 和静态 URL；
- 中文配对文章可引用同一张图片；
- 没有图片的旧文章仍正常渲染；
- 图片文件放在仓库后随部署版本可访问；
- 图片不存在、扩展名不允许、路径越界、缺 alt、只写 image 未写 image_alt 时加载失败。

### SEO

- 有图文章输出正确 `og:image` 和 `Article.image`；
- 无图文章不输出空图片 URL；
- cover 图不改变 `noindex`、sitemap、canonical、hreflang 行为；
- 页面仍保持正确的 `<html lang>` 和绝对 canonical。

### 安全

- 原始 HTML `<img>` 仍被拒绝；
- `![x](https://...)`、`![x](../../...)`、`data:` 和 `javascript:` 均被拒绝；
- 图片路径不能读取 `app/static/` 之外的文件。

### 工程

- 增加单元测试和公开文章路由测试；
- 运行 `pytest --noconftest -q tests/unit/test_public_content.py`；
- 运行目标公开路由集成测试；
- `git diff --check` 通过；
- staging 验证至少检查英文/中文文章、图片 HTTP 200、OG/JSON-LD 和占位 noindex。

## 8. 待确认决策

1. 文章图片是否统一使用共享图片，还是允许英文/中文各自图片？默认共享。
2. 图片格式是否接受现有素材的实际格式；若包含 SVG，需要明确批准后另做安全方案。
3. 是否把首批已生成图片统一转存为 `.webp`，还是保留 `.jpg` / `.png` 原格式？

多图 FAQ、Blog 正文图片和 cover 已获准在本 feature 分支实现；正式部署仍需另一次明确批准。
