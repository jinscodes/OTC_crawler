import os
import re
import json

# 스크립트 위치 기준 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
input_file = os.path.join(BASE_DIR, "AskDocs_submissions.jsonl")
output_file = os.path.join(BASE_DIR, "AskDocs_submissions.filtered.jsonl")
detail_file = os.path.join(BASE_DIR, "detail.json")


def load_detail() -> tuple[dict, list[str]]:
    with open(detail_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("MEDICINE_TERMS", {}), data.get("DOSING_TERMS", [])


def build_pattern(terms: list[str]) -> re.Pattern:
    # 단어 경계로 매칭 (asa, mg, wait 같은 짧은 토큰의 오탐 방지). 대소문자 무시.
    escaped = [re.escape(t) for t in terms]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def main() -> None:
    medicine_terms, dosing_terms = load_detail()

    all_medicine_synonyms = [s for syns in medicine_terms.values() for s in syns]
    medicine_re = build_pattern(all_medicine_synonyms)
    dosing_re = build_pattern(dosing_terms)

    total = 0
    kept = 0

    with open(input_file, "r", encoding="utf-8") as fin, \
            open(output_file, "w", encoding="utf-8") as fout:
        for line in fin:
            total += 1
            try:
                post = json.loads(line)
            except json.JSONDecodeError:
                continue

            text = f"{post.get('title', '')} {post.get('selftext', '') or ''}"

            if medicine_re.search(text) and dosing_re.search(text):
                fout.write(line)
                kept += 1

            if total % 100000 == 0:
                print(f"  ...{total:,}개 처리 / {kept:,}개 유지")

    print(f"\nDone. {total:,}개 중 {kept:,}개 유지 -> {output_file}")


if __name__ == "__main__":
    main()
