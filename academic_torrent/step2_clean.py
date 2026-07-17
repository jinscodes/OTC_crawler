import re

from joblib import Parallel, delayed

import step0_config as cfg

_URL_RE      = re.compile(r"https?://\S+", re.IGNORECASE)
_MD_LINK_RE  = re.compile(r"\[([^\]]+)\]\([^)]+\)")   # [text](url) → text
_WS_RE       = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def normalize_batch(posts: list[dict]) -> list[dict]:
    """
    Add title_clean / body_clean / clean_text to each post (runs in a worker).
    This is the CPU-heavy part; dedup and empty-drop are done afterwards, in
    order, so global state stays correct.
    """
    out = []
    for post in posts:
        record = dict(post)
        record["title_clean"] = normalize_text(post.get("title", "") or "")
        record["body_clean"]  = normalize_text(post.get("body", "") or "")
        record["clean_text"]  = normalize_text(
            f"{record['title_clean']} {record['body_clean']}"
        )
        out.append(record)
    return out


def clean_one(subreddit: str) -> dict:
    """Clean one subreddit's posts_all → posts_cleaned. Returns stats."""
    posts = cfg.read_json(cfg.step_path(cfg.DIR_STEP1, subreddit), default=None)
    if posts is None:
        raise FileNotFoundError(f"{cfg.DIR_STEP1}/{subreddit}.json not found")

    # Parallelize the heavy text normalization (order preserved); fall back to
    # serial for small inputs where worker overhead would dominate.
    if len(posts) < cfg.MIN_PARALLEL_ROWS:
        normalized = normalize_batch(posts)
    else:
        batch_size = cfg.batch_size_for(len(posts))
        batches = Parallel(n_jobs=cfg.N_JOBS)(
            delayed(normalize_batch)(chunk) for chunk in cfg.chunked(posts, batch_size)
        )
        normalized = [rec for batch in batches for rec in batch]

    # Serial post-pass: dedup by post_id (keep first) and drop empty text.
    cleaned: list[dict] = []
    seen: set[str] = set()
    duplicates = dropped_empty = 0
    for record in normalized:
        post_id = record.get("post_id", "")
        if post_id and post_id in seen:
            duplicates += 1
            continue
        if post_id:
            seen.add(post_id)
        if not record["clean_text"]:
            dropped_empty += 1
            continue
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
