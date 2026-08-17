"""Capture English-UI screenshots for the FAQ doc (data already seeded).
Also captures the register page (registration temporarily enabled on staging).
"""
import re, time
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
    txt = page.inner_text("body")[:130].replace("\n", " | ")
    print(f"SHOT {name}\n    text: {txt}")

def gotoload(page, path):
    page.goto(f"{BASE}{path}", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(locale="en-US", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    # ---- public pages (logged out) in EN ----
    gotoload(page, "/")
    en_toggle = page.locator("a,button,span").filter(has_text="EN").first
    if en_toggle.count():
        en_toggle.click()
        page.wait_for_timeout(1200)
    shot(page, "faq-01-landing-en")
    gotoload(page, "/login")
    shot(page, "faq-02-login-en")
    gotoload(page, "/register")
    shot(page, "faq-03-register-en")

    # zh register (same page, switch UI to zh via the header form)
    zh_switch = page.locator("form.ui-locale-form button[type='submit']")
    if zh_switch.count():
        zh_switch.click()
        page.wait_for_load_state("networkidle", timeout=20000)
        page.wait_for_timeout(1000)
    shot(page, "faq-03-register-zh")

    # ---- login ----
    gotoload(page, "/login")
    page.fill('form:has(input[name="email"]) input[name="email"]', EMAIL)
    page.fill('form:has(input[name="email"]) input[name="password"]', PASSWORD)
    page.click('form:has(input[name="email"]) button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=25000)
    print("LOGIN ->", page.url)
    assert "/login" not in page.url

    # switch UI to EN
    if page.locator("html").get_attribute("lang", timeout=3000) != "en":
        page.locator("form.ui-locale-form button[type='submit']").click()
        page.wait_for_load_state("networkidle", timeout=20000)
    print("UI:", page.locator("html").get_attribute("lang"))

    gotoload(page, "/")
    shot(page, "faq-00-home-task-en")
    gotoload(page, "/settings")
    shot(page, "faq-04-settings-language-en")
    gotoload(page, "/words/add")
    shot(page, "faq-06-add-word-en")
    gotoload(page, "/words")
    shot(page, "faq-05-word-list-en")
    for a in page.locator('a[href*="/words/"]').all():
        h = a.get_attribute("href") or ""
        if re.fullmatch(r"/words/\d+", h):
            gotoload(page, h)
            shot(page, "faq-07-word-detail-en")
            break
    gotoload(page, "/intake/import")
    shot(page, "faq-08-import-en")
    gotoload(page, "/intake/1122/candidates")
    shot(page, "faq-09-candidates-en")
    gotoload(page, "/intake/1120/candidates")
    shot(page, "faq-11-sessionpad-candidates-en")

    # review + story (cached from earlier)
    gotoload(page, "/review")
    shot(page, "faq-12-review-en")
    page.wait_for_timeout(2000)
    receipt = page.locator("#review-story-receipt")
    if receipt.count():
        gen = receipt.locator('button[type="submit"]').first
        if gen.count():
            gen.click()
            page.wait_for_timeout(30000)
    gotoload(page, "/review")
    page.wait_for_timeout(2000)
    shot(page, "faq-13-story-en")

    gotoload(page, "/write")
    shot(page, "faq-14-write-en")
    gotoload(page, "/write?mode=diary")
    shot(page, "faq-15-diary-en")
    gotoload(page, "/square")
    shot(page, "faq-16-square-en")
    gotoload(page, "/stats")
    shot(page, "faq-20-stats-en")

    # partners
    gotoload(page, "/partners")
    shot(page, "faq-17-partners-en")
    gotoload(page, "/partners/990/recaps/new")
    shot(page, "faq-18-recap-en")
    gotoload(page, "/partner-packets")
    shot(page, "faq-19-packets-en")

    # reading: open existing doc
    gotoload(page, "/reading/new")
    shot(page, "faq-10-reading-new-en")
    gotoload(page, "/reading/964")
    page.wait_for_timeout(3000)
    term = page.locator("[data-term]").first
    if term.count():
        term.click()
        page.wait_for_timeout(4000)
    shot(page, "faq-10-reading-en")

    browser.close()
print("DONE")
