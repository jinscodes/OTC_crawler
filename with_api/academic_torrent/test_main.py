"""
Test pipeline — same parallel data collection as main.py, screenshots capped
at SCREENSHOT_LIMIT per subreddit.
"""

import asyncio

from main import load_subreddits, run_pipeline, DECOMPRESS_FILTER_WORKERS, SCREENSHOT_WORKERS

SCREENSHOT_LIMIT = 50


def main() -> None:
    subreddits = load_subreddits()
    print(f"[TEST] Pipeline start — subreddits: {subreddits}")
    print(f"[TEST] Screenshot limit   : {SCREENSHOT_LIMIT}")
    print(f"[TEST] decompress/filter workers : {DECOMPRESS_FILTER_WORKERS}")
    print(f"[TEST] screenshot workers        : {SCREENSHOT_WORKERS}\n")

    asyncio.run(run_pipeline(subreddits, screenshot_limit=SCREENSHOT_LIMIT))
    print("\n[TEST] Pipeline complete.")


if __name__ == "__main__":
    main()
