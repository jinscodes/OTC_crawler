"""
Parallel pipeline entry point.

Per subreddit the work is still:
  1. decompress   — zst/{subreddit}.zst  →  jsonl/{subreddit}.jsonl
  2. filter       — jsonl/{subreddit}.jsonl → output/.../{subreddit}/posts.json
  3. screenshot   — posts.json URLs  → output/.../{subreddit}/screenshots/

…but the subreddits run concurrently instead of one-after-another:

  • decompress + filter run in a ProcessPoolExecutor (CPU-bound, GIL-safe).
  • As soon as a subreddit's posts.json is ready it is fed to an async,
    headless Playwright screenshot pool, so screenshotting overlaps with the
    decompress/filter of the remaining subreddits.

Concurrency (conservative defaults):
  DECOMPRESS_FILTER_WORKERS = 2   # processes
  SCREENSHOT_WORKERS        = 2   # concurrent headless pages

Note: unlike the old serial version, a missing .zst no longer stops the whole
run — that subreddit is skipped and the others continue.
"""

import asyncio
import json
import os
from concurrent.futures import ProcessPoolExecutor

from worker import decompress_and_filter
from screenshot_async import ScreenshotPool

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DETAIL_FILE = os.path.join(BASE_DIR, "detail.json")

DECOMPRESS_FILTER_WORKERS = 2
SCREENSHOT_WORKERS        = 2


def load_subreddits() -> list[str]:
    with open(DETAIL_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("SUBREDDITS", [])


async def run_pipeline(subreddits: list[str], screenshot_limit: int | None = None) -> None:
    loop = asyncio.get_running_loop()
    pool = ProcessPoolExecutor(max_workers=DECOMPRESS_FILTER_WORKERS)
    shots = ScreenshotPool(num_workers=SCREENSHOT_WORKERS, limit=screenshot_limit)
    await shots.start()

    async def decompress_filter_then_queue(subreddit: str) -> None:
        print(f"[pipeline] r/{subreddit}: decompress + filter …")
        try:
            posts_path = await loop.run_in_executor(pool, decompress_and_filter, subreddit)
        except FileNotFoundError as exc:
            print(f"[SKIP] r/{subreddit}: {exc}")
            return
        except Exception as exc:                                    # noqa: BLE001
            print(f"[ERROR] r/{subreddit}: {exc}")
            return
        await shots.enqueue_posts(subreddit, posts_path)

    try:
        # decompress+filter for all subreddits run concurrently (capped by the
        # process pool); screenshots stream in as each finishes.
        await asyncio.gather(*(decompress_filter_then_queue(s) for s in subreddits))
        await shots.finish()
    finally:
        pool.shutdown(wait=True)


def main() -> None:
    subreddits = load_subreddits()
    print(f"Pipeline start — subreddits: {subreddits}")
    print(f"  decompress/filter workers : {DECOMPRESS_FILTER_WORKERS}")
    print(f"  screenshot workers        : {SCREENSHOT_WORKERS}\n")

    asyncio.run(run_pipeline(subreddits))
    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
