import os
import zstandard as zstd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
input_file = os.path.join(BASE_DIR, "AskDocs_submissions.zst")
output_file = os.path.join(BASE_DIR, "AskDocs_submissions.jsonl")

with open(input_file, "rb") as compressed:
    dctx = zstd.ZstdDecompressor(max_window_size=2**31)

    with open(output_file, "wb") as destination:
        dctx.copy_stream(compressed, destination)

print(f"Done -> {output_file}")
