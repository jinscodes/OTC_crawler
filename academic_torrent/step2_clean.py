"""
Step 2 — Cleaning.

Read Step 1's posts_all.json and normalize the text so downstream filtering and
LLM annotation see consistent input:
  • drop duplicate post_ids (keep first),
  • strip URLs and markdown link syntax,
  • collapse whitespace/newlines,
  • drop posts with no usable text,
  • add a combined "clean_text" field (title + body, normalized).

Output (per subreddit): output/without_api/{subreddit}/posts_cleaned.json

Run standalone:  python step2_clean.py
"""

import re

import step0_config as cfg

_URL_RE      = re.compile(r"https?://\S+", re.IGNORECASE)
_MD_LINK_RE  = re.compile(r"\[([^\]]+)\]\([^)]+\)")   # [text](url) → text
_WS_RE       = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def clean_one(subreddit: str) -> dict:
    """Clean one subreddit's posts_all.json → posts_cleaned.json. Returns stats."""
    posts = cfg.read_json(cfg.step_path(cfg.DIR_STEP1, subreddit), default=None)
    if posts is None:
        raise FileNotFoundError(f"{cfg.DIR_STEP1}/{subreddit}.json not found")

    cleaned: list[dict] = []
    seen: set[str] = set()
    duplicates = dropped_empty = 0

    for post in posts:
        post_id = post.get("post_id", "")
        if post_id and post_id in seen:
            duplicates += 1
            continue
        if post_id:
            seen.add(post_id)

        title_clean = normalize_text(post.get("title", "") or "")
        body_clean  = normalize_text(post.get("body", "") or "")
        clean_text  = normalize_text(f"{title_clean} {body_clean}")

        if not clean_text:
            dropped_empty += 1
            continue

        record = dict(post)
        record["title_clean"] = title_clean
        record["body_clean"]  = body_clean
        record["clean_text"]  = clean_text
        cleaned.append(record)

    cfg.write_json(cfg.step_path(cfg.DIR_STEP2, subreddit), cleaned)

    stats = {
        "input":         len(posts),
        "duplicates":    duplicates,
        "dropped_empty": dropped_empty,
        "kept":          len(cleaned),
    }
    cfg.update_summary(subreddit, "step2_clean", stats)
    print(f"[step2] r/{subreddit}: cleaned {len(cleaned):,} / {len(posts):,}")
    return stats


def run(subreddits: list[str] | None = None) -> None:
    subreddits = subreddits or cfg.load_subreddits()
    print(f"[step2] clean — subreddits: {subreddits}")
    for subreddit in subreddits:
        try:
            clean_one(subreddit)
        except FileNotFoundError as exc:
            print(f"[SKIP] r/{subreddit}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] r/{subreddit}: {exc}")


if __name__ == "__main__":
    run()
