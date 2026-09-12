"""公开 Q&A / Blog / sitemap / robots，以及 Landing 入口与产品页 noindex。"""
from html.parser import HTMLParser

import pytest

from tests.helpers import login, provision_user

PW = "pw12345678"
PLACEHOLDER = "why-word-lists-fail"


def test_repo_public_pages_are_indexable_and_localized(client):
    qa = client.get("/qa")
    zh_qa = client.get("/zh/qa")
    post = client.get(f"/blog/{PLACEHOLDER}")
    zh_post = client.get(f"/zh/blog/{PLACEHOLDER}")
    listing = client.get("/blog")
    zh_listing = client.get("/zh/blog")

    for resp in (qa, zh_qa, post, zh_post, listing, zh_listing):
        assert resp.status_code == 200
        page = resp.get_data(as_text=True)
        assert 'name="robots" content="noindex,follow"' not in page
        assert 'rel="canonical"' in page
        assert 'hreflang="en"' in page
        assert 'hreflang="zh-Hans"' in page
        assert 'hreflang="x-default"' in page

    qa_page = qa.get_data(as_text=True)
    assert "FAQPage" in qa_page
    assert "RemeMate FAQ" in qa_page
    assert "1.1 What is RemeMate" in qa_page
    assert "<strong>In one sentence</strong>" in qa_page
    assert "这是" in zh_qa.get_data(as_text=True)
    assert "<strong>一句话结论</strong>" in zh_qa.get_data(as_text=True)
    assert "Article" in post.get_data(as_text=True)
    assert "Why Word Lists Fail" in listing.get_data(as_text=True)
    assert "为什么词表没用" in zh_listing.get_data(as_text=True)
    assert 'href="/zh/qa"' in qa_page
    assert 'href="/blog/why-word-lists-fail"' in listing.get_data(as_text=True)


def test_unknown_and_draft_slugs_are_404(client, tmp_path):
    assert client.get("/blog/missing-slug").status_code == 404
    assert client.get("/zh/blog/missing-slug").status_code == 404

    from app.services import public_content as content

    for locale, title in (("en", "Draft"), ("zh", "草稿")):
        blog = tmp_path / locale / "blog"
        blog.mkdir(parents=True)
        (tmp_path / locale / "qa.yaml").write_text(
            "title: Q\ndescription: D\nindexable: false\nitems:\n"
            "  - question: Q?\n    answer: A.\n",
            encoding="utf-8",
        )
        (blog / "why-word-lists-fail.md").write_text(
            "---\ntitle: Live\nslug: why-word-lists-fail\ndescription: d\n"
            "date: 2026-08-14\npublished: true\nindexable: false\n---\n\nLive.\n",
            encoding="utf-8",
        )
        (blog / "draft-note.md").write_text(
            f"---\ntitle: {title}\nslug: draft-note\ndescription: d\n"
            "date: 2026-08-14\npublished: false\nindexable: false\n---\n\nHidden.\n",
            encoding="utf-8",
        )
    content.configure_content_root(tmp_path)
    try:
        assert client.get("/blog/draft-note").status_code == 404
        assert "draft-note" not in client.get("/blog").get_data(as_text=True)
    finally:
        content.configure_content_root(None)


def test_sitemap_and_robots_include_indexable_public_content(app, client, tmp_path):
    from app.services import public_content as content

    for locale, title in (("en", "Public article"), ("zh", "公开文章")):
        blog = tmp_path / locale / "blog"
        blog.mkdir(parents=True)
        (tmp_path / locale / "qa.yaml").write_text(
            f"title: {title} FAQ\ndescription: Public FAQ\nindexable: true\n"
            "items:\n  - question: Public question?\n    answer: Public answer.\n",
            encoding="utf-8",
        )
        (blog / "public-article.md").write_text(
            f"---\ntitle: {title}\nslug: public-article\ndescription: Public article\n"
            "date: 2026-09-05\npublished: true\nindexable: true\n---\n\nPublic body.\n",
            encoding="utf-8",
        )

    content.configure_content_root(tmp_path)
    app.config["PUBLIC_BASE_URL"] = "https://rememate.com"
    app.config["OPEN_REGISTRATION_ENABLED"] = False
    try:
        public_paths = (
            "/qa",
            "/zh/qa",
            "/blog",
            "/zh/blog",
            "/blog/public-article",
            "/zh/blog/public-article",
        )
        for path in public_paths:
            page = client.get(path).get_data(as_text=True)
            assert 'name="robots" content="noindex,follow"' not in page

        closed = client.get("/sitemap.xml")
        assert closed.status_code == 200
        closed_body = closed.get_data(as_text=True)
        assert "<loc>https://rememate.com/</loc>" in closed_body
        assert "<loc>https://rememate.com/login</loc>" in closed_body
        assert "/register" not in closed_body
        for path in public_paths:
            assert f"<loc>https://rememate.com{path}</loc>" in closed_body

        app.config["OPEN_REGISTRATION_ENABLED"] = True
        opened = client.get("/sitemap.xml").get_data(as_text=True)
        assert "<loc>https://rememate.com/register</loc>" in opened
    finally:
        content.configure_content_root(None)

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    text = robots.get_data(as_text=True)
    assert "Disallow: /words" in text
    assert "Disallow: /healthz" in text
    assert "Sitemap: https://rememate.com/sitemap.xml" in text


class _HeadTags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        if tag in ("meta", "link"):
            self.tags.append((tag, dict(attrs)))


@pytest.mark.parametrize("origin, expected", [
    (None, "https://rememate.com/"),
    ("", "https://rememate.com/"),
    ("https://public.example/", "https://public.example/"),
])
@pytest.mark.parametrize("registration_enabled", [True, False])
def test_landing_metadata_uses_public_origin(
    app, client, origin, expected, registration_enabled
):
    app.config["PUBLIC_BASE_URL"] = origin
    app.config["OPEN_REGISTRATION_ENABLED"] = registration_enabled
    response = client.get("/?source=test", headers={"Host": "untrusted.example"})
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    head = _HeadTags()
    head.feed(page)
    canonical = [a["href"] for tag, a in head.tags
                 if tag == "link" and a.get("rel") == "canonical"]
    og_url = [a["content"] for tag, a in head.tags
              if tag == "meta" and a.get("property") == "og:url"]
    assert canonical == [expected]
    for url in canonical + og_url:
        assert "?" not in url
        assert "untrusted.example" not in url
    description = [a["content"] for tag, a in head.tags
                   if tag == "meta" and a.get("name") == "description"]
    assert len(description) == 1
    assert "reading and conversations" in description[0]
    for prop, value in {
        "og:title": "RemeMate — remember the words you actually meet",
        "og:description": description[0],
        "og:type": "website",
        "og:url": expected,
    }.items():
        assert [a["content"] for tag, a in head.tags
                if tag == "meta" and a.get("property") == prop] == [value]
    assert '<title>RemeMate — remember the words you actually meet</title>' in page
    assert not any("hreflang" in a for _, a in head.tags)
    assert not any(a.get("name") == "robots" and "noindex" in a.get("content", "")
                   for _, a in head.tags)


def test_landing_metadata_does_not_change_authenticated_home(app, client):
    provision_user(app, "seo-home@t.com", PW)
    login(client, "seo-home@t.com", PW)
    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'name="robots" content="noindex"' in page
    assert 'property="og:url"' not in page
    assert "Collect words and expressions from your reading and conversations." not in page


def test_landing_links_follow_language_and_keep_registration_gate(app, client):
    app.config["OPEN_REGISTRATION_ENABLED"] = True
    page = client.get("/").get_data(as_text=True)
    assert 'data-href-en="/qa"' in page
    assert 'data-href-zh="/zh/qa"' in page
    assert 'data-href-en="/blog"' in page
    assert 'data-href-zh="/zh/blog"' in page
    assert "data-href-en" in page
    assert "el.setAttribute('href', href)" in page
    assert 'href="/register"' in page

    app.config["OPEN_REGISTRATION_ENABLED"] = False
    closed = client.get("/").get_data(as_text=True)
    assert "/register" not in closed
    assert 'data-href-en="/qa"' in closed


def test_product_pages_are_noindex_login_is_indexable(app, client):
    provision_user(app, "seo@t.com", PW)
    login(client, "seo@t.com", PW)
    settings = client.get("/settings").get_data(as_text=True)
    assert 'name="robots" content="noindex"' in settings

    client.get("/logout")
    login_page = client.get("/login").get_data(as_text=True)
    assert 'name="robots" content="noindex"' not in login_page

    app.config["OPEN_REGISTRATION_ENABLED"] = True
    register_page = client.get("/register").get_data(as_text=True)
    assert 'name="robots" content="noindex"' not in register_page
