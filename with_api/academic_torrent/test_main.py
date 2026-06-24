"""
Test pipeline — same data collection as main.py, screenshots capped at 50.
"""

import json
import os

from decompress       import decompress
from filter_jsonl     import filter_and_save
from screenshot_posts import run as take_screenshots

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DETAIL_FILE = os.path.join(BASE_DIR, "detail.json")

SCREENSHOT_LIMIT = 50


def load_subreddits() -> list[str]:
    with open(DETAIL_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("SUBREDDITS", [])


def main() -> None:
    subreddits = load_subreddits()
    print(f"[TEST] Pipeline start — subreddits: {subreddits}")
    print(f"[TEST] Screenshot limit: {SCREENSHOT_LIMIT}\n")

    for subreddit in subreddits:
        print(f"\n{'=' * 60}")
        print(f"  Subreddit: r/{subreddit}")
        print(f"{'=' * 60}")

        # ── Step 1: Decompress ─────────────────────────────────────────────
        try:
            jsonl_path = decompress(subreddit)
        except FileNotFoundError as exc:
            print(f"[STOP] {exc}")
            break

        # ── Step 2: Filter → posts.json ────────────────────────────────────
        posts_path = filter_and_save(subreddit, jsonl_path)

        # ── Step 3: Screenshots (limited) ──────────────────────────────────
        take_screenshots(subreddit, posts_path, limit=SCREENSHOT_LIMIT)

    print("\n[TEST] Pipeline complete.")


if __name__ == "__main__":
    main()
