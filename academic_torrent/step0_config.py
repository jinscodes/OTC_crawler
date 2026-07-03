"""
Step 0 — Config.

Shared configuration, paths, and helpers for the crawling pipeline. Every other
step imports from here.

Inputs (YAML):
  • keywords.yaml         — medicine / dosing / exclude term lists
  • subreddits.yaml       — subreddits to crawl
  • pipeline_config.yaml  — date range, workers, and other run parameters

Output: shared pipeline settings (the constants and helpers below).

Running this file prints the resolved config so you can sanity-check it.
"""

import json
import os
import re
from datetime import datetime, timezone

import yaml

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
ZST_DIR     = os.path.join(BASE_DIR, "zst")
JSONL_DIR   = os.path.join(BASE_DIR, "jsonl")
OUTPUT_BASE = os.path.normpath(
    os.path.join(BASE_DIR, "..", "output")
)

# ── Config files (Step 0 inputs) ─────────────────────────────────────────────
KEYWORDS_FILE   = os.path.join(BASE_DIR, "keywords.yaml")
SUBREDDITS_FILE = os.path.join(BASE_DIR, "subreddits.yaml")
CONFIG_FILE     = os.path.join(BASE_DIR, "pipeline_config.yaml")

# ── Output layout (step-first: one folder per stage, {subreddit}.json inside) ─
# output/without_api/
#   step1_extract/{subreddit}.json
#   step2_clean/{subreddit}.json
#   step3_filter/{subreddit}.json
#   step4_llm_annotation/{subreddit}.json   (future)
#   summary/{subreddit}.json                (per-subreddit stats, all steps)
#   crawl_summary.json                      (aggregate)
DIR_STEP1   = "step1_extract"      # step 1 output
DIR_STEP2   = "step2_clean"        # step 2 output
DIR_STEP3   = "step3_filter"       # step 3 output
DIR_STEP4   = "step4_llm_annotation"  # step 4 output (future)
DIR_SUMMARY = "summary"            # per-subreddit summaries

# ── Config loading ───────────────────────────────────────────────────────────

def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_keywords() -> dict:
    """medicine / dosing / exclude term lists from keywords.yaml."""
    return _load_yaml(KEYWORDS_FILE)


def load_subreddits() -> list[str]:
    return _load_yaml(SUBREDDITS_FILE).get("subreddits", [])


# ── Run parameters (from pipeline_config.yaml) ───────────────────────────────
_CONFIG      = _load_yaml(CONFIG_FILE)
_DATE_RANGE  = _CONFIG.get("date_range", {})

WORKERS     = _CONFIG.get("workers", 2)          # parallel subreddits in Step 1
REUSE_JSONL = _CONFIG.get("reuse_jsonl", True)   # skip decompress if .jsonl exists

START_YEAR = _DATE_RANGE.get("start_year", 2017)
END_YEAR   = _DATE_RANGE.get("end_year", 2021)
START_TS = int(datetime(START_YEAR, 1, 1, tzinfo=timezone.utc).timestamp())
END_TS   = int(datetime(END_YEAR, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())


# ── Regex helpers ────────────────────────────────────────────────────────────

def build_pattern(terms: list[str]) -> re.Pattern:
    """Word-boundary regex over the given terms (case-insensitive)."""
    escaped = [re.escape(t) for t in terms]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def find_all_matches(pattern: re.Pattern, text: str) -> list[str]:
    return list({m.group().lower() for m in pattern.finditer(text)})


# ── IO helpers ───────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def step_path(step_dir: str, subreddit: str) -> str:
    """
    Path to a step's output file for one subreddit:
    output/without_api/{step_dir}/{subreddit}.json (parent dir is created).
    """
    dir_path = os.path.join(OUTPUT_BASE, step_dir)
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, f"{subreddit}.json")


def read_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_summary(subreddit: str, step_key: str, stats: dict) -> None:
    """
    Read the per-subreddit summary (summary/{subreddit}.json), merge in this
    step's stats under steps[step_key], and write it back. Safe because steps run
    sequentially and each subreddit owns its own summary file.
    """
    summary_path = step_path(DIR_SUMMARY, subreddit)
    summary = read_json(summary_path, default=None) or {
        "subreddit":  subreddit,
        "date_range": {"start_year": START_YEAR, "end_year": END_YEAR},
        "steps":      {},
    }
    summary.setdefault("steps", {})[step_key] = stats
    summary["updated_at"] = now_iso()
    write_json(summary_path, summary)


if __name__ == "__main__":
    keywords = load_keywords()
    print("Pipeline config")
    print(f"  base dir     : {BASE_DIR}")
    print(f"  zst dir      : {ZST_DIR}")
    print(f"  jsonl dir    : {JSONL_DIR}")
    print(f"  output base  : {OUTPUT_BASE}")
    print(f"  date range   : {START_YEAR}-{END_YEAR}")
    print(f"  workers      : {WORKERS}")
    print(f"  reuse jsonl  : {REUSE_JSONL}")
    print(f"  subreddits   : {load_subreddits()}")
    print(f"  medicines    : {list(keywords['medicine_terms'])}")
    print(f"  dosing terms : {len(keywords['dosing_terms'])}")
    print(f"  exclude terms: {len(keywords['exclude_terms'])}")
