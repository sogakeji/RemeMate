"""public_content 读取、占位收录规则与受限 Markdown。"""
from datetime import date
from pathlib import Path

import pytest

from app.services import public_content as content


QA = """title: Sample Q&A
description: Sample description
indexable: {indexable}
items:
  - question: What is this?
    answer: A test answer.
"""

POST = """---
title: {title}
slug: {slug}
description: {description}
date: 2026-08-14
published: {published}
indexable: {indexable}
---

Collect the words you **actually meet**.
"""


def _write_tree(root: Path, *, qa_indexable=False, extra_posts=None):
    for locale, title in (("en", "Why word lists fail"), ("zh", "为什么背完词表还是不会用")):
        (root / locale / "blog").mkdir(parents=True)
        (root / locale / "qa.yaml").write_text(
            QA.format(indexable="true" if qa_indexable else "false"),
            encoding="utf-8",
        )
        (root / locale / "blog" / "why-word-lists-fail.md").write_text(
            POST.format(
                title=title,
                slug="why-word-lists-fail",
                description="placeholder",
                published="true",
                indexable="false",
            ),
            encoding="utf-8",
        )
    extra_posts = extra_posts or []
    for locale, slug, published, indexable, title in extra_posts:
        (root / locale / "blog" / f"{slug}.md").write_text(
            POST.format(
                title=title,
                slug=slug,
                description="extra",
                published="true" if published else "false",
                indexable="true" if indexable else "false",
            ),
            encoding="utf-8",
        )


@pytest.fixture
def catalog(tmp_path):
    _write_tree(tmp_path)
    content.configure_content_root(tmp_path)
    yield tmp_path
    content.configure_content_root(None)


def test_lists_published_placeholder_but_not_indexable(catalog):
    posts = content.list_published_posts("en")
    assert [post.slug for post in posts] == ["why-word-lists-fail"]
    assert posts[0].indexable is False
    assert content.get_qa_page("zh").indexable is False
    urls = content.iter_indexable_urls(registration_enabled=True)
    assert [item.path for item in urls] == ["/", "/login", "/register"]


def test_unpublished_post_is_absent(tmp_path):
    _write_tree(
        tmp_path,
        extra_posts=[
            ("en", "draft-note", False, False, "Draft"),
            ("zh", "draft-note", False, False, "草稿"),
        ],
    )
    content.configure_content_root(tmp_path)
    try:
        assert content.get_published_post("en", "draft-note") is None
        assert all(post.slug != "draft-note" for post in content.list_published_posts("en"))
    finally:
        content.configure_content_root(None)


def test_indexable_pair_enters_sitemap(tmp_path):
    _write_tree(
        tmp_path,
        qa_indexable=True,
        extra_posts=[
            ("en", "ready-post", True, True, "Ready"),
            ("zh", "ready-post", True, True, "已就绪"),
        ],
    )
    content.configure_content_root(tmp_path)
    try:
        paths = [item.path for item in content.iter_indexable_urls(registration_enabled=False)]
        assert "/qa" in paths
        assert "/zh/qa" in paths
        assert "/blog/ready-post" in paths
        assert "/zh/blog/ready-post" in paths
        assert "/blog/why-word-lists-fail" not in paths
        assert "/login" in paths
        assert "/register" not in paths
    finally:
        content.configure_content_root(None)


def test_render_limited_markdown_and_reject_html():
    html = content.render_limited_markdown(
        "Use [RemeMate](/register) and **output**.\n\n- one\n- two"
    )
    assert '<a href="/register">RemeMate</a>' in html
    assert "<strong>output</strong>" in html
    assert "<ul><li>one</li><li>two</li></ul>" in html
    with pytest.raises(content.PublicContentError):
        content.render_limited_markdown("Hello <script>alert(1)</script>")
    with pytest.raises(content.PublicContentError):
        content.render_limited_markdown("[x](javascript:alert(1))")


def test_repo_placeholders_load():
    content.configure_content_root(None)
    content.reset_content_cache()
    qa = content.get_qa_page("en")
    post = content.get_published_post("zh", "why-word-lists-fail")
    assert qa.title.startswith("RemeMate")
    assert post is not None
    assert post.date == date(2026, 8, 14)
    assert post.indexable is False


@pytest.fixture
def public_client():
    import config
    from app import create_app

    content.configure_content_root(None)
    content.reset_content_cache()
    previous = config.TestingConfig.SQLALCHEMY_DATABASE_URI
    config.TestingConfig.SQLALCHEMY_DATABASE_URI = (
        previous
        or "postgresql://rememate:x@127.0.0.1:5432/rememate_test"
    )
    try:
        app = create_app("testing")
        app.config["PUBLIC_BASE_URL"] = "https://rememate.com"
        yield app.test_client()
    finally:
        config.TestingConfig.SQLALCHEMY_DATABASE_URI = previous


def test_public_routes_render_placeholders(public_client):
    qa = public_client.get("/qa")
    zh_post = public_client.get("/zh/blog/why-word-lists-fail")
    listing = public_client.get("/blog")
    missing = public_client.get("/blog/missing-slug")
    landing = public_client.get("/")
    sitemap = public_client.get("/sitemap.xml")
    robots = public_client.get("/robots.txt")
    login_page = public_client.get("/login")

    assert qa.status_code == 200
    assert "FAQPage" in qa.get_data(as_text=True)
    assert 'name="robots" content="noindex,follow"' in qa.get_data(as_text=True)
    assert zh_post.status_code == 200
    assert "Article" in zh_post.get_data(as_text=True)
    assert listing.status_code == 200
    assert "why-word-lists-fail" in listing.get_data(as_text=True)
    assert missing.status_code == 404
    assert 'data-href-en="/qa"' in landing.get_data(as_text=True)
    assert "/qa" not in sitemap.get_data(as_text=True)
    assert "Disallow: /words" in robots.get_data(as_text=True)
    assert 'name="robots" content="noindex"' not in login_page.get_data(as_text=True)
