# Reddit OTC-Medication Crawling Pipeline

Reddit(Academic Torrent 덤프)에서 일반의약품(OTC) **복용량 관련 질문 글**을 추출하는
6단계 파이프라인. 각 스텝은 이전 스텝의 출력 파일을 입력으로 받아 자기 출력을 생성하는
**파일 기반 스테이지 구조**라, 각 단계를 독립적으로 실행·재실행할 수 있다.

```
Step 1          Step 2           Step 3            Step 4            Step 5
Extract   →     Clean     →      Filter     →      Annotate    →     Export
posts_all  →  posts_cleaned  →  posts_candidates → posts_annotated → review export
   ▲
Step 0 (Config) — 모든 스텝이 공유하는 설정 제공
```

대상 서브레딧: `AskDocs`, `medical_advice`, `AskPharmacists`, `pharmacy`,
`NoStupidQuestions`, `TooAfraidToAsk` · 기간: 2017–2021

---

## Step 0 — Config
**파일:** `step0_config.py`

**Input**
- `keywords.yaml` — 의약품 용어(brand/generic), 복용량(dosing) 용어, 제외(exclude) 용어
- `subreddits.yaml` — 크롤링 대상 서브레딧 목록
- `pipeline_config.yaml` — 기간, 병렬 워커 수, 경로 등 실행 파라미터

**Output**
- shared pipeline settings — 모든 스텝이 import 해서 사용하는 공통 설정
  (경로, 날짜 범위, 정규식 패턴 빌더, IO/요약 헬퍼)

---

## Step 1 — Fast Extraction
**파일:** `step1_extract.py`

**Input**
- `zst/{subreddit}.zst` — 원본 Reddit 덤프(압축)
- Step 0 shared settings

**Output**
- `posts_all.json` — 대량 1차 추출 결과

**처리 내용**
- `.zst` 압축 해제 → `.jsonl`
- ① 기간 필터(2017–2021) ② 의약품 키워드 매칭(둘 다 만족한 글만 유지)
- 서브레딧 병렬 처리(CPU 바운드). `.zst` 없는 서브레딧은 건너뜀

---

## Step 2 — Cleaning
**파일:** `step2_clean.py`

**Input**
- `posts_all.json`

**Output**
- `posts_cleaned.json` — 정제된 텍스트 + `clean_text` 필드 추가

**처리 내용**
- 중복 글(post_id) 제거
- URL·마크다운 링크 제거, 공백/줄바꿈 정규화
- 본문이 빈 글 제거

---

## Step 3 — Precise Filtering
**파일:** `step3_filter.py`

**Input**
- `posts_cleaned.json`

**Output**
- `posts_candidates.json` — 고품질 후보 글

**처리 내용**
- 제외 용어(반려동물·아동·임신·광고 등) 포함 글 제거
- 복용량(dosing) 용어가 하나 이상 있는 글만 유지
- 의약품별 분류(`medicine_category`) 및 매칭된 dosing 용어 기록

---

## Step 4 — LLM Annotation  *(예정 / not implemented)*
**파일:** `step4_llm_annotation.py`

**Input**
- `posts_candidates.json`

**Output**
- `posts_annotated.json` — LLM(Claude) 주석이 달린 검토용 후보 세트

**처리 내용(계획)**
- 질문 의도 분류, 위험한 복용량 질문 플래그, 구조화된 복용 정보 추출

---

## Step 5 — Review / Export  *(예정 / not implemented)*
**파일:** `step5_export.py`

**Input**
- `posts_annotated.json`

**Output**
- 검토용 export 산출물(예: 서브레딧 통합 CSV/스프레드시트) + 최종 집계 리포트

---

## 산출물 요약 (per subreddit)

출력 경로: `output/without_api/{subreddit}/`

| 파일 | 생성 스텝 | 내용 |
|------|-----------|------|
| `posts_all.json`        | Step 1 | 기간 + 의약품 매칭 전체 글 |
| `posts_cleaned.json`    | Step 2 | 정제된 글 |
| `posts_candidates.json` | Step 3 | dosing 질문 후보 |
| `posts_annotated.json`  | Step 4 | LLM 주석 결과 *(예정)* |
| `crawl_summary.json`    | 전 스텝 | 스텝별 통계 누적 |

전체 통합 요약: `output/without_api/crawl_summary.json`

---

## 실행 방법

```bash
python crawling_reddit.py     # 전체 파이프라인 (Step 1 → 2 → 3)
python step1_extract.py       # 특정 스텝만 독립 실행
```

## 현재 구현 상태 (2026-07-02)

- **구현 완료:** Step 0 · Step 1 · Step 2 · Step 3
- **파일만 생성(미구현):** Step 4 · Step 5
- **설정 파일:** 현재는 `detail.json` 하나를 사용. 위 `keywords.yaml` /
  `subreddits.yaml` / `pipeline_config.yaml` 분리는 계획된 구조.
- **검증 실행:** AskDocs + medical_advice(`.zst` 보유분) 기준 —
  posts_all 26,801건 → candidates 8,046건.
