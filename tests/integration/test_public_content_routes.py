"""公开 Q&A / Blog / sitemap / robots，以及 Landing 入口与产品页 noindex。"""
from tests.helpers import login, provision_user

PW = "pw12345678"
PLACEHOLDER = "why-word-lists-fail"


def test_public_placeholder_pages_are_previewable_and_not_indexed(client):
    qa = client.get("/qa")
    zh_qa = client.get("/zh/qa")
    post = client.get(f"/blog/{PLACEHOLDER}")
    zh_post = client.get(f"/zh/blog/{PLACEHOLDER}")
    listing = client.get("/blog")
    zh_listing = client.get("/zh/blog")

    for resp in (qa, zh_qa, post, zh_post, listing, zh_listing):
        assert resp.status_code == 200
        page = resp.get_data(as_text=True)
        assert 'name="robots" content="noindex,follow"' in page
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
    assert "Why word lists fail" in listing.get_data(as_text=True)
    assert "为什么背完词表还是不会用" in zh_listing.get_data(as_text=True)
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


def test_sitemap_and_robots_omit_placeholders(app, client):
    app.config["PUBLIC_BASE_URL"] = "https://rememate.com"
    app.config["OPEN_REGISTRATION_ENABLED"] = False
    closed = client.get("/sitemap.xml")
    assert closed.status_code == 200
    closed_body = closed.get_data(as_text=True)
    assert "<loc>https://rememate.com/</loc>" in closed_body
    assert "<loc>https://rememate.com/login</loc>" in closed_body
    assert "/register" not in closed_body
    assert "/qa" not in closed_body
    assert PLACEHOLDER not in closed_body

    app.config["OPEN_REGISTRATION_ENABLED"] = True
    opened = client.get("/sitemap.xml").get_data(as_text=True)
    assert "<loc>https://rememate.com/register</loc>" in opened

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    text = robots.get_data(as_text=True)
    assert "Disallow: /words" in text
    assert "Disallow: /healthz" in text
    assert "Sitemap: https://rememate.com/sitemap.xml" in text


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
