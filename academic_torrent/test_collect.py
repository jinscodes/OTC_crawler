"""
Test harness — collect a small sample per subreddit and run steps 1–3.

It streams the source until it finds up to SAMPLE_SIZE posts per subreddit that
pass the final Step 3 repeat-dose filter (or reaches EOF). This matters because
repeat-dose timing questions are rare; sampling the first Step 1 medicine hits
would usually produce an irrelevant or empty Step 3 sample.

Everything is written under output/test/ so the real output/ is untouched. The
three step files contain the same final sampled post IDs at their respective
processing stages:

    output/test/step1/{subreddit}.json     # raw fields for final sample
    output/test/step2/{subreddit}.json     # cleaned final sample
    output/test/step3/{subreddit}.json     # repeat-dose candidates
    output/test/summary/{subreddit}.json   # per-step stats

Run:  python test_collect.py
"""

import os

import step0_config as cfg
import step1_extract as s1
import step2_clean as s2
import step3_filter as s3

SAMPLE_SIZE = 50          # maximum final Step 3 posts collected per subreddit
SCAN_CHUNK  = 10_000      # raw lines processed per streaming batch

# Redirect all outputs to output/test/ with numbered step folders.
cfg.OUTPUT_BASE = os.path.join(cfg.OUTPUT_BASE, "test")
cfg.DIR_STEP1   = "step1"
cfg.DIR_STEP2   = "step2"
cfg.DIR_STEP3   = "step3"
cfg.DIR_SUMMARY = "summary"


def _merge_filter_stats(total: dict, partial: dict) -> None:
    """Merge one Step 3 batch's scalar and grouped statistics."""
    for key in (
        "flagged_other_medicine",
        "flagged_excluded",
        "flagged_excluded_intent",
        "no_repeat_dose_question",
    ):
        total[key] += partial[key]
    for key in ("by_other_medicine", "by_medicine", "by_repeat_dose_rule"):
        for name, count in partial[key].items():
            total[key][name] = total[key].get(name, 0) + count


def sample_candidates(subreddit: str, limit: int) -> int:
    """
    Stream raw posts through Steps 1–3 and retain the first `limit` final
    repeat-dose candidates. Stops early at the limit; otherwise scans to EOF.
    """
    keywords = cfg.load_keywords()
    medicine_terms = keywords["medicine_terms"]
    dosing_terms = keywords["dosing_terms"]
    exclude_terms = keywords["exclude_terms"]
    other_medicine_terms = keywords.get("other_medicine_terms", {})
    crawl_ts = cfg.now_iso()

    jsonl_path = s1.decompress(subreddit)  # reuses existing .jsonl if present

    sampled_step1: list[dict] = []
    sampled_step2: list[dict] = []
    sampled_step3: list[dict] = []
    sampled_ids: set[str] = set()
    seen_clean_ids: set[str] = set()
    total = skipped_date = skipped_medicine = 0
    target_matches_examined = cleaned_examined = 0
    duplicates = dropped_empty = 0
    filter_stats = {
        "flagged_other_medicine": 0,
        "by_other_medicine": {},
        "flagged_excluded": 0,
        "flagged_excluded_intent": 0,
        "no_repeat_dose_question": 0,
        "by_medicine": {},
        "by_repeat_dose_rule": {},
    }

    with open(jsonl_path, "r", encoding="utf-8") as fin:
        for chunk in s1._iter_batches(fin, SCAN_CHUNK):
            recs, st = s1.process_batch(
                chunk, medicine_terms, cfg.START_TS, cfg.END_TS, subreddit, crawl_ts
            )
            total += st["total"]
            skipped_date += st["skipped_date"]
            skipped_medicine += st["skipped_medicine"]
            target_matches_examined += len(recs)

            normalized = s2.normalize_batch(recs)
            cleaned: list[dict] = []
            for record in normalized:
                post_id = record.get("post_id", "")
                if post_id and post_id in seen_clean_ids:
                    duplicates += 1
                    continue
                if post_id:
                    seen_clean_ids.add(post_id)
                if not record["clean_text"]:
                    dropped_empty += 1
                    continue
                cleaned.append(record)
            cleaned_examined += len(cleaned)

            candidates, partial_stats = s3.filter_batch(
                cleaned,
                dosing_terms,
                exclude_terms,
                other_medicine_terms,
                medicine_terms,
            )
            _merge_filter_stats(filter_stats, partial_stats)

            raw_by_id = {record.get("post_id"): record for record in recs}
            clean_by_id = {record.get("post_id"): record for record in cleaned}
            for candidate in candidates:
                post_id = candidate.get("post_id", "")
                if not post_id or post_id in sampled_ids:
                    continue
                raw = raw_by_id.get(post_id)
                clean = clean_by_id.get(post_id)
                if raw is None or clean is None:
                    continue
                sampled_ids.add(post_id)
                sampled_step1.append(raw)
                sampled_step2.append(clean)
                sampled_step3.append(candidate)
                if len(sampled_step3) >= limit:
                    break
            if len(sampled_step3) >= limit:
                break

    cfg.write_json(cfg.step_path(cfg.DIR_STEP1, subreddit), sampled_step1)
    cfg.write_json(cfg.step_path(cfg.DIR_STEP2, subreddit), sampled_step2)
    cfg.write_json(cfg.step_path(cfg.DIR_STEP3, subreddit), sampled_step3)

    cfg.update_summary(subreddit, "step1_extract", {
        "sample_limit": limit,
        "sample_basis": "step3_repeat_dose_candidate",
        "scanned_until_limit": total,
        "skipped_date": skipped_date,
        "skipped_no_medicine": skipped_medicine,
        "target_matches_examined": target_matches_examined,
        "kept_all": len(sampled_step1),
    })
    cfg.update_summary(subreddit, "step2_clean", {
        "input_examined": target_matches_examined,
        "duplicates": duplicates,
        "dropped_empty": dropped_empty,
        "cleaned_examined": cleaned_examined,
        "kept": len(sampled_step2),
    })
    cfg.update_summary(subreddit, "step3_filter", {
        "input_examined": cleaned_examined,
        **filter_stats,
        "candidates": len(sampled_step3),
    })
    status = "limit reached" if len(sampled_step3) >= limit else "EOF reached"
    print(
        f"[test] r/{subreddit}: collected {len(sampled_step3)} final "
        f"candidates ({status}, scanned {total:,}, "
        f"target hits {target_matches_examined:,})"
    )
    return len(sampled_step3)


def main() -> None:
    subreddits = cfg.load_subreddits()
    print(f"[test] sample={SAMPLE_SIZE} per subreddit → {cfg.OUTPUT_BASE}\n")
    for subreddit in subreddits:
        try:
            sample_candidates(subreddit, SAMPLE_SIZE)
        except FileNotFoundError as exc:
            print(f"[SKIP] r/{subreddit}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] r/{subreddit}: {exc}")
    print(f"\n[test] done → {cfg.OUTPUT_BASE}")


if __name__ == "__main__":
    main()
