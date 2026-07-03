"""
Step 4 — LLM annotation.  (NOT IMPLEMENTED YET)

Planned: read Step 3's posts_candidates.json and annotate each candidate with an
LLM (e.g. Claude) for review — classify intent, flag risky dosing questions,
extract structured dose info — then write posts_annotated.json.

Input  : output/without_api/{subreddit}/posts_candidates.json
Output : output/without_api/{subreddit}/posts_annotated.json   (cfg.FILE_ANNOTATED)

Left as a placeholder on purpose; implementation to be added later.
"""

import academic_torrent.step0_config as cfg  # noqa: F401  (kept so the module wiring is ready)


def annotate_one(subreddit: str) -> dict:
    raise NotImplementedError("Step 4 (LLM annotation) is not implemented yet.")


def run(subreddits: list[str] | None = None) -> None:
    raise NotImplementedError("Step 4 (LLM annotation) is not implemented yet.")


if __name__ == "__main__":
    run()
