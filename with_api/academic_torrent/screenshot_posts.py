import os
import json
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_BASE = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "output", "with_api", "academic_torrent"))


# ── helpers ────────────────────────────────────────────────────────────────────

def _posts_path(subreddit: str) -> str:
    return os.path.join(OUTPUT_BASE, subreddit, "posts.json")


def _screenshots_dir(subreddit: str) -> str:
    return os.path.join(OUTPUT_BASE, subreddit, "screenshots")


def _load_posts(posts_file: str) -> list[dict]:
    with open(posts_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_posts(posts: list[dict], posts_file: str) -> None:
    with open(posts_file, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def _take_screenshot(page, save_path: str) -> None:
    """Try to screenshot the main post element; fall back to full-page."""
    for sel in ["shreddit-post", "[data-testid='post-container']", "main", ".Post"]:
        el = page.query_selector(sel)
        if el:
            el.screenshot(path=save_path)
            return
    page.screenshot(path=save_path, full_page=True)


# ── main ───────────────────────────────────────────────────────────────────────

def run(subreddit: str, posts_file: str | None = None, limit: int | None = None) -> None:
    """
    Take screenshots for posts in posts_file that have an empty 'screenshot' field.

    Args:
        subreddit:  Subreddit name (used to resolve default output paths).
        posts_file: Path to posts.json. Defaults to the pushshift output path for
                    the given subreddit.
        limit:      Maximum number of screenshots to take. None = no limit.
    """
    if posts_file is None:
        posts_file = _posts_path(subreddit)

    screenshots_dir = _screenshots_dir(subreddit)
    os.makedirs(screenshots_dir, exist_ok=True)

    posts = _load_posts(posts_file)
    total = len(posts)
    print(f"\n[screenshot] Loaded {total} posts from {posts_file}")

    pending = [
        i for i, p in enumerate(posts)
        if not p.get("screenshot") and p.get("filter_status") in ("ok", "ok_with_dosing")
    ]
    if limit is not None:
        pending = pending[:limit]
    print(f"[screenshot] {len(pending)} post(s) need screenshots (ok / ok_with_dosing only)")

    if not pending:
        print("[screenshot] All posts already have screenshots.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            slow_mo=300,
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

        print("[screenshot] Opening Reddit …")
        page.goto("https://www.reddit.com", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        for order, idx in enumerate(pending, start=1):
            post    = posts[idx]
            url     = post.get("url", "")
            post_id = post.get("post_id", f"idx{idx}")

            if not url:
                print(f"  [{order}/{len(pending)}] SKIP — no URL (post_id={post_id})")
                continue

            print(f"  [{order}/{len(pending)}] {url}")

            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)

                ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(screenshots_dir, f"{post_id}_{ts}.png")

                _take_screenshot(page, save_path)
                posts[idx]["screenshot"] = save_path
                print(f"    → {save_path}")

                # Persist after every screenshot so progress survives interruptions
                _save_posts(posts, posts_file)

            except PlaywrightTimeoutError:
                print(f"    [WARN] Timeout — skipping {post_id}")
            except Exception as exc:
                print(f"    [ERROR] {exc}")

        browser.close()

    done = sum(1 for p in posts if p.get("screenshot"))
    print(f"\n[screenshot] Done — {done}/{total} posts have screenshots.")
    print(f"             Screenshots → {screenshots_dir}")
    print(f"             Updated JSON → {posts_file}")


if __name__ == "__main__":
    import json as _json

    _detail_file = os.path.join(BASE_DIR, "detail.json")
    with open(_detail_file, "r", encoding="utf-8") as _f:
        _subreddits: list[str] = _json.load(_f).get("SUBREDDITS", [])

    for _sr in _subreddits:
        run(_sr)
