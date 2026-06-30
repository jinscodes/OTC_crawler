"""
Async screenshot pool.

Browser work is network/IO bound, so it runs on async Playwright with a small
number of reusable pages (headless). Subreddits are fed in as soon as their
posts.json is ready, so screenshotting overlaps with decompress/filter of the
remaining subreddits.

Concurrency = number of worker pages (default 2). Each worker keeps one
persistent page and pulls jobs from a shared queue.
"""

import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_BASE = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "output", "with_api", "academic_torrent"))

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _screenshots_dir(subreddit: str) -> str:
    return os.path.join(OUTPUT_BASE, subreddit, "screenshots")


async def _take_screenshot(page, save_path: str) -> None:
    """Try to screenshot the main post element; fall back to full-page."""
    for sel in ["shreddit-post", "[data-testid='post-container']", "main", ".Post"]:
        el = await page.query_selector(sel)
        if el:
            await el.screenshot(path=save_path)
            return
    await page.screenshot(path=save_path, full_page=True)


class ScreenshotPool:
    """
    Headless async screenshot pool with `num_workers` concurrent pages.

    Usage:
        pool = ScreenshotPool(num_workers=2, limit=None)
        await pool.start()
        await pool.enqueue_posts(subreddit, posts_path)   # call as each finishes
        ...
        await pool.finish()
    """

    def __init__(self, num_workers: int = 2, limit: int | None = None):
        self.num_workers = num_workers
        self.limit       = limit                     # per-subreddit screenshot cap

        self.queue: asyncio.Queue   = asyncio.Queue()
        self.locks                  = defaultdict(asyncio.Lock)   # per posts.json
        self.cache: dict[str, list] = {}             # posts_path -> posts list (shared)

        self._pw      = None
        self.browser  = None
        self.workers: list[asyncio.Task] = []

        self.done   = 0
        self.failed = 0

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(channel="chrome", headless=True)

        for n in range(self.num_workers):
            context = await self.browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=USER_AGENT,
            )
            page = await context.new_page()
            try:
                await page.goto("https://www.reddit.com", wait_until="domcontentloaded")
            except Exception:
                pass
            self.workers.append(asyncio.create_task(self._worker(n + 1, page)))

        print(f"[screenshot] Pool started — {self.num_workers} concurrent page(s), headless")

    async def finish(self) -> None:
        await self.queue.join()
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()
        print(f"\n[screenshot] Pool done — {self.done} screenshot(s), {self.failed} failed")

    # ── producer side ────────────────────────────────────────────────────────
    async def enqueue_posts(self, subreddit: str, posts_path: str) -> None:
        """Load posts.json and queue every post that still needs a screenshot."""
        with open(posts_path, "r", encoding="utf-8") as f:
            posts = json.load(f)
        self.cache[posts_path] = posts

        os.makedirs(_screenshots_dir(subreddit), exist_ok=True)

        pending = [
            i for i, p in enumerate(posts)
            if not p.get("screenshot") and p.get("filter_status") in ("ok", "ok_with_dosing")
        ]
        if self.limit is not None:
            pending = pending[: self.limit]

        print(f"[screenshot] r/{subreddit}: queued {len(pending)} post(s)")
        for idx in pending:
            await self.queue.put((subreddit, posts_path, idx))

    # ── consumer side ────────────────────────────────────────────────────────
    async def _worker(self, wid: int, page) -> None:
        while True:
            subreddit, posts_path, idx = await self.queue.get()
            try:
                await self._process(wid, page, subreddit, posts_path, idx)
            except asyncio.CancelledError:
                self.queue.task_done()
                raise
            except Exception as exc:                              # noqa: BLE001
                self.failed += 1
                print(f"  [w{wid}] [ERROR] {exc}")
            finally:
                self.queue.task_done()

    async def _process(self, wid, page, subreddit, posts_path, idx) -> None:
        posts   = self.cache[posts_path]
        post    = posts[idx]
        url     = post.get("url", "")
        post_id = post.get("post_id", f"idx{idx}")

        if not url:
            print(f"  [w{wid}] SKIP — no URL (post_id={post_id})")
            return

        print(f"  [w{wid}] r/{subreddit} {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
        except PlaywrightTimeoutError:
            self.failed += 1
            print(f"  [w{wid}] [WARN] Timeout — skipping {post_id}")
            return

        ts        = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        save_path = os.path.join(_screenshots_dir(subreddit), f"{post_id}_{ts}.png")
        await _take_screenshot(page, save_path)

        async with self.locks[posts_path]:
            posts[idx]["screenshot"] = save_path
            with open(posts_path, "w", encoding="utf-8") as f:
                json.dump(posts, f, ensure_ascii=False, indent=2)

        self.done += 1
        print(f"  [w{wid}]   → {save_path}")
