"""
Pipeline entry point.

Execution order per subreddit:
  1. decompress   — {subreddit}.zst  →  {subreddit}.jsonl
  2. filter       — {subreddit}.jsonl → output/with_api/pushshift/{subreddit}/posts.json
  3. screenshot   — posts.json URLs  → output/with_api/pushshift/{subreddit}/screenshots/

Stops immediately if a .zst file is missing for the current subreddit.
"""

import json
import os

from decompress      import decompress
from filter_jsonl    import filter_and_save
from screenshot_posts import run as take_screenshots

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DETAIL_FILE = os.path.join(BASE_DIR, "detail.json")


def load_subreddits() -> list[str]:
    with open(DETAIL_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("SUBREDDITS", [])


def main() -> None:
    subreddits = load_subreddits()
    print(f"Pipeline start — subreddits: {subreddits}\n")

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

        # ── Step 3: Screenshots ────────────────────────────────────────────
        take_screenshots(subreddit, posts_path)

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
