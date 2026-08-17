"""Capture RemeMate staging screenshots for the FAQ doc (docs/FAQ/images).
Runs against http://127.0.0.1:8892 (SSH tunnel to staging.rememate.com service).
"""
import sys, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8892"
EMAIL = "faq-test@example.com"
PASSWORD = "XrcOnph4rmpLw5oD"
OUT = r"D:\home\Rememate\docs\FAQ\images"

def shot(page, name, settle=1.5):
    try:
        page.wait_for_load_state("networkidle", timeout=25000)
    except Exception:
        pass
    time.sleep(settle)
    page.screenshot(path=f"{OUT}/{name}.png")
    print("SHOT:", name, "| url:", page.url[:80])

def try_shoot(page, name, fn):
    try:
        fn()
        shot(page, name)
    except Exception as e:
        print("FAIL:", name, "->", repr(e)[:200])
        try:
            shot(page, name)  # still save whatever rendered
        except Exception as e2:
            print("FAIL-shot:", name, repr(e2)[:120])

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(locale="zh-CN", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    # ---------- public ----------
    page.goto(f"{BASE}/", timeout=30000)
    shot(page, "faq-01-landing-zh")
    page.goto(f"{BASE}/login", timeout=30000)
    shot(page, "faq-02-login-zh")

    # ---------- login ----------
    page.fill('form:has(input[name="email"]) input[name="email"]', EMAIL)
    page.fill('form:has(input[name="email"]) input[name="password"]', PASSWORD)
    page.click('form:has(input[name="email"]) button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=25000)
    print("LOGIN ->", page.url)
    assert "/login" not in page.url, "login failed: " + page.url

    page.goto(f"{BASE}/", timeout=30000)
    shot(page, "faq-00-home-task-zh")

    # ---------- settings / languages ----------
    try_shoot(page, "faq-04-settings-zh", lambda: page.goto(f"{BASE}/settings", timeout=30000))

    # ---------- words: add 3 words ----------
    def add_word(w, ctx_text):
        page.goto(f"{BASE}/words/add", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        fields = page.locator("input, select, textarea").evaluate_all(
            "els => els.map(e => (e.name || e.id))")
        print("add fields:", fields)
        wf = page.locator('input[name="word"]')
        if wf.count():
            wf.fill(w)
        cf = page.locator('textarea[name="context"], textarea[name="example"], input[name="context"]').first
        if cf.count():
            cf.fill(ctx_text)
        sel = page.locator('select').first
        if sel.count():
            opts = sel.locator("option").evaluate_all("els => els.map(e => e.value)")
            print("select options:", opts[:6])
            if opts:
                sel.select_option(opts[0])
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=25000)
        print("added", w, "->", page.url)
    for w, c in [("bonjour", "Bonjour, comment ça va ?"),
                 ("rendez-vous", "On a un rendez-vous demain à dix heures."),
                 ("se dépêcher", "Il faut se dépêcher, le train part bientôt.")]:
        try_shoot(page, "skip", lambda: add_word(w, c))

    # words list + detail
    try_shoot(page, "faq-05-words-zh", lambda: page.goto(f"{BASE}/words", timeout=30000))
    try:
        page.goto(f"{BASE}/words", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        href = page.locator('a[href*="/words/"]').first.get_attribute("href")
        if href and "/words/add" not in href:
            page.goto(f"{BASE}{href}", timeout=30000)
            shot(page, "faq-07-word-detail-zh")
    except Exception as e:
        print("detail fail:", repr(e)[:150])

    # intake import + quick add
    try_shoot(page, "faq-08-import-zh", lambda: page.goto(f"{BASE}/intake/import", timeout=30000))
    try_shoot(page, "faq-09-candidates-zh", lambda: page.goto(f"{BASE}/intake/quick_add", timeout=30000))

    # sessionpad candidates
    try_shoot(page, "faq-11-sessionpad-zh", lambda: page.goto(f"{BASE}/intake/sessionpad/candidates", timeout=30000))

    # review
    try_shoot(page, "faq-12-review-zh", lambda: page.goto(f"{BASE}/review", timeout=30000))

    # story
    def story():
        page.goto(f"{BASE}/review/story", timeout=30000)
        page.wait_for_timeout(25000)  # AI generation
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
    try_shoot(page, "faq-13-story-zh", story)

    # write: sentence + diary
    try_shoot(page, "faq-14-write-zh", lambda: page.goto(f"{BASE}/write", timeout=30000))
    try_shoot(page, "faq-15-diary-zh", lambda: page.goto(f"{BASE}/write?mode=diary", timeout=30000))

    # square
    try_shoot(page, "faq-16-square-zh", lambda: page.goto(f"{BASE}/square", timeout=30000))

    # partners: create one partner then recap form
    def partners():
        page.goto(f"{BASE}/partners", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        if page.locator('a[href="/partners/new"]').count():
            page.click('a[href="/partners/new"]')
            page.wait_for_load_state("networkidle", timeout=20000)
            fields = page.locator("input, select, textarea").evaluate_all(
                "els => els.map(e => (e.name || e.id) + ':' + e.tagName)")
            print("partner form fields:", fields)
            name_in = page.locator('input[name="name"]')
            if name_in.count():
                name_in.fill("Test Partner")
            sel = page.locator('select').first
            if sel.count():
                opts = sel.locator("option").evaluate_all("els => els.map(e => e.value)")
                if opts:
                    sel.select_option(opts[0])
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=25000)
            print("partner created ->", page.url)
    try_shoot(page, "faq-17-partners-zh", partners)

    def recap_form():
        page.goto(f"{BASE}/partners", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        href = page.locator('a[href*="/partners/"]').first.get_attribute("href")
        if href and "/new" not in href:
            page.goto(f"{BASE}{href}/recaps/new", timeout=30000)
    try_shoot(page, "faq-18-recap-zh", recap_form)
    try_shoot(page, "faq-19-packets-zh", lambda: page.goto(f"{BASE}/partner-packets", timeout=30000))

    # reading: new doc -> show -> lookup
    def reading():
        page.goto(f"{BASE}/reading/new", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        ta = page.locator("textarea").first
        if ta.count():
            ta.fill("Le soleil se lève sur la ville. Nous prenons le café ensemble, puis nous partons à la gare.")
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=30000)
            print("reading doc ->", page.url)
            # click a word to trigger lookup
            page.locator("text=rendez-vous, café, gare").first.click(timeout=5000)
            page.wait_for_timeout(4000)
    try_shoot(page, "faq-10-reading-zh", reading)

    # stats
    try_shoot(page, "faq-20-stats-zh", lambda: page.goto(f"{BASE}/stats", timeout=30000))

    browser.close()
print("DONE")
