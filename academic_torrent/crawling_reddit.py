"""
crawling_reddit.py — pipeline orchestrator.

Runs the crawling pipeline end to end by calling each step module in order.
Each step reads the previous step's output files and writes its own, so steps
can also be run independently (python stepN_*.py).

  Step 0  config          — step0_config.py     (shared config/helpers)
  Step 1  fast extraction — step1_extract.py    → posts_all.json
  Step 2  cleaning        — step2_clean.py       → posts_cleaned.json
  Step 3  precise filter  — step3_filter.py      → posts_candidates.json
  Step 4  LLM annotation  — step4_llm_annotation.py  (not implemented yet)
  Step 5  review/export   — step5_export.py          (not implemented yet)

After the implemented steps, an aggregate summary is written to
output/without_api/crawl_summary.json.

Run:  python crawling_reddit.py
"""

import os

import academic_torrent.step0_config as cfg
import academic_torrent.step1_extract as step1_extract
import academic_torrent.step2_clean as step2_clean
import academic_torrent.step3_filter as step3_filter

# Step 4/5 are placeholders; import lazily in run_pipeline once implemented.

RUN_LLM_ANNOTATION = False   # step 4 — off until implemented
RUN_EXPORT         = False   # step 5 — off until implemented


def write_aggregate(subreddits: list[str]) -> None:
    """Collect each subreddit's crawl_summary.json into one aggregate file."""
    per_subreddit = []
    total_all = total_candidates = 0
    for subreddit in subreddits:
        summary = cfg.read_json(cfg.step_path(cfg.DIR_SUMMARY, subreddit), default=None)
        if not summary:
            continue
        per_subreddit.append(summary)
        steps = summary.get("steps", {})
        total_all        += steps.get("step1_extract", {}).get("kept_all", 0)
        total_candidates += steps.get("step3_filter", {}).get("candidates", 0)

    aggregate = {
        "crawl_timestamp":      cfg.now_iso(),
        "date_range":           {"start_year": cfg.START_YEAR, "end_year": cfg.END_YEAR},
        "subreddits_processed": [s["subreddit"] for s in per_subreddit],
        "total_posts_all":      total_all,
        "total_candidates":     total_candidates,
        "per_subreddit":        per_subreddit,
    }
    os.makedirs(cfg.OUTPUT_BASE, exist_ok=True)
    cfg.write_json(os.path.join(cfg.OUTPUT_BASE, "crawl_summary.json"), aggregate)
    print(f"\nPipeline complete — "
          f"posts_all={total_all:,}  candidates={total_candidates:,}")


def run_pipeline() -> None:
    subreddits = cfg.load_subreddits()
    print(f"Pipeline start — subreddits: {subreddits}\n")

    step1_extract.run(subreddits)
    step2_clean.run(subreddits)
    step3_filter.run(subreddits)

    if RUN_LLM_ANNOTATION:
        import academic_torrent.step4_llm_annotation as step4_llm_annotation
        step4_llm_annotation.run(subreddits)
    if RUN_EXPORT:
        import academic_torrent.step5_export as step5_export
        step5_export.run(subreddits)

    write_aggregate(subreddits)


if __name__ == "__main__":
    run_pipeline()
