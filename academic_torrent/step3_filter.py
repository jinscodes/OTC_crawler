"""
Step 3 — Precise filtering.

Read Step 2's posts_cleaned.json and reduce it to high-quality candidates:
  • drop posts hitting EXCLUDE_TERMS (pets, kids, pregnancy, ads, …),
  • require at least one dosing-related term,
  • categorize by medicine and record the matched dosing terms.

Output (per subreddit): output/without_api/{subreddit}/posts_candidates.json

Run standalone:  python step3_filter.py
"""

import step0_config as cfg


def filter_one(subreddit: str) -> dict:
    """Filter one subreddit's posts_cleaned.json → posts_candidates.json."""
    keywords   = cfg.load_keywords()
    dosing_re  = cfg.build_pattern(keywords["dosing_terms"])
    exclude_re = cfg.build_pattern(keywords["exclude_terms"])

    posts = cfg.read_json(cfg.step_path(cfg.DIR_STEP2, subreddit), default=None)
    if posts is None:
        raise FileNotFoundError(f"{cfg.DIR_STEP2}/{subreddit}.json not found")

    candidates: list[dict] = []
    flagged_excluded = no_dosing = 0
    by_medicine: dict[str, int] = {}

    for post in posts:
        text = post.get("clean_text") or f"{post.get('title', '')} {post.get('body', '')}"

        if exclude_re.search(text):
            flagged_excluded += 1
            continue

        dosing_matches = cfg.find_all_matches(dosing_re, text)
        if not dosing_matches:
            no_dosing += 1
            continue

        medicine = post.get("matched_medicine")
        by_medicine[medicine] = by_medicine.get(medicine, 0) + 1

        candidate = dict(post)
        candidate["matched_dosing_terms"] = dosing_matches
        candidate["medicine_category"]    = medicine
        candidate["filter_status"]        = "candidate"
        candidates.append(candidate)

    cfg.write_json(cfg.step_path(cfg.DIR_STEP3, subreddit), candidates)

    stats = {
        "input":            len(posts),
        "flagged_excluded": flagged_excluded,
        "no_dosing":        no_dosing,
        "candidates":       len(candidates),
        "by_medicine":      by_medicine,
    }
    cfg.update_summary(subreddit, "step3_filter", stats)
    print(f"[step3] r/{subreddit}: {len(candidates):,} candidates / {len(posts):,}")
    return stats


def run(subreddits: list[str] | None = None) -> None:
    subreddits = subreddits or cfg.load_subreddits()
    print(f"[step3] filter — subreddits: {subreddits}")
    for subreddit in subreddits:
        try:
            filter_one(subreddit)
        except FileNotFoundError as exc:
            print(f"[SKIP] r/{subreddit}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] r/{subreddit}: {exc}")


if __name__ == "__main__":
    run()
