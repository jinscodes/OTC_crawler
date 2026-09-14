import json
import math
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import pandas as pd

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_FILE)

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
INPUT_CASES_FILE = "structured_cases.json"

NUM_RUNS = 5
TEMPERATURE = 0.7
MAX_NEW_TOKENS = 300

ANSWER_FORMAT = {
    "format": {
        "type": "json_schema",
        "name": "confidence_answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"},
                "decision": {"type": "string", "enum": ["A", "B", "C"]},
                "confidence": {"type": "integer"}
            },
            "required": ["reasoning", "decision", "confidence"],
            "additionalProperties": False
        }
    }
}

PROBABILITY_FORMAT = {
    "format": {
        "type": "json_schema",
        "name": "decision_probabilities",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "p_yes": {"type": "number"},
                "p_no": {"type": "number"},
                "p_ambiguous": {"type": "number"}
            },
            "required": ["p_yes", "p_no", "p_ambiguous"],
            "additionalProperties": False
        }
    }
}

# OUTPUT_RUNS_FILE = "confidence_runs_qwen25_7b.json"
# OUTPUT_SUMMARY_FILE = "confidence_summary_qwen25_7b.json"

MODEL_FILE_NAME = MODEL_NAME.replace("-", "_").replace(".", "_")
OUTPUT_RUNS_CSV_FILE = f"confidence_runs_{MODEL_FILE_NAME}.csv"
OUTPUT_SUMMARY_CSV_FILE = f"confidence_summary_{MODEL_FILE_NAME}.csv"

def load_cases(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(question_text):
    return f"""You are answering an over-the-counter medication dosing question.

Medication question:
{question_text}

Return your answer ONLY in valid JSON using this schema:
{{
  "reasoning": "2-4 sentences explaining your reasoning",
  "decision": "A | B | C",
  "confidence": 1-10
}}

Decision mapping:
A = YES
B = NO
C = AMBIGUOUS

Guidelines:
- Use AMBIGUOUS if the information is incomplete, conflicting, or not sufficient for a
confident answer.
- Do not include any text outside the JSON object.
"""


def build_decision_prompt(question_text):
    return f"""You are answering an over-the-counter medication dosing question.

Medication question:
{question_text}

Choose exactly one decision:
A
B
C

Decision mapping:
A = YES
B = NO
C = AMBIGUOUS

Decision:"""


def format_chat_prompt(tokenizer, prompt):
    messages = [{"role": "user", "content": prompt}]
    if tokenizer.chat_template:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return prompt


def extract_json_object(text):
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None

def normalize_decision(value):
    if value is None:
        return "INVALID"

    value = str(value).strip().upper()

    mapping = {
        "A": "YES",
        "B": "NO",
        "C": "AMBIGUOUS"
    }

    return mapping.get(value, "INVALID")


def normalize_confidence(value):
    try:
        value = int(value)
        if 1 <= value <= 10:
            return value
    except Exception:
        pass
    return None


def decision_confidence_scores(model, tokenizer, question_text):
    prompt = build_decision_prompt(question_text) + """

Estimate the relative probability of each decision. Return non-negative
numbers for p_yes, p_no, and p_ambiguous that sum to 1.
"""
    request = {
        "model": MODEL_NAME,
        "input": prompt,
        "max_output_tokens": MAX_NEW_TOKENS,
        "text": PROBABILITY_FORMAT,
        "store": False,
        "temperature": TEMPERATURE
    }
    if MODEL_NAME.startswith("gpt-5"):
        request["reasoning"] = {"effort": "none"}

    response = model.responses.create(**request)
    parsed = json.loads(response.output_text)

    probs = [
        max(0.0, float(parsed["p_yes"])),
        max(0.0, float(parsed["p_no"])),
        max(0.0, float(parsed["p_ambiguous"]))
    ]
    total = sum(probs)
    if total <= 0:
        raise ValueError("The API returned decision probabilities that sum to zero")
    p_yes, p_no, p_ambiguous = [p / total for p in probs]

    prob_dict = {
        "YES": p_yes,
        "NO": p_no,
        "AMBIGUOUS": p_ambiguous
    }

    predicted_label = max(prob_dict, key=prob_dict.get)
    confidence = prob_dict[predicted_label]

    sorted_probs = sorted(prob_dict.values(), reverse=True)
    margin = sorted_probs[0] - sorted_probs[1]

    entropy = -sum(p * math.log(p + 1e-12) for p in prob_dict.values())
    entropy_normalized = entropy / math.log(3)

    return {
        "p_yes": p_yes,
        "p_no": p_no,
                "p_ambiguous": p_ambiguous,
        "decision_candidate_probs": prob_dict,
        "decision_probability_prediction": predicted_label,
        "decision_confidence": confidence,
        "decision_entropy": entropy,
        "decision_entropy_normalized": entropy_normalized,
        "decision_margin": margin
    }

def generate_answer(model, tokenizer, prompt):
    request = {
        "model": MODEL_NAME,
        "input": prompt,
        "max_output_tokens": MAX_NEW_TOKENS,
        "text": ANSWER_FORMAT,
        "store": False,
        "temperature": TEMPERATURE
    }
    if MODEL_NAME.startswith("gpt-5"):
        request["reasoning"] = {"effort": "none"}

    response = model.responses.create(**request)
    raw_output = response.output_text.strip()

    return {
        "raw_output": raw_output,
        "generated_sum_logprob": None,
        "generated_avg_logprob": None,
        "generated_avg_token_probability": None,
        "generated_perplexity_like": None
    }

def text_likelihood(model, tokenizer, context_prompt, target_text):
    return {
        "sum_logprob": None,
        "avg_logprob": None,
        "avg_token_probability": None,
        "perplexity_like": None
    }

def safe_mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None

def build_case_summary(all_runs):
    grouped = defaultdict(list)

    for row in all_runs:
        grouped[row["case_id"]].append(row)

    summaries = []

    for case_id, rows in grouped.items():
        decisions = [r["parsed_decision"] for r in rows if r["parsed_decision"] != "INVALID"]
        if decisions:
            majority_decision = Counter(decisions).most_common(1)[0][0]
            agreement = decisions.count(majority_decision) / len(decisions)
        else:
            majority_decision = "INVALID"
            agreement = 0

        gold_answer = rows[0].get("gold_answer")
        majority_correct = majority_decision == gold_answer
        if agreement == 1.0:
            consistency_score = 2
        elif agreement >= 0.6:
            consistency_score = 1
        else:
            consistency_score = 0

        summaries.append({
            "case_id": case_id,
            "drug_focus": rows[0].get("drug_focus"),
            "question_text": rows[0].get("question_text"),
            "gold_answer": gold_answer,
            "error_category": rows[0].get("error_category"),

            "majority_decision": majority_decision,
            "majority_correct": int(majority_correct),

            "agreement": agreement,
            "consistency_score": consistency_score,

            "avg_decision_confidence": safe_mean([r["decision_confidence"] for r in rows]),
            "avg_decision_entropy": safe_mean([r["decision_entropy"] for r in rows]),
            "avg_decision_margin": safe_mean([r["decision_margin"] for r in rows]),

            "avg_reasoning_avg_logprob": safe_mean([r["reasoning_avg_logprob"] for r in rows]),
            "avg_reasoning_perplexity_like": safe_mean([r["reasoning_perplexity_like"] for r in rows]),

            "manual_verifiability_score": None,
            "manual_error_type": None,

            "num_runs": len(rows)
        })

    return summaries

def main():
    print("Loading model...")

    tokenizer = None
    model = OpenAI()

    cases = load_cases(INPUT_CASES_FILE)

    all_runs = []

    for case in tqdm(cases):
        for run_id in range(1, NUM_RUNS + 1):
            question_text = case["question_text"]
            prompt = build_prompt(question_text)

            generation = generate_answer(model, tokenizer, prompt)
            parsed = extract_json_object(generation["raw_output"]) or {}

            parsed_reasoning = parsed.get("reasoning")
            parsed_decision = normalize_decision(parsed.get("decision"))
            parsed_confidence = normalize_confidence(parsed.get("confidence"))

            decision_scores = decision_confidence_scores(model, tokenizer, question_text)
            reasoning_scores = text_likelihood(model, tokenizer, prompt, parsed_reasoning)
            parse_status = "valid"
            if parsed_decision == "INVALID":
                parse_status = "invalid_json_schema"

            row = {
                "case_id": case.get("case_id"),

                "run_id": run_id,
                "model": MODEL_NAME,

                "drug_focus": case.get("drug_focus"),
                "question_text": question_text,
                "gold_answer": case.get("gold_answer"),
                "error_category": case.get("error_category"),

                "raw_output": generation["raw_output"],
                "parse_status": parse_status,

                "parsed_decision": parsed_decision,
                "parsed_verbal_confidence": parsed_confidence,

                "decision_confidence": decision_scores["decision_confidence"],
                "decision_entropy": decision_scores["decision_entropy"],
                "decision_margin": decision_scores["decision_margin"],

                "reasoning_avg_logprob": reasoning_scores["avg_logprob"],
                "reasoning_perplexity_like": reasoning_scores["perplexity_like"],

                "is_correct": parsed_decision == case.get("gold_answer")
            }

            all_runs.append(row)

            print(
                f"Case {case.get('case_id')} run {run_id}: "
                f"parsed={parsed_decision}, "
                f"gold={case.get('gold_answer')}, "
                f"conf={row['decision_confidence']:.3f}, "
                f"margin={row['decision_margin']:.3f}"
            )
            summaries = build_case_summary(all_runs)

    # with open(OUTPUT_RUNS_FILE, "w", encoding="utf-8") as f:
    #     json.dump(all_runs, f, indent=2, ensure_ascii=False)

    # with open(OUTPUT_SUMMARY_FILE, "w", encoding="utf-8") as f:
    #     json.dump(summaries, f, indent=2, ensure_ascii=False)

    pd.DataFrame(all_runs).to_csv(OUTPUT_RUNS_CSV_FILE, index=False)
    pd.DataFrame(summaries).to_csv(OUTPUT_SUMMARY_CSV_FILE, index=False)

    # print(f"\nSaved run-level results to {OUTPUT_RUNS_FILE}")
    # print(f"Saved case-level summary to {OUTPUT_SUMMARY_FILE}")
    print(f"Saved run-level CSV to {OUTPUT_RUNS_CSV_FILE}")
    print(f"Saved case-level summary CSV to {OUTPUT_SUMMARY_CSV_FILE}")


if __name__ == "__main__":
    main();
