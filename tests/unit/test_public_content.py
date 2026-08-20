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


def test_future_visible_from_post_is_hidden(tmp_path):
    _write_tree(tmp_path)
    for locale in ("en", "zh"):
        blog = tmp_path / locale / "blog"
        (blog / "scheduled.md").write_text(
            "---\ntitle: Scheduled\nslug: scheduled\ndescription: scheduled\n"
            "date: 2026-08-14\nvisible_from: 2099-01-01\n"
            "published: true\nindexable: true\n---\n\nLater.\n",
            encoding="utf-8",
        )
    content.configure_content_root(tmp_path)
    try:
        assert content.get_published_post("en", "scheduled") is None
        assert all(post.slug != "scheduled" for post in content.list_published_posts("en"))
        assert all("scheduled" not in item.path for item in content.iter_indexable_urls(registration_enabled=False))
    finally:
        content.configure_content_root(None)


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


def test_markdown_images_are_scoped_and_escaped(tmp_path):
    static = tmp_path / "static"
    asset = static / "public" / "blog" / "demo"
    asset.mkdir(parents=True)
    (asset / "figure.webp").write_bytes(b"image")
    content.configure_static_root(static)
    try:
        html = content.render_limited_markdown(
            "![A & B](public/blog/demo/figure.webp)",
            image_scope="public/blog/demo",
        )
        assert '/static/public/blog/demo/figure.webp' in html
        assert 'alt="A &amp; B"' in html
        with pytest.raises(content.PublicContentError):
            content.render_limited_markdown(
                "![x](https://example.com/x.webp)",
                image_scope="public/blog/demo",
            )
    finally:
        content.configure_static_root(None)


def test_qa_images_load_from_nested_items(tmp_path):
    for locale in ("en", "zh"):
        (tmp_path / locale / "blog").mkdir(parents=True)
        (tmp_path / locale / "qa.yaml").write_text(
            "title: FAQ\ndescription: Description\nindexable: false\n"
            "items:\n  - question: Import?\n    answer: Use the import action.\n"
            "    images:\n      - src: public/qa/{0}/step.webp\n"
            "        alt: Import screen\n        caption: Step one.\n".format(locale),
            encoding="utf-8",
        )
    static = tmp_path / "static"
    for locale in ("en", "zh"):
        image = static / "public" / "qa" / locale
        image.mkdir(parents=True)
        (image / "step.webp").write_bytes(b"image")
    content.configure_content_root(tmp_path)
    content.configure_static_root(static)
    try:
        item = content.get_qa_page("en").items[0]
        assert item.images[0].src == "public/qa/en/step.webp"
        assert item.images[0].caption == "Step one."
    finally:
        content.configure_content_root(None)
        content.configure_static_root(None)


def test_repo_placeholders_load():
    content.configure_content_root(None)
    content.reset_content_cache()
    qa = content.get_qa_page("en")
    post = content.get_published_post("zh", "why-word-lists-fail")
    assert qa.title.startswith("RemeMate")
    assert post is not None
    assert post.date == date(2026, 8, 17)
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


# ---- 多段 Markdown 答案（block scalar）----

QA_BLOCK = """title: Sample Q&A
description: Sample description
indexable: false
items:
  - question: How do I add a word?
    answer: |
      **In one sentence**

      Collect what you actually meet.

      - catch a few words
      - review them later

      ![Add word screen](public/qa/en/add.webp)
"""


def test_qa_block_answer_renders_markdown(tmp_path):
    (tmp_path / "en" / "blog").mkdir(parents=True)
    (tmp_path / "en" / "qa.yaml").write_text(QA_BLOCK, encoding="utf-8")
    static = tmp_path / "static"
    image = static / "public" / "qa" / "en"
    image.mkdir(parents=True)
    (image / "add.webp").write_bytes(b"image")
    content.configure_content_root(tmp_path)
    content.configure_static_root(static)
    try:
        item = content.get_qa_page("en").items[0]
        assert "<strong>In one sentence</strong>" in item.answer_html
        assert "<ul>" in item.answer_html
        assert '<img src="/static/public/qa/en/add.webp"' in item.answer_html
        # JSON-LD plain text keeps wording but drops the inline image syntax
        assert "Collect what you actually meet" in item.answer
        assert "![Add word screen]" not in item.answer
        assert "add.webp" not in item.answer
    finally:
        content.configure_content_root(None)
        content.configure_static_root(None)


def test_qa_block_answer_rejects_anchor_links(tmp_path):
    (tmp_path / "en" / "blog").mkdir(parents=True)
    (tmp_path / "en" / "qa.yaml").write_text(
        "title: FAQ\ndescription: D\nindexable: false\n"
        "items:\n  - question: Q?\n    answer: |\n      See the section below.\n\n"
        "      More in [8.6](#86-troubleshooting).\n",
        encoding="utf-8",
    )
    content.configure_content_root(tmp_path)
    try:
        with pytest.raises(content.PublicContentError):
            content.get_qa_page("en")
    finally:
        content.configure_content_root(None)


def test_qa_block_answer_rejects_out_of_scope_image(tmp_path):
    (tmp_path / "en" / "blog").mkdir(parents=True)
    (tmp_path / "en" / "qa.yaml").write_text(
        "title: FAQ\ndescription: D\nindexable: false\n"
        "items:\n  - question: Q?\n    answer: |\n      ![x](public/blog/demo/x.webp)\n",
        encoding="utf-8",
    )
    static = tmp_path / "static"
    (static / "public" / "blog" / "demo").mkdir(parents=True)
    (static / "public" / "blog" / "demo" / "x.webp").write_bytes(b"x")
    content.configure_content_root(tmp_path)
    content.configure_static_root(static)
    try:
        with pytest.raises(content.PublicContentError):
            content.get_qa_page("en")
    finally:
        content.configure_content_root(None)
        content.configure_static_root(None)
