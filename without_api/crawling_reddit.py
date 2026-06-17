import os
import json
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 1 variables
TRIAL_INDEX = 9
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(_BASE, "output", "without_api", str(TRIAL_INDEX))
SCREENSHOTS_DIR = os.path.join(OUTPUT_DIR, "screenshots")
DATA_FILE = os.path.join(OUTPUT_DIR, "posts.json")
DETAIL_FILE = os.path.join(os.path.dirname(__file__), "detail.json")


# 1 function
def setup_dirs() -> None:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# 2 function
def load_detail() -> tuple[list[str], dict, list[str], list[str]]:
    try:
        with open(DETAIL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("SUBREDDITS", []),
            data.get("MEDICINE_TERMS", {}),
            data.get("DOSING_TERMS", []),
            data.get("EXCLUDE_TERMS", []),
        )
    except Exception as exc:
        print(f"[WARN] Could not load detail.json: {exc}")
        return [], {}, [], []

def build_search_query(medicine_terms: dict) -> str:
    all_synonyms = []
    for synonyms in medicine_terms.values():
        all_synonyms.extend(synonyms)
    return " OR ".join(all_synonyms)

def detect_medicines(text: str, medicine_terms: dict) -> list[str]:
    text_lower = text.lower()
    found = []
    for medicine, synonyms in medicine_terms.items():
        if any(s.lower() in text_lower for s in synonyms):
            found.append(medicine)
    return found

def compute_relevance(text: str, medicine_terms: dict, dosing_terms: list[str]) -> int:
    text_lower = text.lower()
    has_medicine = any(
        s.lower() in text_lower
        for synonyms in medicine_terms.values()
        for s in synonyms
    )
    has_dosing = any(t.lower() in text_lower for t in dosing_terms)
    return 1 if (has_medicine and has_dosing) else 0

def is_excluded(text: str, exclude_terms: list[str]) -> list[str]:
    text_lower = text.lower()
    return [t for t in exclude_terms if t.lower() in text_lower]



# 3 function
def safe_text(page, selector: str, default: str = "") -> str:
    try:
        el = page.query_selector(selector)
        return el.inner_text().strip() if el else default
    except Exception:
        return default

# 4 function
def collect_post_links(page, url: str, seen: set, subreddit: str = "") -> list[str]:
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    try:
        page.wait_for_selector("a[href*='/comments/']", timeout=3000)
    except Exception:
        return []
    raw_links = page.eval_on_selector_all(
        "a[href*='/comments/']",
        "els => els.map(e => e.href)",
    )
    new_links = []
    sr_filter = f"/r/{subreddit.lower()}/" if subreddit else ""
    for href in raw_links:
        clean = href.split("?")[0].rstrip("/")
        if clean not in seen and clean.count("/comments/") == 1:
            if sr_filter and sr_filter not in clean.lower():
                continue
            seen.add(clean)
            new_links.append(clean)
    return new_links

# 5 function
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


def parse_subreddit(url: str) -> str:
    parts = url.split("/")
    try:
        r_idx = parts.index("r")
        return parts[r_idx + 1]
    except (ValueError, IndexError):
        return ""

# 6 function
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

        subreddits, medicine_terms, dosing_terms, exclude_terms = load_detail()
        seen: set = set()
        post_links: list[str] = []

        # [2] Search per subreddit per medicine
        if subreddits and medicine_terms:
            print(f"[2] Searching {len(subreddits)} subreddit(s) × {len(medicine_terms)} medicine(s) …")
            for sr in subreddits:
                print(f"\n  /r/{sr}")
                for medicine, synonyms in medicine_terms.items():
                    encoded_query = " OR ".join(synonyms).replace(' ', '+').replace('&', '%26')
                    sr_url = (
                        f"https://www.reddit.com/r/{sr}/search/"
                        f"?q={encoded_query}&restrict_sr=1&type=link&t=month"
                    )
                    print(f"    [{medicine}] …")
                    links = collect_post_links(page, sr_url, seen, subreddit=sr)
                    post_links.extend(links)
                    print(f"      → {len(links)} new post(s)")
        else:
            print("[2] No subreddits or medicine terms found in detail.json, skipping.")

        print(f"\n[3] Visiting {len(post_links)} posts …")

        save_idx = 0
        for idx, link in enumerate(post_links, start=1):
            print(f"\n[Post {idx}/{len(post_links)}] {link}")

            try:
                page.goto(link, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)

                data = extract_post_content(page)
                text = data["title"] + " " + data["body"]

                matched = is_excluded(text, exclude_terms)
                if matched:
                    print(f"    [SKIP] Excluded term(s) matched: {matched}")
                    continue

                data["subreddit"] = parse_subreddit(link)

                if subreddits and data["subreddit"].lower() not in [s.lower() for s in subreddits]:
                    print(f"    [SKIP] r/{data['subreddit']} not in allowed subreddits — skipping post.")
                    continue

                data["medicines"] = detect_medicines(text, medicine_terms)

                if not data["medicines"]:
                    print(f"    [SKIP] No medicine terms detected — skipping post.")
                    continue

                data["relevance"] = compute_relevance(text, medicine_terms, dosing_terms)
                save_idx += 1
                data["index"] = save_idx
                data["timestamp"] = datetime.now().isoformat()

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(
                    SCREENSHOTS_DIR, f"post_{save_idx:03d}_{ts}.png"
                )

                # Try to screenshot just the main content column (no sidebars)
                content_selectors = [
                    "shreddit-post",
                    "[data-testid='post-container']",
                    "main",
                    ".Post",
                ]
                captured = False
                for sel in content_selectors:
                    el = page.query_selector(sel)
                    if el:
                        el.screenshot(path=screenshot_path)
                        captured = True
                        break
                if not captured:
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
