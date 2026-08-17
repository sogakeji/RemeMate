"""Capture RemeMate staging screenshots for the FAQ doc — v3.
Fixes: zh UI enforcement, real quick-add flow, commit candidates, review+story,
partner+recap, PDF reading with a validated PDF, per-page text dump.
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
    print(f"SHOT {name} | {page.url[:75]}\n    text: {txt}")

def gotoload(page, path):
    page.goto(f"{BASE}{path}", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(locale="zh-CN", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    # ---- public ----
    gotoload(page, "/")
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

    # force zh UI (the account may have been toggled to en earlier)
    if page.locator("html").get_attribute("lang", timeout=3000) == "en":
        page.locator("form.ui-locale-form button[type='submit']").click()
        page.wait_for_load_state("networkidle", timeout=20000)
        print("UI switched to zh ->", page.url[:60])

    gotoload(page, "/")
    shot(page, "faq-00-home-task-zh")
    gotoload(page, "/settings")
    shot(page, "faq-04-settings-zh")
    toggle = page.locator('button[data-settings-toggle="learning-panel"]')
    if toggle.count():
        toggle.click()
        page.wait_for_timeout(500)
        page.check('input[name="languages"][value="fr"]')
        page.locator('#learning-panel button[type="submit"]').click()
        page.wait_for_load_state("networkidle", timeout=25000)
    gotoload(page, "/words/add")
    shot(page, "faq-06-add-word-zh")

    # ---- quick-add 3 words, remember first source for faq-11 ----
    first_candidates = None
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
        if first_candidates is None:
            first_candidates = page.url.replace(BASE, "")
        print("quick-add", w, "->", page.url.replace(BASE, ""))

    # candidates page (last source) + commit
    path = page.url.replace(BASE, "")
    gotoload(page, path)
    shot(page, "faq-09-candidates-zh")
    commit_btn = page.locator('form[action*="commit"] button[type="submit"]').first
    if commit_btn.count():
        commit_btn.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        print("committed ->", page.url.replace(BASE, "")[:60])
    else:
        print("no commit button")

    # sessionpad shot: use first source's candidates page (valid page)
    if first_candidates:
        gotoload(page, first_candidates)
        shot(page, "faq-11-sessionpad-candidates-zh")

    # ---- words list + detail ----
    gotoload(page, "/words")
    shot(page, "faq-05-word-list-zh")
    link = page.locator('a[href*="/words/"]').first
    if link.count():
        href = link.get_attribute("href")
        if href and "/words/add" not in href:
            gotoload(page, href)
            shot(page, "faq-07-word-detail-zh")

    # ---- review: grade all due cards ----
    gotoload(page, "/review")
    shot(page, "faq-12-review-zh")
    for _ in range(6):
        grade = page.locator("button.srs-btn").first
        if grade.count():
            grade.click()
            page.wait_for_timeout(2500)
        else:
            break
    page.wait_for_timeout(2000)

    # ---- story ----
    gotoload(page, "/review")
    page.wait_for_timeout(2000)
    receipt = page.locator("#review-story-receipt")
    if receipt.count():
        gen = receipt.locator('button[type="submit"]').first
        if gen.count():
            gen.click()
            page.wait_for_timeout(30000)  # AI generation
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
    gotoload(page, "/square")
    shot(page, "faq-16-square-zh")
    gotoload(page, "/intake/import")
    shot(page, "faq-08-import-zh")
    gotoload(page, "/stats")
    shot(page, "faq-20-stats-zh")

    # ---- partners ----
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
    print("partner ->", page.url.replace(BASE, "")[:60])

    gotoload(page, "/partners")
    plinks = page.locator('a[href*="/partners/"]').all()
    detail = None
    import re
    for a in plinks:
        h = a.get_attribute("href") or ""
        if re.fullmatch(r"/partners/\d+", h):
            detail = h
            break
    if detail:
        gotoload(page, f"{detail}/recaps/new")
        shot(page, "faq-18-recap-zh")
    gotoload(page, "/partner-packets")
    shot(page, "faq-19-packets-zh")

    # ---- reading: upload PDF, open, click term ----
    gotoload(page, "/reading/new")
    shot(page, "faq-10-reading-new-zh")
    page.set_input_files('form:has(input[name="file"]) input[name="file"]',
                         r"D:\home\Rememate\docs\FAQ\scripts\sample-fr.pdf")
    lsel = page.locator('form:has(input[name="file"]) select[name="language_code"]').first
    if lsel.count():
        opts = lsel.locator("option").evaluate_all("els => els.map(e => e.value)")
        if "fr" in opts:
            lsel.select_option("fr")
    page.click('form:has(input[name="file"]) button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=30000)
    print("reading doc ->", page.url.replace(BASE, "")[:70])
    page.wait_for_timeout(4000)
    term = page.locator("[data-term]").first
    if term.count():
        term.click()
        page.wait_for_timeout(4000)
    shot(page, "faq-10-reading-zh")

    browser.close()
print("DONE")
