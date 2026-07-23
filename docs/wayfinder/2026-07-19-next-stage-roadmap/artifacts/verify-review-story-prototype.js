const { chromium } = require("playwright");
const { pathToFileURL } = require("url");
const path = require("path");
const fs = require("fs");

const prototypePath = path.resolve(__dirname, "review-story-experience.html");
const screenshotDir = path.resolve(__dirname, "review-story-screenshots");
fs.mkdirSync(screenshotDir, { recursive: true });

async function inspect(page, name) {
  const metrics = await page.evaluate(() => {
    const switcher = document.querySelector(".prototype-switcher").getBoundingClientRect();
    const mobileNavElement = document.querySelector(".mobile-nav");
    const mobileNav = getComputedStyle(mobileNavElement).display === "none"
      ? null
      : mobileNavElement.getBoundingClientRect();
    const visible = [...document.querySelectorAll("body *")].filter((element) => {
      const style = getComputedStyle(element);
      return style.display !== "none" && style.visibility !== "hidden";
    });
    const overflow = visible
      .filter((element) => element.scrollWidth > element.clientWidth + 2)
      .map((element) => ({
        tag: element.tagName,
        className: element.className,
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth
      }))
      .slice(0, 10);
    return {
      viewport: { width: innerWidth, height: innerHeight },
      bodyScrollWidth: document.body.scrollWidth,
      switcher: {
        top: switcher.top,
        bottom: switcher.bottom
      },
      mobileNav: mobileNav && {
        top: mobileNav.top,
        bottom: mobileNav.bottom
      },
      switcherOverlapsMobileNav: Boolean(mobileNav && switcher.bottom > mobileNav.top),
      overflow
    };
  });
  await page.screenshot({
    path: path.join(screenshotDir, `${name}.png`),
    fullPage: true
  });
  return { name, ...metrics };
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
  });
  const results = [];
  try {
    const desktop = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    for (const [variant, state] of [
      ["A", "normal"],
      ["B", "strong"],
      ["C", "ready"]
    ]) {
      const url = new URL(pathToFileURL(prototypePath));
      url.searchParams.set("variant", variant);
      url.searchParams.set("state", state);
      await desktop.goto(url.href);
      results.push(await inspect(desktop, `desktop-${variant}-${state}`));
    }

    const mobile = await browser.newPage({
      viewport: { width: 390, height: 844 },
      isMobile: true
    });
    for (const [variant, state] of [
      ["A", "strong"],
      ["B", "error"],
      ["C", "ready"]
    ]) {
      const url = new URL(pathToFileURL(prototypePath));
      url.searchParams.set("variant", variant);
      url.searchParams.set("state", state);
      await mobile.goto(url.href);
      results.push(await inspect(mobile, `mobile-${variant}-${state}`));
    }

    const interactive = new URL(pathToFileURL(prototypePath));
    interactive.searchParams.set("variant", "C");
    interactive.searchParams.set("state", "normal");
    await mobile.goto(interactive.href);
    await mobile.getByRole("button", { name: "生成故事" }).click();
    await mobile.waitForTimeout(1100);
    const params = new URL(mobile.url()).searchParams;
    results.push({
      name: "interaction-generate",
      finalState: params.get("state"),
      hasStory: await mobile.getByText("Le quai sous la pluie").isVisible()
    });
  } finally {
    await browser.close();
  }

  const failed = results.some((result) =>
    result.bodyScrollWidth > result.viewport?.width ||
    result.switcherOverlapsMobileNav ||
    (result.overflow && result.overflow.length > 0) ||
    result.finalState && (result.finalState !== "ready" || !result.hasStory)
  );
  console.log(JSON.stringify({ failed, results }, null, 2));
  process.exitCode = failed ? 1 : 0;
})();


