import json
import math
import os
from datetime import datetime, timezone

from joblib import Parallel, delayed

import step0_config as cfg


def resolve_batch_size(jsonl_path: str) -> int:
    """
    Decide how many posts go in one parallel task for this file.

    If cfg.BATCH_SIZE is a fixed int, use it. If it is "auto", count the file's
    lines (cheap, pure I/O) and size batches so there are about
    cfg.BATCHES_PER_WORKER batches per core — this keeps every core busy
    regardless of how big or small the subreddit is.
    """
    if isinstance(cfg.BATCH_SIZE, int) and cfg.BATCH_SIZE > 0:
        return cfg.BATCH_SIZE

    with open(jsonl_path, "rb") as f:      # ~1.4s for a 6 GB file; no parsing
        n_lines = sum(1 for _ in f)

    workers = cfg.effective_workers()
    target_batches = max(workers, workers * cfg.BATCHES_PER_WORKER)
    return max(1, math.ceil(n_lines / target_batches))


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


def _iter_batches(fin, batch_size: int):
    """Yield lists of up to batch_size non-empty lines from an open file."""
    batch: list[str] = []
    for line in fin:
        line = line.strip()
        if not line:
            continue
        batch.append(line)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def process_batch(lines: list[str], medicine_terms: dict, start_ts: int,
                  end_ts: int, subreddit: str, crawl_ts: str) -> tuple[list[dict], dict]:
    """
    Process one batch of raw JSONL lines (runs inside a joblib worker).
    Applies the date + medicine filters and returns (records, partial_stats).
    Kept module-level and self-contained so it is picklable across processes.
    """
    # Compile patterns once per batch (cheap relative to batch size).
    medicine_patterns = {
        generic: cfg.build_pattern(synonyms)
        for generic, synonyms in medicine_terms.items()
    }

    records: list[dict] = []
    total = len(lines)
    skipped_date = skipped_medicine = 0

    for raw_line in lines:
        try:
            post = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        # Date filter
        try:
            created_utc = int(post.get("created_utc", 0))
        except (ValueError, TypeError):
            continue
        if not (start_ts <= created_utc <= end_ts):
            skipped_date += 1
            continue

        # Medicine filter (required)
        title = post.get("title", "") or ""
        body  = post.get("selftext", "") or ""
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

        records.append({
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

    stats = {
        "total":            total,
        "skipped_date":     skipped_date,
        "skipped_medicine": skipped_medicine,
        "kept":             len(records),
    }
    return records, stats


def extract_one(subreddit: str) -> dict:
    """
    Decompress + parallel fast-filter one subreddit. Writes its posts_all file,
    updates the summary, and returns this subreddit's stats.
    """
    keywords = cfg.load_keywords()
    medicine_terms = keywords["medicine_terms"]
    crawl_ts = cfg.now_iso()

    jsonl_path = decompress(subreddit)
    batch_size = resolve_batch_size(jsonl_path)

    print(f"[step1] r/{subreddit}: processing {os.path.basename(jsonl_path)} "
          f"(n_jobs={cfg.N_JOBS}, batch_size={batch_size:,}) ...")

    # A generator of batches keeps memory bounded; joblib pre-dispatches a few
    # batches at a time rather than materializing the whole file.
    with open(jsonl_path, "r", encoding="utf-8") as fin:
        batches = _iter_batches(fin, batch_size)
        batch_results = Parallel(n_jobs=cfg.N_JOBS)(
            delayed(process_batch)(
                batch, medicine_terms, cfg.START_TS, cfg.END_TS, subreddit, crawl_ts
            )
            for batch in batches
        )

    # Merge batch outputs (order preserved by joblib).
    posts: list[dict] = []
    total = skipped_date = skipped_medicine = kept = 0
    for records, st in batch_results:
        posts.extend(records)
        total            += st["total"]
        skipped_date     += st["skipped_date"]
        skipped_medicine += st["skipped_medicine"]
        kept             += st["kept"]

    cfg.write_json(cfg.step_path(cfg.DIR_STEP1, subreddit), posts)

    stats = {
        "total_scanned":       total,
        "skipped_date":        skipped_date,
        "skipped_no_medicine": skipped_medicine,
        "kept_all":            kept,
        "batch_size":          batch_size,
        "batches":             len(batch_results),
    }
    cfg.update_summary(subreddit, "step1_extract", stats)
    print(f"[step1] r/{subreddit}: kept {kept:,} / {total:,} "
          f"({len(batch_results)} batches)")
    return stats


def run(subreddits: list[str] | None = None) -> None:
    subreddits = subreddits or cfg.load_subreddits()
    print(f"[step1] extract — subreddits: {subreddits} "
          f"(n_jobs={cfg.N_JOBS}, batch_size={cfg.BATCH_SIZE})")
    # Subreddits run sequentially; parallelism happens inside each file so a
    # single large subreddit still saturates all cores.
    for subreddit in subreddits:
        try:
            extract_one(subreddit)
        except FileNotFoundError as exc:
            print(f"[SKIP] r/{subreddit}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] r/{subreddit}: {exc}")


if __name__ == "__main__":
    run()
