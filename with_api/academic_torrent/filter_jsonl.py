import json
import os
import re
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_BASE = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "output", "with_api", "academic_torrent"))
DETAIL_FILE = os.path.join(BASE_DIR, "detail.json")

# ── Date range ─────────────────────────────────────────────────────────────────
START_YEAR = 2017
END_YEAR   = 2021
START_TS = int(datetime(START_YEAR, 1, 1, tzinfo=timezone.utc).timestamp())
END_TS   = int(datetime(END_YEAR, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_detail() -> dict:
    with open(DETAIL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_pattern(terms: list[str]) -> re.Pattern:
    """Word-boundary regex (case-insensitive)."""
    escaped = [re.escape(t) for t in terms]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def _find_all_matches(pattern: re.Pattern, text: str) -> list[str]:
    return list({m.group().lower() for m in pattern.finditer(text)})


# ── Main filtering function ────────────────────────────────────────────────────

def filter_and_save(subreddit: str, jsonl_path: str) -> str:
    """
    Read jsonl_path and apply three filtering stages:

      Stage 1 — Date range (START_YEAR–END_YEAR)
                Posts outside the range are dropped.

      Stage 2 — MEDICINE_TERMS + DOSING_TERMS
                Posts with no medicine match are dropped.
                Dosing matches are recorded; posts without them get
                filter_status='ok' (medicine only).

      Stage 3 — EXCLUDE_TERMS
                Posts matching exclude terms are NOT dropped;
                they are marked filter_status='flagged' for later review.

    Writes output/with_api/pushshift/{subreddit}/posts.json.
    Returns the output file path.
    """
    detail = _load_detail()
    medicine_terms: dict[str, list[str]] = detail["MEDICINE_TERMS"]
    dosing_terms: list[str]              = detail["DOSING_TERMS"]
    exclude_terms: list[str]             = detail["EXCLUDE_TERMS"]

    medicine_patterns: dict[str, re.Pattern] = {
        generic: _build_pattern(synonyms)
        for generic, synonyms in medicine_terms.items()
    }
    dosing_re   = _build_pattern(dosing_terms)
    exclude_re  = _build_pattern(exclude_terms)

    output_dir  = os.path.join(OUTPUT_BASE, subreddit)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "posts.json")

    crawl_ts = datetime.now(timezone.utc).isoformat()
    posts: list[dict] = []
    total = kept = skipped_date = skipped_medicine = 0

    print(f"\n[filter] Reading {jsonl_path} ...")

    with open(jsonl_path, "r", encoding="utf-8") as fin:
        for raw_line in fin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            total += 1

            try:
                post = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            # ── Stage 1: Date filter ───────────────────────────────────────
            try:
                created_utc = int(post.get("created_utc", 0))
            except (ValueError, TypeError):
                continue

            if not (START_TS <= created_utc <= END_TS):
                skipped_date += 1
                continue

            # ── Stage 2: Medicine filter ───────────────────────────────────
            title: str = post.get("title", "") or ""
            body: str  = post.get("selftext", "") or ""
            if body in ("[deleted]", "[removed]"):
                body = ""
            text = f"{title} {body}"

            matched_generic: str | None = None
            matched_synonym: str | None = None
            for generic, pat in medicine_patterns.items():
                m = pat.search(text)
                if m:
                    matched_generic = generic
                    matched_synonym = m.group()
                    break

            if not matched_generic:
                skipped_medicine += 1
                continue

            dosing_matches = _find_all_matches(dosing_re, text)

            # ── Stage 3: Exclude filter (mark only) ───────────────────────
            has_exclude = bool(exclude_re.search(text))

            if has_exclude:
                filter_status = "flagged"
            elif dosing_matches:
                filter_status = "ok_with_dosing"
            else:
                filter_status = "ok"

            # ── Build record ───────────────────────────────────────────────
            post_id        = post.get("id", "")
            subreddit_name = post.get("subreddit", subreddit)
            permalink      = post.get("permalink", "")
            url = (
                post.get("url") or
                (f"https://www.reddit.com{permalink}" if permalink else
                 f"https://www.reddit.com/r/{subreddit_name}/comments/{post_id}/")
            )
            created_time = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()

            posts.append({
                "post_id":                post_id,
                "subreddit":              subreddit_name,
                "title":                  title,
                "body":                   body,
                "url":                    url,
                "created_time":           created_time,
                "crawl_timestamp":        crawl_ts,
                "matched_medicine":       matched_generic,
                "matched_brand_or_generic": matched_synonym,
                "matched_dosing_terms":   dosing_matches,
                "filter_status":          filter_status,
                "screenshot":             "",
            })
            kept += 1

            if total % 100_000 == 0:
                print(f"  ... {total:,} scanned / {kept:,} kept")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

    flagged    = sum(1 for p in posts if p["filter_status"] == "flagged")
    with_dosing = sum(1 for p in posts if p["filter_status"] == "ok_with_dosing")
    ok_only    = sum(1 for p in posts if p["filter_status"] == "ok")

    print(f"[filter] Done — {subreddit}")
    print(f"  Total scanned      : {total:,}")
    print(f"  Skipped (date)     : {skipped_date:,}")
    print(f"  Skipped (medicine) : {skipped_medicine:,}")
    print(f"  Kept               : {kept:,}")
    print(f"    ok               : {ok_only:,}")
    print(f"    ok_with_dosing   : {with_dosing:,}")
    print(f"    flagged          : {flagged:,}")
    print(f"  Output             : {output_file}")
    return output_file
