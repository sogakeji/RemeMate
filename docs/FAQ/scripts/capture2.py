"""Capture RemeMate staging screenshots for the FAQ doc — v2.
Uses quick-add flow to create real words, then captures all FAQ pages.
Writes page-text snippets to stdout for content verification.
"""
import time
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
    txt = page.inner_text("body")[:150].replace("\n", " | ")
    print(f"SHOT {name} | {page.url[:70]}\n    text: {txt}")

def gotoload(page, path):
    page.goto(f"{BASE}{path}", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass

def fill_first(page, selector, value):
    loc = page.locator(selector).first
    if loc.count():
        loc.fill(value)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(locale="zh-CN", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    # ---- public ----
    gotoload(page, "/")
    # landing defaults to EN; switch to Chinese via the in-page toggle
    zh_toggle = page.locator("a,button,span").filter(has_text="中").first
    if zh_toggle.count():
        zh_toggle.click()
        page.wait_for_timeout(1200)
    shot(page, "faq-01-landing-zh")
    gotoload(page, "/login")
    shot(page, "faq-02-login-zh")

    # ---- login ----
    page.fill('form:has(input[name="email"]) input[name="email"]', EMAIL)
    page.fill('form:has(input[name="email"]) input[name="password"]', PASSWORD)
    page.click('form:has(input[name="email"]) button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=25000)
    print("LOGIN ->", page.url)
    assert "/login" not in page.url

    gotoload(page, "/")
    shot(page, "faq-00-home-task-zh")
    gotoload(page, "/settings")
    shot(page, "faq-04-settings-zh")
    # set learning language = French (required before quick-add works)
    toggle = page.locator('button[data-settings-toggle="learning-panel"]')
    if toggle.count():
        toggle.click()
        page.wait_for_timeout(500)
        page.check('input[name="languages"][value="fr"]')
        page.locator('#learning-panel button[type="submit"]').click()
        page.wait_for_load_state("networkidle", timeout=25000)
        print("learning lang set ->", page.url[:70])
    else:
        print("learning panel toggle not found")

    # ---- words/add form (screenshot only) ----
    gotoload(page, "/words/add")
    shot(page, "faq-06-add-word-zh")

    # ---- quick-add 3 french words -> candidates pages ----
    for w, m in [("bonjour", "你好（问候语）"),
                 ("rendez-vous", "约会、会面"),
                 ("se dépêcher", "赶紧、加快")]:
        gotoload(page, "/intake/quick-add")
        qform = page.locator('form:has(input[name="word"])')
        qform.locator('input[name="word"]').fill(w)
        qform.locator('input[name="meaning"]').fill(m)
        sel = qform.locator('select[name="language_code"]')
        opts = sel.locator("option").evaluate_all("els => els.map(e => e.value)")
        if "fr" in opts:
            sel.select_option("fr")
        qform.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle", timeout=25000)
        print("quick-add", w, "->", page.url[:80])

    # candidates page (now on last source) — screenshot + accept
    path = page.url.replace(BASE, "")
    if path:
        page.goto(f"{BASE}{path}", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
    shot(page, "faq-09-candidates-zh")
    commit_btn = page.locator('button[type="submit"], input[type="submit"]').filter(has_text="入库")
    if commit_btn.count():
        commit_btn.first.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        print("committed ->", page.url[:70])
    else:
        print("no commit button on candidates page")

    # ---- words list + detail ----
    gotoload(page, "/words")
    shot(page, "faq-05-words-zh")
    link = page.locator('a[href*="/words/"]').first
    if link.count():
        href = link.get_attribute("href")
        if href and "/words/add" not in href:
            gotoload(page, href)
            shot(page, "faq-07-word-detail-zh")

    # ---- review + story ----
    gotoload(page, "/review")
    shot(page, "faq-12-review-zh")
    gotoload(page, "/review/story")
    page.wait_for_timeout(30000)  # AI story generation
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    shot(page, "faq-13-story-zh")

    # ---- write ----
    gotoload(page, "/write")
    shot(page, "faq-14-write-zh")
    gotoload(page, "/write?mode=diary")
    shot(page, "faq-15-diary-zh")

    # ---- square ----
    gotoload(page, "/square")
    shot(page, "faq-16-square-zh")

    # ---- import / sessionpad / stats ----
    gotoload(page, "/intake/import")
    shot(page, "faq-08-import-zh")
    gotoload(page, "/intake/sessionpad/candidates")
    shot(page, "faq-11-sessionpad-zh")
    gotoload(page, "/stats")
    shot(page, "faq-20-stats-zh")

    # ---- partners: create -> recap form -> packets ----
    gotoload(page, "/partners")
    shot(page, "faq-17-partners-zh")
    gotoload(page, "/partners/new")
    pform = page.locator('form:has(input[name="display_name"])')
    pform.locator('input[name="display_name"]').fill("Test Partner")
    nat = pform.locator('select[name="native_language_code"]')
    if nat.count():
        nat.select_option("zh")
    lrn = pform.locator('select[name="learning_language_code"]')
    if lrn.count():
        opts = lrn.locator("option").evaluate_all("els => els.map(e => e.value)")
        if "fr" in opts:
            lrn.select_option("fr")
    pform.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle", timeout=25000)
    print("partner ->", page.url[:80])
    gotoload(page, "/partners")
    link = page.locator('a[href*="/partners/"]').first
    if link.count():
        href = link.get_attribute("href")
        if href and "/new" not in href:
            gotoload(page, f"{href}/recaps/new")
            shot(page, "faq-18-recap-zh")
    gotoload(page, "/partner-packets")
    shot(page, "faq-19-packets-zh")

    # ---- reading: upload crafted PDF, open, click term ----
    pdf = r"D:\home\Rememate\docs\FAQ\scripts\sample-fr.pdf"
    gotoload(page, "/reading/new")
    shot(page, "faq-10-reading-new-zh")
    page.set_input_files('form:has(input[name="file"]) input[name="file"]', pdf)
    lsel = page.locator('form:has(input[name="file"]) select[name="language_code"]').first
    if lsel.count():
        opts = lsel.locator("option").evaluate_all("els => els.map(e => e.value)")
        if "fr" in opts:
            lsel.select_option("fr")
    page.click('form:has(input[name="file"]) button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=30000)
    print("reading doc ->", page.url[:80])
    page.wait_for_timeout(4000)
    term = page.locator("[data-term]").first
    if term.count():
        term.click()
        page.wait_for_timeout(4000)
    shot(page, "faq-10-reading-zh")

    browser.close()
print("DONE")
