"""未登录可访问的 Q&A / Blog / robots / sitemap。"""
from flask import Blueprint, Response, abort, current_app, render_template, url_for

from app.services import public_content as content

bp = Blueprint("public", __name__)


def _base_url() -> str:
    return content.absolute_url(
        current_app.config.get("PUBLIC_BASE_URL"),
        "/",
    ).rstrip("/")


def _page_urls(kind: str, locale: str, slug: str | None = None) -> dict:
    path = content.public_path(kind, locale, slug)
    other = "zh" if locale == "en" else "en"
    other_path = content.public_path(kind, other, slug)
    origin = _base_url()
    return {
        "canonical": f"{origin}{path}",
        "hreflang_en": f"{origin}{content.public_path(kind, 'en', slug)}",
        "hreflang_zh": f"{origin}{content.public_path(kind, 'zh', slug)}",
        "alternate_path": other_path,
        "alternate_locale": other,
    }


def _nav(locale: str) -> dict:
    return {
        "locale": locale,
        "html_lang": content.HTML_LANG[locale],
        "home_path": "/",
        "qa_path": content.public_path("qa", locale),
        "blog_path": content.public_path("blog", locale),
        "login_path": url_for("auth.login"),
        "register_path": (
            url_for("auth.register")
            if current_app.config.get("OPEN_REGISTRATION_ENABLED")
            else None
        ),
    }


def _qa(locale: str):
    page = content.get_qa_page(locale)
    urls = _page_urls("qa", locale)
    return render_template(
        "public/qa.html",
        page=page,
        title=page.title,
        description=page.description,
        indexable=page.indexable,
        og_type="website",
        nav=_nav(locale),
        **urls,
    )


def _blog_index(locale: str):
    posts = content.list_published_posts(locale)
    urls = _page_urls("blog", locale)
    title = "RemeMate Blog" if locale == "en" else "RemeMate 博客"
    description = (
        "Notes on remembering words you actually meet."
        if locale == "en"
        else "关于记住真实遇到的词的文章。"
    )
    return render_template(
        "public/blog_index.html",
        locale=locale,
        posts=posts,
        title=title,
        description=description,
        indexable=False,
        og_type="website",
        nav=_nav(locale),
        **urls,
    )


def _blog_post(locale: str, slug: str):
    post = content.get_published_post(locale, slug)
    if post is None:
        abort(404)
    urls = _page_urls("post", locale, slug)
    return render_template(
        "public/post.html",
        post=post,
        title=post.title,
        description=post.description,
        indexable=post.indexable,
        og_type="article",
        nav=_nav(locale),
        **urls,
    )


@bp.get("/qa")
def qa_en():
    return _qa("en")


@bp.get("/zh/qa")
def qa_zh():
    return _qa("zh")


@bp.get("/blog")
def blog_en():
    return _blog_index("en")


@bp.get("/zh/blog")
def blog_zh():
    return _blog_index("zh")


@bp.get("/blog/<slug>")
def post_en(slug):
    return _blog_post("en", slug)


@bp.get("/zh/blog/<slug>")
def post_zh(slug):
    return _blog_post("zh", slug)


@bp.get("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /words",
        "Disallow: /review",
        "Disallow: /write",
        "Disallow: /reading",
        "Disallow: /partners",
        "Disallow: /partner-packets",
        "Disallow: /square",
        "Disallow: /settings",
        "Disallow: /admin",
        "Disallow: /intake",
        "Disallow: /stats",
        "Disallow: /bark",
        "Disallow: /healthz",
        "Disallow: /forgot-password",
        "Disallow: /reset-password",
        "Disallow: /set-password",
        "Disallow: /verify-email",
        "Disallow: /language/",
        "Disallow: /ui-language",
        f"Sitemap: {_base_url()}/sitemap.xml",
        "",
    ]
    return Response("\n".join(lines), mimetype="text/plain; charset=utf-8")


@bp.get("/sitemap.xml")
def sitemap_xml():
    origin = _base_url()
    urls = content.iter_indexable_urls(
        registration_enabled=bool(
            current_app.config.get("OPEN_REGISTRATION_ENABLED")
        )
    )
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    for item in urls:
        loc = f"{origin}{item.path}"
        parts.append("  <url>")
        parts.append(f"    <loc>{loc}</loc>")
        if item.locale and item.alternate_path:
            en_path = item.path if item.locale == "en" else item.alternate_path
            zh_path = item.path if item.locale == "zh" else item.alternate_path
            parts.append(
                f'    <xhtml:link rel="alternate" hreflang="en" href="{origin}{en_path}"/>'
            )
            parts.append(
                f'    <xhtml:link rel="alternate" hreflang="zh-Hans" href="{origin}{zh_path}"/>'
            )
            parts.append(
                f'    <xhtml:link rel="alternate" hreflang="x-default" href="{origin}{en_path}"/>'
            )
        parts.append("  </url>")
    parts.append("</urlset>")
    parts.append("")
    return Response(
        "\n".join(parts),
        mimetype="application/xml; charset=utf-8",
    )
