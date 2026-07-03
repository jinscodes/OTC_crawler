"""
Step 1 — Fast extraction.

Decompress zst/{subreddit}.zst → jsonl/{subreddit}.jsonl, then scan the JSONL and
keep only posts that are (a) inside the date range and (b) mention a target
medicine. This is the cheap, high-volume first pass.

Output (per subreddit): output/without_api/{subreddit}/posts_all.json

Subreddits run in parallel (CPU-bound). A missing .zst is skipped, not fatal.

Run standalone:  python step1_extract.py
"""

import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone

import step0_config as cfg


def decompress(subreddit: str) -> str:
    """
    Decompress zst/{subreddit}.zst → jsonl/{subreddit}.jsonl and return its path.
    Raises FileNotFoundError if the .zst is missing. Reuses an existing non-empty
    .jsonl when cfg.REUSE_JSONL is True.
    """
    import zstandard as zstd  # lazy import so the module loads without it

    zst_path   = os.path.join(cfg.ZST_DIR, f"{subreddit}.zst")
    jsonl_path = os.path.join(cfg.JSONL_DIR, f"{subreddit}.jsonl")

    if cfg.REUSE_JSONL and os.path.exists(jsonl_path) and os.path.getsize(jsonl_path) > 0:
        print(f"[step1] {subreddit}: reusing existing {subreddit}.jsonl")
        return jsonl_path

    if not os.path.exists(zst_path):
        raise FileNotFoundError(f"{zst_path} not found")

    os.makedirs(cfg.JSONL_DIR, exist_ok=True)
    print(f"[step1] {subreddit}.zst → {subreddit}.jsonl ...")
    with open(zst_path, "rb") as compressed, open(jsonl_path, "wb") as destination:
        dctx = zstd.ZstdDecompressor(max_window_size=2 ** 31)
        dctx.copy_stream(compressed, destination)
    size_mb = os.path.getsize(jsonl_path) / 1024 / 1024
    print(f"[step1] Done → {jsonl_path} ({size_mb:.1f} MB)")
    return jsonl_path


def extract_one(subreddit: str) -> dict:
    """
    Decompress + fast-filter one subreddit. Writes posts_all.json, updates the
    summary, and returns this subreddit's stats.
    """
    keywords = cfg.load_keywords()
    medicine_patterns = {
        generic: cfg.build_pattern(synonyms)
        for generic, synonyms in keywords["medicine_terms"].items()
    }
    crawl_ts = cfg.now_iso()

    jsonl_path = decompress(subreddit)
    posts: list[dict] = []
    total = kept = skipped_date = skipped_medicine = 0

    print(f"[step1] r/{subreddit}: scanning {os.path.basename(jsonl_path)} ...")
    with open(jsonl_path, "r", encoding="utf-8") as fin:
        for raw_line in fin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            total += 1

            try:
                post = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            # Date filter
            try:
                created_utc = int(post.get("created_utc", 0))
            except (ValueError, TypeError):
                continue
            if not (cfg.START_TS <= created_utc <= cfg.END_TS):
                skipped_date += 1
                continue

            # Medicine filter (required)
            title = post.get("title", "") or ""
            body  = post.get("selftext", "") or ""
            if body in ("[deleted]", "[removed]"):
                body = ""
            text = f"{title} {body}"

            matched_generic = matched_synonym = None
            for generic, pat in medicine_patterns.items():
                m = pat.search(text)
                if m:
                    matched_generic = generic
                    matched_synonym = m.group()
                    break
            if not matched_generic:
                skipped_medicine += 1
                continue

            post_id        = post.get("id", "")
            subreddit_name = post.get("subreddit", subreddit)
            permalink      = post.get("permalink", "")
            url = (
                post.get("url") or
                (f"https://www.reddit.com{permalink}" if permalink else
                 f"https://www.reddit.com/r/{subreddit_name}/comments/{post_id}/")
            )
            created_time = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()

            posts.append({
                "post_id":                  post_id,
                "subreddit":                subreddit_name,
                "title":                    title,
                "body":                     body,
                "url":                      url,
                "created_time":             created_time,
                "crawl_timestamp":          crawl_ts,
                "matched_medicine":         matched_generic,
                "matched_brand_or_generic": matched_synonym,
            })
            kept += 1

            if total % 100_000 == 0:
                print(f"  [step1] r/{subreddit}: {total:,} scanned / {kept:,} kept")

    cfg.write_json(cfg.step_path(cfg.DIR_STEP1, subreddit), posts)

    stats = {
        "total_scanned":       total,
        "skipped_date":        skipped_date,
        "skipped_no_medicine": skipped_medicine,
        "kept_all":            kept,
    }
    cfg.update_summary(subreddit, "step1_extract", stats)
    print(f"[step1] r/{subreddit}: kept {kept:,} / {total:,}")
    return stats


def run(subreddits: list[str] | None = None) -> None:
    subreddits = subreddits or cfg.load_subreddits()
    print(f"[step1] extract — subreddits: {subreddits} (workers={cfg.WORKERS})")
    with ProcessPoolExecutor(max_workers=cfg.WORKERS) as pool:
        futures = {pool.submit(extract_one, s): s for s in subreddits}
        for future in as_completed(futures):
            subreddit = futures[future]
            try:
                future.result()
            except FileNotFoundError as exc:
                print(f"[SKIP] r/{subreddit}: {exc}")
            except Exception as exc:  # noqa: BLE001
                print(f"[ERROR] r/{subreddit}: {exc}")


if __name__ == "__main__":
    run()
