from joblib import Parallel, delayed

import step0_config as cfg


def filter_batch(posts: list[dict], dosing_terms: list, exclude_terms: list
                 ) -> tuple[list[dict], dict]:
    """
    Apply the exclude + dosing filters to a batch of posts (runs in a worker).
    Returns (candidates, partial_stats). Patterns are rebuilt here (cheap) so the
    function stays picklable and self-contained.
    """
    dosing_re  = cfg.build_pattern(dosing_terms)
    exclude_re = cfg.build_pattern(exclude_terms)

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

    stats = {
        "flagged_excluded": flagged_excluded,
        "no_dosing":        no_dosing,
        "by_medicine":      by_medicine,
    }
    return candidates, stats


def filter_one(subreddit: str) -> dict:
    """Filter one subreddit's posts_cleaned → posts_candidates. Returns stats."""
    keywords      = cfg.load_keywords()
    dosing_terms  = keywords["dosing_terms"]
    exclude_terms = keywords["exclude_terms"]

    posts = cfg.read_json(cfg.step_path(cfg.DIR_STEP2, subreddit), default=None)
    if posts is None:
        raise FileNotFoundError(f"{cfg.DIR_STEP2}/{subreddit}.json not found")

    # Parallelize the regex filtering (order preserved); serial for small inputs.
    if len(posts) < cfg.MIN_PARALLEL_ROWS:
        batch_results = [filter_batch(posts, dosing_terms, exclude_terms)]
    else:
        batch_size = cfg.batch_size_for(len(posts))
        batch_results = Parallel(n_jobs=cfg.N_JOBS)(
            delayed(filter_batch)(chunk, dosing_terms, exclude_terms)
            for chunk in cfg.chunked(posts, batch_size)
        )

    # Merge batches (order preserved).
    candidates: list[dict] = []
    flagged_excluded = no_dosing = 0
    by_medicine: dict[str, int] = {}
    for recs, st in batch_results:
        candidates.extend(recs)
        flagged_excluded += st["flagged_excluded"]
        no_dosing        += st["no_dosing"]
        for med, n in st["by_medicine"].items():
            by_medicine[med] = by_medicine.get(med, 0) + n

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
