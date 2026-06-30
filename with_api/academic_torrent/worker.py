"""
CPU-bound stage for the parallel pipeline.

decompress + filter are pure-Python / CPU work, so they run inside a
ProcessPoolExecutor (threads would be useless here because of the GIL).

This lives in its own module so the callable is importable by the spawned
worker processes (macOS uses the 'spawn' start method).
"""

from decompress import decompress
from filter_jsonl import filter_and_save


def decompress_and_filter(subreddit: str) -> str:
    """
    Run decompress → filter for one subreddit inside a worker process.
    Returns the path to the produced posts.json.
    Raises FileNotFoundError if the .zst file is missing.
    """
    jsonl_path = decompress(subreddit)
    posts_path = filter_and_save(subreddit, jsonl_path)
    return posts_path
