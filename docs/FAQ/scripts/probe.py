"""Probe RemeMate staging UI flows (login, add word, settings) via playwright."""
import re, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8892"
EMAIL = "faq-test@example.com"
PASSWORD = "I0q31zFouYjztnL9"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(locale="zh-CN", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(f"{BASE}/login", timeout=30000)
    page.wait_for_load_state("networkidle")
    print("LOGIN PAGE TITLE:", page.title())
    inputs = page.locator("input").evaluate_all("els => els.map(e => e.name || e.id)")
    print("LOGIN INPUTS:", inputs)

    # login
    page.fill('input[name="email"]', EMAIL)
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"], input[type="submit"]')
    page.wait_for_load_state("networkidle")
    print("AFTER LOGIN URL:", page.url)
    print("AFTER LOGIN TITLE:", page.title())

    # home
    page.goto(f"{BASE}/", timeout=30000)
    page.wait_for_load_state("networkidle")
    print("HOME TITLE:", page.title())
    body = page.inner_text("body")[:400]
    print("HOME TEXT:", body.replace("\n", " | ")[:400])

    # words add form fields
    page.goto(f"{BASE}/words/add", timeout=30000)
    page.wait_for_load_state("networkidle")
    print("ADD URL:", page.url)
    print("ADD TITLE:", page.title())
    add_inputs = page.locator("input, select, textarea").evaluate_all(
        "els => els.map(e => (e.name || e.id) + ':' + (e.tagName))")
    print("ADD FIELDS:", add_inputs)
    print("ADD TEXT:", page.inner_text("body")[:500].replace("\n", " | "))

    # settings languages
    page.goto(f"{BASE}/settings", timeout=30000)
    page.wait_for_load_state("networkidle")
    print("SETTINGS TITLE:", page.title())
    print("SETTINGS TEXT:", page.inner_text("body")[:600].replace("\n", " | "))
    browser.close()
