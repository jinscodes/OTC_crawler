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

After the implemented steps, aggregate summaries are written to
output/summary/comprehensive.json and output/crawl_summary.json.

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
    """Refresh both the summary-folder aggregate and legacy root aggregate."""
    aggregate = cfg.write_comprehensive_summary(subreddits)
    os.makedirs(cfg.OUTPUT_BASE, exist_ok=True)
    cfg.write_json(os.path.join(cfg.OUTPUT_BASE, "crawl_summary.json"), aggregate)
    steps = aggregate["posts_by_step"]
    print(
        "\nPipeline complete — "
        f"step1={steps['step1_extract']:,}  "
        f"step2={steps['step2_clean']:,}  "
        f"step3={steps['step3_filter']:,}"
    )


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
