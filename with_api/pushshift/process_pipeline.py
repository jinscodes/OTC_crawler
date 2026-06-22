"""
Pipeline: decompress .zst → filter JSONL → save posts.json

Processes each subreddit in SUBREDDITS order (from detail.json).
Stops immediately if a .zst file is missing for the current subreddit.

Output: output/with_api/{subreddit}/posts.json
"""

import io
import json
import os
import re
from datetime import datetime, timezone

import zstandard as zstd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_BASE = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "output", "with_api", "pushshift"))
DETAIL_FILE = os.path.join(BASE_DIR, "detail.json")

# ── Date range ────────────────────────────────────────────────────────────────
START_YEAR = 2017
END_YEAR = 2021
START_TS = int(datetime(START_YEAR, 1, 1, tzinfo=timezone.utc).timestamp())
END_TS = int(datetime(END_YEAR, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_detail() -> dict:
    with open(DETAIL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_pattern(terms: list[str]) -> re.Pattern:
    """Word-boundary regex for a list of terms (case-insensitive)."""
    escaped = [re.escape(t) for t in terms]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def find_all_matches(pattern: re.Pattern, text: str) -> list[str]:
    return list({m.group().lower() for m in pattern.finditer(text)})


# ── Per-subreddit processing ──────────────────────────────────────────────────

def process_subreddit(subreddit: str, detail: dict) -> bool:
    """
    Returns True on success, False if the .zst file is missing
    (caller should stop the pipeline in that case).
    """
    zst_file = os.path.join(BASE_DIR, f"{subreddit}.zst")
    if not os.path.exists(zst_file):
        print(f"[{subreddit}] {subreddit}.zst not found — stopping pipeline.")
        return False

    medicine_terms: dict[str, list[str]] = detail["MEDICINE_TERMS"]
    dosing_terms: list[str] = detail["DOSING_TERMS"]
    exclude_terms: list[str] = detail["EXCLUDE_TERMS"]

    # Build per-generic patterns so we can record which generic matched
    medicine_patterns: dict[str, re.Pattern] = {
        generic: build_pattern(synonyms)
        for generic, synonyms in medicine_terms.items()
    }
    dosing_re = build_pattern(dosing_terms)
    exclude_re = build_pattern(exclude_terms)

    # Prepare output
    output_dir = os.path.join(OUTPUT_BASE, subreddit)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "posts.json")

    crawl_ts = datetime.now(timezone.utc).isoformat()
    posts: list[dict] = []
    total = kept = 0

    print(f"\n[{subreddit}] Decompressing & filtering {zst_file} ...")

    with open(zst_file, "rb") as fh:
        dctx = zstd.ZstdDecompressor(max_window_size=2**31)
        stream_reader = dctx.stream_reader(fh)
        text_stream = io.TextIOWrapper(stream_reader, encoding="utf-8")

        for raw_line in text_stream:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            total += 1

            try:
                post = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            # ── 1. Date filter (2017–2021) ─────────────────────────────────
            try:
                created_utc = int(post.get("created_utc", 0))
            except (ValueError, TypeError):
                continue

            if not (START_TS <= created_utc <= END_TS):
                continue

            # ── 2. Build search text ───────────────────────────────────────
            title: str = post.get("title", "") or ""
            body: str = post.get("selftext", "") or ""
            if body in ("[deleted]", "[removed]"):
                body = ""
            text = f"{title} {body}"

            # ── 3. Medicine filter (required) ──────────────────────────────
            matched_generic: str | None = None
            matched_synonym: str | None = None

            for generic, pat in medicine_patterns.items():
                m = pat.search(text)
                if m:
                    matched_generic = generic
                    matched_synonym = m.group()
                    break

            if not matched_generic:
                continue  # Must contain at least one medicine term (5-1)

            # ── 4. Dosing terms ────────────────────────────────────────────
            dosing_matches = find_all_matches(dosing_re, text)

            # ── 5. Exclude terms — mark, do NOT drop (5-3) ─────────────────
            has_exclude = bool(exclude_re.search(text))

            # ── 6. filter_status ───────────────────────────────────────────
            if has_exclude:
                filter_status = "flagged"           # marked for potential removal
            elif dosing_matches:
                filter_status = "ok_with_dosing"    # medicine + dosing (5-2)
            else:
                filter_status = "ok"                # medicine only (5-1)

            # ── 7. Build record ────────────────────────────────────────────
            post_id = post.get("id", "")
            subreddit_name = post.get("subreddit", subreddit)
            permalink = post.get("permalink", "")
            url = (
                post.get("url") or
                (f"https://www.reddit.com{permalink}" if permalink else
                 f"https://www.reddit.com/r/{subreddit_name}/comments/{post_id}/")
            )
            created_time = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()

            record = {
                "post_id": post_id,
                "subreddit": subreddit_name,
                "title": title,
                "body": body,
                "url": url,
                "created_time": created_time,
                "crawl_timestamp": crawl_ts,
                "query_used": matched_generic,
                "matched_medicine": matched_generic,
                "matched_brand_or_generic": matched_synonym,
                "matched_dosing_terms": dosing_matches,
                "filter_status": filter_status,
                "screenshot": "",
            }
            posts.append(record)
            kept += 1

            if total % 100_000 == 0:
                print(f"  ... {total:,} scanned / {kept:,} kept")

    # ── Save ──────────────────────────────────────────────────────────────────
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

    flagged = sum(1 for p in posts if p["filter_status"] == "flagged")
    with_dosing = sum(1 for p in posts if p["filter_status"] == "ok_with_dosing")
    ok_only = sum(1 for p in posts if p["filter_status"] == "ok")

    print(f"[{subreddit}] Done.")
    print(f"  Total scanned : {total:,}")
    print(f"  Kept          : {kept:,}")
    print(f"    ok           : {ok_only:,}")
    print(f"    ok_with_dosing: {with_dosing:,}")
    print(f"    flagged      : {flagged:,}")
    print(f"  Output        : {output_file}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    detail = load_detail()
    subreddits: list[str] = detail.get("SUBREDDITS", [])

    print(f"Pipeline start — subreddits: {subreddits}")
    print(f"Date range: {START_YEAR}–{END_YEAR}")
    print(f"Output base: {OUTPUT_BASE}\n")

    for subreddit in subreddits:
        success = process_subreddit(subreddit, detail)
        if not success:
            break  # Stop pipeline when .zst is missing (requirement 2-2)

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
