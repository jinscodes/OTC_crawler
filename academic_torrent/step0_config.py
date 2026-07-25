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
import math
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
#   summary/comprehensive.json              (combined stats for all subreddits)
#   crawl_summary.json                      (aggregate)
DIR_STEP1   = "step1_extract"      # step 1 output
DIR_STEP2   = "step2_clean"        # step 2 output
DIR_STEP3   = "step3_filter"       # step 3 output
DIR_STEP4   = "step4_llm_annotation"  # step 4 output (future)
DIR_SUMMARY = "summary"            # per-subreddit summaries
COMPREHENSIVE_SUMMARY_FILE = "comprehensive.json"

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
_STEP4_CONFIG = _CONFIG.get("step4_llm_annotation", {})

N_JOBS      = _CONFIG.get("n_jobs", -1)              # joblib workers (-1 = all cores)
BATCH_SIZE  = _CONFIG.get("batch_size", "auto")      # "auto" or a fixed int
BATCHES_PER_WORKER = _CONFIG.get("batches_per_worker", 4)  # used when BATCH_SIZE == "auto"
MIN_PARALLEL_ROWS  = _CONFIG.get("min_parallel_rows", 5000)  # below this: run serial
REUSE_JSONL = _CONFIG.get("reuse_jsonl", True)       # skip decompress if .jsonl exists

# Step 4 LLM batch controls. The model and prompt location are environment-
# specific and live in .env; non-secret execution settings stay in this
# version-controlled pipeline config.
STEP4_MAX_OUTPUT_TOKENS = _STEP4_CONFIG.get("max_output_tokens", 1_000)
STEP4_PROGRESS_EVERY = _STEP4_CONFIG.get("progress_every", 10)
STEP4_MAX_CONSECUTIVE_ERRORS = _STEP4_CONFIG.get("max_consecutive_errors", 3)
STEP4_CLIENT_MAX_RETRIES = _STEP4_CONFIG.get("client_max_retries", 3)
STEP4_CLIENT_TIMEOUT_SECONDS = _STEP4_CONFIG.get("client_timeout_seconds", 60.0)


def effective_workers() -> int:
    """Resolve N_JOBS to an actual worker count (n_jobs=-1 → machine core count)."""
    if isinstance(N_JOBS, int) and N_JOBS > 0:
        return N_JOBS
    return os.cpu_count() or 1


def batch_size_for(n_items: int) -> int:
    """
    Adaptive batch size for an in-memory list of n_items: size batches so there
    are ~BATCHES_PER_WORKER per core. Honors a fixed BATCH_SIZE if configured.
    """
    if isinstance(BATCH_SIZE, int) and BATCH_SIZE > 0:
        return BATCH_SIZE
    target_batches = max(1, effective_workers() * BATCHES_PER_WORKER)
    return max(1, math.ceil(n_items / target_batches))


def chunked(items: list, size: int):
    """Yield successive slices of `items` of length `size`."""
    for i in range(0, len(items), size):
        yield items[i:i + size]

START_YEAR = _DATE_RANGE.get("start_year", 2017)
END_YEAR   = _DATE_RANGE.get("end_year", 2025)
START_TS = int(datetime(START_YEAR, 1, 1, tzinfo=timezone.utc).timestamp())
END_TS   = int(datetime(END_YEAR, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())


# ── Regex helpers ────────────────────────────────────────────────────────────

def build_pattern(terms: list[str]) -> re.Pattern:
    """Word-boundary regex over the given terms (case-insensitive)."""
    escaped = [re.escape(t) for t in terms]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def find_all_matches(pattern: re.Pattern, text: str) -> list[str]:
    """Unique matches (lowercased), in order of first appearance — deterministic
    across processes so parallel and serial runs produce identical output."""
    seen: set[str] = set()
    out: list[str] = []
    for m in pattern.finditer(text):
        g = m.group().lower()
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out


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


def build_comprehensive_summary(
    subreddits: list[str] | None = None,
) -> dict:
    """Combine all available per-subreddit summaries into one document."""
    configured = subreddits or load_subreddits()
    per_subreddit = []
    missing = []
    total_posts_all = 0
    total_posts_cleaned = 0
    total_candidates = 0

    summary_dir = os.path.join(OUTPUT_BASE, DIR_SUMMARY)
    for subreddit in configured:
        summary_path = os.path.join(summary_dir, f"{subreddit}.json")
        summary = read_json(summary_path, default=None)
        if not summary:
            missing.append(subreddit)
            continue

        per_subreddit.append(summary)
        steps = summary.get("steps", {})
        total_posts_all += steps.get("step1_extract", {}).get("kept_all", 0)
        total_posts_cleaned += steps.get("step2_clean", {}).get("kept", 0)
        total_candidates += steps.get("step3_filter", {}).get("candidates", 0)

    included = [summary["subreddit"] for summary in per_subreddit]
    # A lean rollup: just the headline totals. Per-subreddit detail already
    # lives in each summary/{subreddit}.json, so it is not duplicated here.
    return {
        "generated_at": now_iso(),
        "date_range": {
            "start_year": START_YEAR,
            "end_year": END_YEAR,
        },
        "subreddits": len(included),
        "subreddits_missing_summary": missing,
        "posts_by_step": {
            "step1_extract": total_posts_all,
            "step2_clean": total_posts_cleaned,
            "step3_filter": total_candidates,
        },
    }


def write_comprehensive_summary(
    subreddits: list[str] | None = None,
) -> dict:
    """Write summary/comprehensive.json and return the combined document."""
    comprehensive = build_comprehensive_summary(subreddits)
    summary_dir = os.path.join(OUTPUT_BASE, DIR_SUMMARY)
    os.makedirs(summary_dir, exist_ok=True)
    write_json(
        os.path.join(summary_dir, COMPREHENSIVE_SUMMARY_FILE),
        comprehensive,
    )
    return comprehensive


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
    write_comprehensive_summary()


if __name__ == "__main__":
    keywords = load_keywords()
    print("Pipeline config")
    print(f"  base dir     : {BASE_DIR}")
    print(f"  zst dir      : {ZST_DIR}")
    print(f"  jsonl dir    : {JSONL_DIR}")
    print(f"  output base  : {OUTPUT_BASE}")
    print(f"  date range   : {START_YEAR}-{END_YEAR}")
    print(f"  n_jobs       : {N_JOBS}  (effective {effective_workers()}; detected {os.cpu_count()})")
    print(f"  batch_size   : {BATCH_SIZE}"
          + (f"  (~{BATCHES_PER_WORKER} batches/core)" if BATCH_SIZE == "auto" else ""))
    print(f"  reuse jsonl  : {REUSE_JSONL}")
    print(f"  subreddits   : {load_subreddits()}")
    print(f"  medicines    : {list(keywords['medicine_terms'])}")
    print(f"  dosing terms : {len(keywords['dosing_terms'])}")
    print(f"  exclude terms: {len(keywords['exclude_terms'])}")
