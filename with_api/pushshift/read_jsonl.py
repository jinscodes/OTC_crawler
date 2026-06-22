import os
import json

# 스크립트 위치 기준 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
input_file = os.path.join(BASE_DIR, "AskDocs_submissions.jsonl")

LIMIT = 10  # 확인할 줄 수

with open(input_file, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        post = json.loads(line)

        print(f"[{i}] {post.get('title', '')}")
        print(f"    subreddit : {post.get('subreddit', '')}")
        print(f"    author    : {post.get('author', '')}")
        body = (post.get("selftext") or "").replace("\n", " ")
        print(f"    body      : {body[:120]}")
        print("-" * 60)

        if i >= LIMIT:
            break
