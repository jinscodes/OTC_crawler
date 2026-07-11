"""
Test harness — collect a small sample per subreddit and run steps 1–3.

For a quick end-to-end check it grabs up to SAMPLE_SIZE posts per subreddit (the
first ones passing the date + medicine filter), then runs cleaning and filtering.
Everything is written under output/test/ so the real output/ is untouched:

    output/test/step1/{subreddit}.json     # sampled posts_all
    output/test/step2/{subreddit}.json     # cleaned
    output/test/step3/{subreddit}.json     # candidates
    output/test/summary/{subreddit}.json   # per-step stats

Run:  python test_collect.py
"""

import os

import step0_config as cfg
import step1_extract as s1
import step2_clean as s2
import step3_filter as s3

SAMPLE_SIZE = 50          # posts collected per subreddit
SCAN_CHUNK  = 1000        # lines read per streaming step while sampling

# Redirect all outputs to output/test/ with numbered step folders.
cfg.OUTPUT_BASE = os.path.join(cfg.OUTPUT_BASE, "test")
cfg.DIR_STEP1   = "step1"
cfg.DIR_STEP2   = "step2"
cfg.DIR_STEP3   = "step3"
cfg.DIR_SUMMARY = "summary"


def sample_extract(subreddit: str, limit: int) -> int:
    """
    Stream the JSONL and keep the first `limit` posts that pass Step 1's filters,
    stopping as soon as enough are found (fast — no full scan). Reuses Step 1's
    real filter logic (process_batch) so the sample matches production output.
    """
    keywords       = cfg.load_keywords()
    medicine_terms = keywords["medicine_terms"]
    crawl_ts       = cfg.now_iso()

    jsonl_path = s1.decompress(subreddit)   # reuses existing .jsonl if present

    kept: list[dict] = []
    total = skipped_date = skipped_medicine = 0
    with open(jsonl_path, "r", encoding="utf-8") as fin:
        for chunk in s1._iter_batches(fin, SCAN_CHUNK):
            recs, st = s1.process_batch(
                chunk, medicine_terms, cfg.START_TS, cfg.END_TS, subreddit, crawl_ts
            )
            total            += st["total"]
            skipped_date     += st["skipped_date"]
            skipped_medicine += st["skipped_medicine"]
            kept.extend(recs)
            if len(kept) >= limit:
                break

    kept = kept[:limit]
    cfg.write_json(cfg.step_path(cfg.DIR_STEP1, subreddit), kept)
    cfg.update_summary(subreddit, "step1_extract", {
        "sample_limit":        limit,
        "scanned_until_limit": total,
        "skipped_date":        skipped_date,
        "skipped_no_medicine": skipped_medicine,
        "kept_all":            len(kept),
    })
    print(f"[test] r/{subreddit}: collected {len(kept)} (scanned {total:,})")
    return len(kept)


def main() -> None:
    subreddits = cfg.load_subreddits()
    print(f"[test] sample={SAMPLE_SIZE} per subreddit → {cfg.OUTPUT_BASE}\n")
    for subreddit in subreddits:
        try:
            sample_extract(subreddit, SAMPLE_SIZE)
            s2.clean_one(subreddit)
            s3.filter_one(subreddit)
        except FileNotFoundError as exc:
            print(f"[SKIP] r/{subreddit}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] r/{subreddit}: {exc}")
    print(f"\n[test] done → {cfg.OUTPUT_BASE}")


if __name__ == "__main__":
    main()
