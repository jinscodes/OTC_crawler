"""
Step 5 — Review / export.  (NOT IMPLEMENTED YET)

Planned: take Step 4's annotated candidates and export a review-friendly artifact
(e.g. a combined CSV/spreadsheet across subreddits, or a filtered review set) plus
a final aggregate report.

Input  : output/without_api/{subreddit}/posts_annotated.json
Output : TBD (e.g. output/without_api/review_export.csv)

Left as a placeholder on purpose; implementation to be added later.
"""

import academic_torrent.step0_config as cfg  # noqa: F401  (kept so the module wiring is ready)


def run(subreddits: list[str] | None = None) -> None:
    raise NotImplementedError("Step 5 (review/export) is not implemented yet.")


if __name__ == "__main__":
    run()
