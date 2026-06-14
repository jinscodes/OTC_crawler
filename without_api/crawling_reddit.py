import os
import json
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 1 variables
SEARCH_QUERY = "Tylenol & Ibuprofen intake"
OUTPUT_DIR = "output/without_api"
SCREENSHOTS_DIR = os.path.join(OUTPUT_DIR, "screenshots")
DATA_FILE = os.path.join(OUTPUT_DIR, "posts.json")


# 1 function
def setup_dirs() -> None:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# 2 function
def safe_text(page, selector: str, default: str = "") -> str:
    try:
        el = page.query_selector(selector)
        return el.inner_text().strip() if el else default
    except Exception:
        return default

# 3 function
def extract_post_content(page) -> dict:
    title = ""
    for sel in [
        "h1[slot='title']",
        "h1",
        "[data-testid='post-title']",
        "shreddit-post [slot='title']",
    ]:
        title = safe_text(page, sel)
        if title:
            break

    body = ""
    for sel in [
        "[slot='text-body']",
        "[data-click-id='text'] div",
        ".md",
        "[data-testid='post-content'] p",
        "div[class*='usertext-body']",
    ]:
        body = safe_text(page, sel)
        if body:
            break

    return {"title": title, "body": body, "url": page.url}

# 4 function
def run() -> None:
    setup_dirs()
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            slow_mo=500,
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()

        print("[1] Opening Reddit …")
        page.goto("https://www.reddit.com", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        print(f"[2] Searching for: {SEARCH_QUERY!r} …")
        search_url = (
            "https://www.reddit.com/search/"
            f"?q={SEARCH_QUERY.replace(' ', '+').replace('&', '%26')}"
            "&type=link"
        )
        page.goto(search_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        print("[3] Applying 'Today' filter …")
        today_url = search_url + "&t=day"
        page.goto(today_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        print("[4] Collecting post links …")
        page.wait_for_selector("a[href*='/comments/']", timeout=15000)

        raw_links = page.eval_on_selector_all(
            "a[href*='/comments/']",
            "els => els.map(e => e.href)",
        )

        seen: set = set()
        post_links: list[str] = []

        for href in raw_links:
            clean = href.split("?")[0].rstrip("/")
            if clean not in seen and clean.count("/comments/") == 1:
                seen.add(clean)
                post_links.append(clean)

        print(f"    Found {len(post_links)} posts.")

        for idx, link in enumerate(post_links, start=1):
            print(f"\n[Post {idx}/{len(post_links)}] {link}")

            try:
                page.goto(link, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)

                data = extract_post_content(page)
                data["index"] = idx
                data["timestamp"] = datetime.now().isoformat()

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(
                    SCREENSHOTS_DIR, f"post_{idx:03d}_{ts}.png"
                )
                page.screenshot(path=screenshot_path, full_page=True)

                data["screenshot"] = screenshot_path
                results.append(data)

                print(f"    Title   : {data['title'][:80]}")
                print(f"    Body    : {data['body'][:120].replace(chr(10), ' ')}")
                print(f"    Screenshot saved → {screenshot_path}")

            except PlaywrightTimeoutError:
                print(f"    [WARN] Timeout on post {idx}, skipping.")
            except Exception as exc:
                print(f"    [ERROR] {exc}")

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n[Done] Saved {len(results)} posts → {DATA_FILE}")
        browser.close()


if __name__ == "__main__":
    run()
