"""
Step 3b — Merge.

Combine every output/step3_filter/{subreddit}.json into one file so the whole
candidate set can be read at once. Records already carry `subreddit`, so this is
a concatenation plus a post_id de-duplication (the same post can be reached from
more than one dump, e.g. a subreddit and its comments file).

Output: step3_filter/_all.json — or _decidable.json with --decidable, which
keeps only the annotation-decidable subset tagged by step3_filter.
"""

import glob
import os
import sys

import step0_config as cfg


ALL_FILE = "_all.json"
DECIDABLE_FILE = "_decidable.json"


def _subreddit_files() -> list[str]:
    """Per-subreddit Step 3 outputs, sorted. Merged files (_*.json) excluded."""
    pattern = os.path.join(cfg.OUTPUT_BASE, cfg.DIR_STEP3, "*.json")
    return sorted(
        path
        for path in glob.glob(pattern)
        if not os.path.basename(path).startswith("_")
    )


def merge(decidable_only: bool = False) -> dict:
    """Write the merged Step 3 file and return counts."""
    merged: list[dict] = []
    seen_ids: set[str] = set()
    duplicates = 0
    skipped_undecidable = 0
    by_subreddit: dict[str, int] = {}

    for path in _subreddit_files():
        posts = cfg.read_json(path, default=[]) or []
        for post in posts:
            if decidable_only and not post.get("decidability", {}).get(
                "decidable"
            ):
                skipped_undecidable += 1
                continue
            post_id = post.get("post_id", "")
            if post_id and post_id in seen_ids:
                duplicates += 1
                continue
            if post_id:
                seen_ids.add(post_id)
            merged.append(post)
            subreddit = post.get("subreddit", "")
            by_subreddit[subreddit] = by_subreddit.get(subreddit, 0) + 1

    name = DECIDABLE_FILE if decidable_only else ALL_FILE
    out_path = os.path.join(cfg.OUTPUT_BASE, cfg.DIR_STEP3, name)
    cfg.write_json(out_path, merged)

    stats = {
        "output": out_path,
        "files": len(_subreddit_files()),
        "posts": len(merged),
        "duplicates": duplicates,
        "skipped_undecidable": skipped_undecidable,
        "by_subreddit": by_subreddit,
    }
    print(
        f"[step3-merge] {len(merged):,} posts "
        f"from {stats['files']} files → {os.path.basename(out_path)}"
        + (f" ({duplicates:,} duplicate post_ids dropped)" if duplicates else "")
    )
    return stats


if __name__ == "__main__":
    merge(decidable_only="--decidable" in sys.argv[1:])
