"""Capture the review-story flow: add 10+ words, commit, review them, generate story."""
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8892"
EMAIL = "faq-test@example.com"
PASSWORD = "XrcOnph4rmpLw5oD"
OUT = r"D:\home\Rememate\docs\FAQ\images"
WORDS = [
    ("s'il vous plaît", "请"),
    ("merci", "谢谢"),
    ("maintenant", "现在"),
    ("demain", "明天"),
    ("aujourd'hui", "今天"),
    ("la ville", "城市"),
    ("l'école", "学校"),
    ("le travail", "工作"),
    ("la famille", "家庭"),
    ("les amis", "朋友们"),
]

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

    page.goto(f"{BASE}/login", timeout=30000)
    page.fill('form:has(input[name="email"]) input[name="email"]', EMAIL)
    page.fill('form:has(input[name="email"]) input[name="password"]', PASSWORD)
    page.click('form:has(input[name="email"]) button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=25000)
    print("LOGIN ->", page.url)
    assert "/login" not in page.url, "login failed"
    if page.locator("html").get_attribute("lang", timeout=3000) == "en":
        page.locator("form.ui-locale-form button[type='submit']").click()
        page.wait_for_load_state("networkidle", timeout=20000)

    # add + commit 10 words
    added = 0
    for w, m in WORDS:
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
        commit_btn = page.locator('form[action*="commit"] button[type="submit"]').first
        if commit_btn.count():
            commit_btn.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            added += 1
            print("added+committed:", w)
        else:
            print("commit btn missing for", w)

    # words list
    gotoload(page, "/words")
    shot(page, "faq-05-word-list-zh")

    # review all due cards
    gotoload(page, "/review")
    for i in range(20):
        grade = page.locator("button.srs-btn").first
        if grade.count():
            grade.click()
            page.wait_for_timeout(2500)
        else:
            break
    page.wait_for_timeout(1500)
    shot(page, "faq-12-review-zh")

    # story: reload, generate, wait
    gotoload(page, "/review")
    page.wait_for_timeout(2000)
    receipt = page.locator("#review-story-receipt")
    if receipt.count():
        gen = receipt.locator('button[type="submit"]').first
        if gen.count():
            gen.click()
            page.wait_for_timeout(45000)  # AI story generation
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
    shot(page, "faq-13-story-zh")

    browser.close()
print("DONE")
