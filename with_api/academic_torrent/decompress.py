import os
import zstandard as zstd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def decompress(subreddit: str) -> str:
    """
    Decompress {subreddit}.zst → {subreddit}.jsonl (same folder).
    Returns the absolute path to the output .jsonl file.
    Raises FileNotFoundError if the .zst file does not exist.
    """
    zst_path = os.path.join(BASE_DIR, f"{subreddit}.zst")
    jsonl_path = os.path.join(BASE_DIR, f"{subreddit}.jsonl")

    if not os.path.exists(zst_path):
        raise FileNotFoundError(f"{zst_path} not found")

    print(f"[decompress] {subreddit}.zst → {subreddit}.jsonl ...")

    with open(zst_path, "rb") as compressed, open(jsonl_path, "wb") as destination:
        dctx = zstd.ZstdDecompressor(max_window_size=2**31)
        dctx.copy_stream(compressed, destination)

    size_mb = os.path.getsize(jsonl_path) / 1024 / 1024
    print(f"[decompress] Done → {jsonl_path} ({size_mb:.1f} MB)")
    return jsonl_path
