import re

from joblib import Parallel, delayed

import step0_config as cfg


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TIME_RE = re.compile(
    r"\b(?:"
    r"(?:\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve)\s*(?:minutes?|mins?|hours?|hrs?|days?)\s*ago|"
    r"at\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?|"
    r"earlier|today|tonight|this\s+morning|this\s+afternoon|"
    r"last\s+night|yesterday|last\s+dose|previous\s+dose|next\s+dose|"
    r"again|another\s+dose|how\s+long|how\s+soon|when\s+can"
    r")\b",
    re.IGNORECASE,
)
_ELAPSED_OR_SCHEDULE_RE = re.compile(
    r"\b(?:"
    r"(?:\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve)\s*(?:minutes?|mins?|hours?|hrs?|days?)\s*ago|"
    r"at\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?|"
    r"earlier|today|tonight|tomorrow|right\s+now|this\s+morning|"
    r"this\s+afternoon|last\s+night|yesterday|"
    r"last\s+dose|previous\s+dose|next\s+dose"
    r")\b",
    re.IGNORECASE,
)
_EXCLUDED_REPEAT_INTENT_RE = re.compile(
    r"\b(?:"
    r"alcohol|beer|wine|liquor|drink|drinks|drank|drinking|drunk|hangover|"
    r"cbd|cannabis|weed|marijuana|"
    r"different\s+(?:drug|medicine|medication)"
    r")\b",
    re.IGNORECASE,
)
_CONDITIONAL_TRANSITION_INTENT_RE = re.compile(
    r"\b(?:mix(?:ed|ing)?\s+with|combin(?:e|ing)|substitut(?:e|ing)|"
    r"replac(?:e|ing))\b",
    re.IGNORECASE,
)
_TARGET_PAIR_REPLACEMENT_RE = re.compile(
    r"\b(?:substitut(?:e|ing)|replac(?:e|ing))\b",
    re.IGNORECASE,
)
_TARGET_PAIR_COMBINATION_RE = re.compile(
    r"\b(?:mix(?:ed|ing)?\s+with|combin(?:e|ing))\b",
    re.IGNORECASE,
)
_TARGET_PAIR_TIMING_RE = re.compile(
    r"\b(?:"
    r"alternat(?:e|ing)|after|before|wait|between|interval|gap|schedule|"
    r"another|next|second|again|every\s+\d+(?:\.\d+)?\s*(?:hours?|hrs?)"
    r")\b",
    re.IGNORECASE,
)
_CONTEXTUAL_STRONG_TARGET_SWITCH_RE = re.compile(
    r"\b(?:switch(?:ing)?|alternat(?:e|ing)|instead\s+of|"
    r"replac(?:e|ing)|substitut(?:e|ing))\b",
    re.IGNORECASE,
)

_QUESTION_LEAD_SOURCE = (
    r"(?:"
    r"\b(?:can|could|should|may)\s+"
    r"(?:i|we|you|he|she|they|one|someone)\b|"
    r"\bwould\b(?=\s+(?:(?:i|we|you|he|she|they|one|someone)\b|"
    r"(?:taking|having|using)\b))|"
    r"\b(?:am\s+i|are\s+(?:we|you|they)|is\s+it)\b|"
    r"\bwhen\s+(?:can|could|should|may|would|is|do)\b|"
    r"\bhow\s+(?:soon|long)\b"
    r")"
)
_REPEAT_CUE_SOURCE = (
    r"(?:"
    r"again|(?<!no\s)(?<!not\s)more|"
    r"another(?:\s+(?:dose|pill|tablet|capsule|time))?|"
    r"next(?:\s+(?:dose|pill|tablet|capsule))?|"
    r"second(?:\s+(?:dose|pill|tablet|capsule|time|gram))?|"
    r"re[-\s]?(?:take|dose)"
    r")"
)
_REPEAT_TO_TARGET_GAP_SOURCE = (
    r"\s+(?:(?:\d+(?:\.\d+)?\s*"
    r"(?:mg|milligrams?|g|grams?)\s*)?(?:of\s+)?)"
)
_POST_TARGET_REPEAT_SOURCE = r"(?:again|another\s+time)"
_DOSE_ACTION_SOURCE = (
    r"(?:"
    r"take|taking|use|using|dose|dosing|"
    r"pill|tablet|capsule|gram|re[-\s]?(?:take|dose)"
    r")"
)
_SAFETY_SOURCE = r"(?:safe|ok(?:ay)?|alright|dangerous|recommended)"
# Single-dose ("how much can I take") dosing questions. These broaden the scope
# beyond repeat-dose intent to any amount/limit question about a research
# target, while still requiring an explicit dosing question, not a bare mention.
_DOSE_AMOUNT_UNIT_SOURCE = (
    r"(?:mg|milligrams?|g|grams?|tablets?|pills?|caplets?|capsules?|doses?)"
)
_DOSING_AMOUNT_CUE_SOURCE = (
    r"(?:take|taking|have|use|using|safe|ok(?:ay)?|alright|too\s+much|"
    r"overdose|mg|milligrams?|grams?|dose|dosage|per\s+day|a\s+day|daily|"
    r"at\s+once|in\s+24\s*(?:hours?|hrs?)|each\s+time|max(?:imum)?)"
)
_PRIOR_DOSE_VERB_SOURCE = (
    r"(?<!haven't\s)(?<!hasn't\s)(?<!hadn't\s)"
    r"(?<!not\s)(?<!never\s)"
    r"(?:took|taken|used|swallowed|ingested)"
)
_CONTEXTUAL_QUESTION_RE = re.compile(
    rf"(?:\?|{_QUESTION_LEAD_SOURCE}|"
    r"\b(?:safe|ok(?:ay)?|alright|dangerous)\s+to\b)",
    re.IGNORECASE,
)
_CONTEXTUAL_ACTION_RE = re.compile(
    rf"\b{_DOSE_ACTION_SOURCE}\b|\b(?:have|having|had|swallow(?:ed|ing)?|"
    r"ingest(?:ed|ing)?)\b",
    re.IGNORECASE,
)
_CONTEXTUAL_SAFETY_RE = re.compile(
    r"\b(?:safe|ok(?:ay)?|alright|dangerous|recommended)\b",
    re.IGNORECASE,
)
_CONTEXTUAL_DECISION_RE = re.compile(
    rf"(?:\?|{_QUESTION_LEAD_SOURCE}|"
    r"\bdo\s+(?:i|we|you|they)\b|"
    r"\b(?:safe|ok(?:ay)?|alright|dangerous|recommended)\b)",
    re.IGNORECASE,
)

# ── Decidability tags ────────────────────────────────────────────────────────
# A candidate is annotation-decidable (a YES/NO is computable under the frozen
# Drug Facts labels) only when the post supplies the facts a decision needs:
#   • interval    — a prior dose taken at a stated time (→ min-interval check)
#   • rolling     — a prior dose with an amount and a time (→ rolling 24h total)
#   • single_dose — an explicit proposed amount (→ single-dose / 24h max check)
# Posts with none of these are structurally AMBIGUOUS ("how much can I take?"
# with no history or proposed amount) and are flagged so downstream annotation
# can keep only the decidable subset.
_DECIDE_AMOUNT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*"
    r"(?:mg|milligrams?|g|grams?|tablets?|pills?|caplets?|capsules?)\b",
    re.IGNORECASE,
)
_DECIDE_STRENGTH_RE = re.compile(r"\b(?:325|500|200)\s*mg\b", re.IGNORECASE)
_DECIDE_TIME_RE = re.compile(
    r"\b(?:"
    r"(?:\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve)\s*(?:minutes?|mins?|hours?|hrs?)\s*ago|"
    r"\d+(?:\.\d+)?\s*(?:hours?|hrs?)\b|"
    r"at\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)|"
    r"this\s+morning|this\s+afternoon|this\s+evening|last\s+night|"
    r"tonight|yesterday|earlier|last\s+dose|previous\s+dose|"
    r"a\s+few\s+hours\s+ago|couple\s+(?:of\s+)?hours\s+ago"
    r")\b",
    re.IGNORECASE,
)
_DECIDE_PRIOR_DOSE_RE = re.compile(
    r"\b(?:took|taken|had|used|swallowed|ingested|popped|"
    r"have\s+taken|had\s+taken|been\s+taking)\b",
    re.IGNORECASE,
)
_DECIDE_PROPOSED_AMOUNT_RE = re.compile(
    r"\b(?:take|have|use|do|pop|swallow|down)\b[^.?!]{0,40}"
    r"\d+(?:\.\d+)?\s*"
    r"(?:mg|milligrams?|tablets?|pills?|caplets?|capsules?)\b",
    re.IGNORECASE,
)


def _decidability(text: str) -> dict:
    """Tag which YES/NO reasoning axis (if any) the post supplies facts for."""
    has_amount = bool(_DECIDE_AMOUNT_RE.search(text))
    has_strength = bool(_DECIDE_STRENGTH_RE.search(text))
    has_time = bool(_DECIDE_TIME_RE.search(text))
    has_prior_dose = bool(_DECIDE_PRIOR_DOSE_RE.search(text))
    proposed_amount = bool(_DECIDE_PROPOSED_AMOUNT_RE.search(text))

    interval_decidable = has_prior_dose and has_time
    rolling_decidable = interval_decidable and has_amount
    single_dose_decidable = proposed_amount

    if rolling_decidable:
        axis = "rolling"
    elif interval_decidable:
        axis = "interval"
    elif single_dose_decidable:
        axis = "single_dose"
    else:
        axis = None

    return {
        "has_prior_dose": has_prior_dose,
        "has_time": has_time,
        "has_amount": has_amount,
        "has_strength": has_strength,
        "proposed_amount_stated": proposed_amount,
        "decidable_axis": axis,
        "decidable": axis is not None,
    }


def _term_source(terms: list[str]) -> str:
    """Return a longest-first, escaped alternation for medicine aliases."""
    unique = sorted(
        {term.strip() for term in terms if term and term.strip()},
        key=lambda term: (-len(term), term.lower()),
    )
    return "(?:" + "|".join(re.escape(term) for term in unique) + ")"


def _compile_repeat_dose_rules(
    medicine_terms: dict[str, list[str]],
) -> dict[str, dict]:
    """Compile deterministic same-medicine repeat-dose rules by target."""
    compiled: dict[str, dict] = {}
    for medicine, aliases in medicine_terms.items():
        if not aliases:
            continue
        alias_source = _term_source(aliases)
        target = rf"(?<![A-Za-z0-9]){alias_source}(?![A-Za-z0-9])"

        prior_dose = re.compile(
            rf"(?:"
            rf"\b(?:i|we|he|she|they)\b.{{0,30}}"
            rf"\b{_PRIOR_DOSE_VERB_SOURCE}\b.{{0,100}}{target}|"
            rf"\b{_PRIOR_DOSE_VERB_SOURCE}\b.{{0,100}}{target}|"
            rf"\b(?:i|we|he|she|they)\s+had\b.{{0,45}}{target}|"
            rf"\b(?:last|previous|first)\s+(?:dose|tablet|pill|capsule)\b"
            rf".{{0,80}}{target}|"
            rf"{target}.{{0,60}}"
            rf"(?:\b(?:dose|tablet|pill|capsule|took|taken|used)\b|"
            rf"\b\d+(?:\.\d+)?\s*(?:mg|milligrams?)\b).{{0,60}}"
            rf"\b(?:ago|earlier|already|last\s+night|"
            rf"this\s+morning|yesterday|last\s+dose|previous\s+dose)\b"
            rf")",
            re.IGNORECASE,
        )
        contextual_prior_dose = re.compile(
            rf"(?:"
            rf"\b{_PRIOR_DOSE_VERB_SOURCE}\b.{{0,140}}{target}|"
            rf"\b(?:i|we|he|she|they)\s+had\b.{{0,60}}{target}|"
            rf"{target}.{{0,90}}"
            rf"(?:\b(?:dose|tablet|pill|capsule|took|taken|used)\b|"
            rf"\b\d+(?:\.\d+)?\s*(?:mg|milligrams?)\b).{{0,90}}"
            rf"\b(?:ago|earlier|already|today|tonight|last\s+night|"
            rf"this\s+morning|yesterday|last\s+dose|previous\s+dose)\b|"
            rf"\bafter\s+{target}\b|"
            rf"\bafter\b.{{0,30}}\b(?:taking|took|having|had|using|used)\b"
            rf".{{0,50}}{target}"
            rf")",
            re.IGNORECASE,
        )
        contextual_explicit_repeat = re.compile(
            rf"(?:"
            rf"\b(?:again|re[-\s]?(?:take|dose))\b.{{0,70}}{target}|"
            rf"{target}.{{0,70}}\b(?:again|another\s+time|one\s+more)\b|"
            rf"\b(?:another|next|second|one\s+more)\b.{{0,55}}"
            rf"(?:\b(?:dose|pill|tablet|capsule)\b.{{0,25}})?{target}|"
            rf"\bmore\s+(?:(?:\d+(?:\.\d+)?\s*"
            rf"(?:mg|milligrams?)\s+)?(?:of\s+)?)?{target}|"
            rf"\b(?:another|next|second)\s+"
            rf"(?:dose|pill|tablet|capsule)\b.{{0,30}}(?:of\s+)?{target}|"
            rf"\bre[-\s]?(?:take|dose)\b.{{0,60}}{target}"
            rf")",
            re.IGNORECASE,
        )
        contextual_followup_question = re.compile(
            rf"(?:"
            rf"\b(?:take|have|use)\b.{{0,30}}"
            rf"\b(?:another|next|second)\s+"
            rf"(?:dose|pill|tablet|capsule)\b|"
            rf"\b(?:take|have|use)\b.{{0,30}}\bone\s+more\b"
            rf"(?:.{{0,20}}(?:{target}|"
            rf"\b(?:dose|pill|tablet|capsule)\b))?|"
            rf"\btake\s+more\b(?:.{{0,25}}{target})?|"
            rf"\b(?:take|have|use)\b.{{0,45}}"
            rf"(?:{target}|\bit\b|\bone\b).{{0,35}}"
            rf"\b(?:again|now|today|tonight)\b|"
            rf"\b(?:again|now|today|tonight)\b.{{0,45}}"
            rf"\b(?:take|have|use)\b.{{0,45}}"
            rf"(?:{target}|\bit\b|\bone\b|\bmore\b)|"
            rf"\bwait\b.{{0,100}}"
            rf"\b(?:another|next|second)\s+"
            rf"(?:dose|pill|tablet|capsule)\b"
            rf")",
            re.IGNORECASE,
        )
        contextual_interval_question = re.compile(
            rf"(?:"
            rf"\bhow\s+(?:long|soon|many\s+hours|much\s+time)\b"
            rf".{{0,140}}\bafter\b.{{0,90}}"
            rf"(?:\b(?:take|taking|took|have|having|had|use|using|used)\b"
            rf".{{0,55}})?{target}.{{0,140}}"
            rf"\b(?:take|have|use)\b.{{0,55}}"
            rf"(?:{target}|\bit\b|\bone\b|\bmore\b)|"
            rf"\bhow\s+(?:long|soon|many\s+hours|much\s+time)\b"
            rf".{{0,140}}\bwait\b.{{0,100}}\b(?:before|until)\b"
            rf".{{0,80}}\b(?:take|have|use)\b.{{0,55}}"
            rf"(?:{target}|\bit\b|\bone\b|\bmore\b)|"
            rf"\b(?:gap|interval)\b.{{0,100}}\bbetween\b.{{0,80}}"
            rf"(?:{target}.{{0,35}}\bdoses?\b|"
            rf"\bdoses?\b.{{0,35}}{target})|"
            rf"\bbetween\b.{{0,80}}(?:"
            rf"{target}.{{0,35}}\bdoses?\b|"
            rf"\bdoses?\b.{{0,35}}{target})|"
            rf"\b{target}\b.{{0,55}}\bdoses?\s+apart\b"
            rf")",
            re.IGNORECASE,
        )

        dosing_amount_question = re.compile(
            rf"(?:"
            # how much/how many <target> ... dosing cue
            rf"\bhow\s+(?:much|many)\b[^?.!]{{0,55}}{target}[^?.!]{{0,45}}"
            rf"\b{_DOSING_AMOUNT_CUE_SOURCE}\b|"
            # how much/how many ... dosing cue ... <target>
            # (e.g. "how many mg of tylenol")
            rf"\bhow\s+(?:much|many)\b[^?.!]{{0,25}}"
            rf"\b{_DOSING_AMOUNT_CUE_SOURCE}\b[^?.!]{{0,45}}{target}|"
            # max/maximum/safe/recommended dose|amount|limit of <target>
            rf"\b(?:max(?:imum)?|safe|recommended|normal|right|correct|proper|"
            rf"highest|daily|single)\b[^?.!]{{0,25}}"
            rf"\b(?:dose|dosage|amount|limit)\b[^?.!]{{0,45}}{target}|"
            rf"{target}[^?.!]{{0,45}}\b(?:max(?:imum)?|safe|recommended|highest|"
            rf"daily|single)\b[^?.!]{{0,25}}\b(?:dose|dosage|amount|limit)\b|"
            # can I take <N> mg/tablets (of) <target>
            rf"{_QUESTION_LEAD_SOURCE}[^?.!]{{0,45}}"
            rf"\b(?:take|have|use)\b[^?.!]{{0,30}}"
            rf"\d+(?:\.\d+)?\s*{_DOSE_AMOUNT_UNIT_SOURCE}"
            rf"[^?.!]{{0,25}}(?:of\s+)?{target}|"
            # is <N> mg (of) <target> too much/safe
            rf"\bis\b[^?.!]{{0,20}}\d+(?:\.\d+)?\s*{_DOSE_AMOUNT_UNIT_SOURCE}"
            rf"[^?.!]{{0,25}}(?:of\s+)?{target}[^?.!]{{0,45}}"
            rf"\b(?:safe|too\s+much|ok(?:ay)?|alright|fine|enough|dangerous|"
            rf"overdose)\b|"
            # <target> ... is <N> mg too much/safe (target stated first)
            rf"{target}[^?.!]{{0,30}}\bis\b[^?.!]{{0,20}}"
            rf"\d+(?:\.\d+)?\s*{_DOSE_AMOUNT_UNIT_SOURCE}[^?.!]{{0,35}}"
            rf"\b(?:safe|too\s+much|ok(?:ay)?|alright|fine|enough|dangerous)\b"
            rf")",
            re.IGNORECASE,
        )

        # The final boolean says whether the rule also needs an independently
        # detected prior dose of the same target in the two-sentence window.
        explicit_rules = [
            (
                "explicit_same_medicine_repeat_question",
                re.compile(
                    rf"(?:"
                    rf"{_QUESTION_LEAD_SOURCE}[^?!.]{{0,90}}"
                    rf"\b{_DOSE_ACTION_SOURCE}\b[^?!.]{{0,25}}"
                    rf"(?:"
                    rf"\b{_REPEAT_CUE_SOURCE}\b"
                    rf"{_REPEAT_TO_TARGET_GAP_SOURCE}{target}|"
                    rf"{target}\s+\b{_POST_TARGET_REPEAT_SOURCE}\b"
                    rf")|"
                    rf"{_QUESTION_LEAD_SOURCE}[^?!.]{{0,100}}"
                    rf"\bre[-\s]?(?:take|dose)\b[^?!.]{{0,45}}{target}|"
                    rf"(?:^|[?!.]\s+)\bis\b[^?!.]{{0,45}}"
                    rf"(?:\b{_DOSE_ACTION_SOURCE}\b[^?!.]{{0,35}})?"
                    rf"\b{_REPEAT_CUE_SOURCE}\b"
                    rf"{_REPEAT_TO_TARGET_GAP_SOURCE}{target}"
                    rf"[^?!.]{{0,60}}\b{_SAFETY_SOURCE}\b"
                    rf")",
                    re.IGNORECASE,
                ),
                False,
            ),
            (
                "same_medicine_interval_question",
                re.compile(
                    rf"(?:"
                    rf"\bhow\s+(?:long|soon|many\s+hours|much\s+time)\b"
                    rf"[^?]{{0,90}}\bafter\b[^?]{{0,70}}"
                    rf"(?:\b(?:take|taking|took|have|having|had|use|using|"
                    rf"used)\b[^?]{{0,45}})?{target}[^?]{{0,110}}"
                    rf"(?:"
                    rf"\b(?:can|could|should|may|would)\s+"
                    rf"(?:i|we|you|he|she|they|one)\b|"
                    rf"\bdo\s+(?:i|we|you|they)\b"
                    rf")[^?]{{0,45}}"
                    rf"\b(?:take|have|use)\b"
                    rf"\s+(?:(?:the|some)\s+)?"
                    rf"(?:{target}|\bit\b|\bone\b)|"
                    rf"\b(?:is\s+it\s+)?(?:safe|dangerous|ok(?:ay)?)\b"
                    rf".{{0,100}}\bwait\b.{{0,70}}\bbetween\b.{{0,60}}"
                    rf"(?:{target}.{{0,30}}\bdoses?\b|"
                    rf"\bdoses?\b.{{0,30}}{target})"
                    rf")",
                    re.IGNORECASE,
                ),
                False,
            ),
            (
                "when_take_same_medicine_again",
                re.compile(
                    rf"\bwhen\s+(?:can|could|should|may)\s+i\s+"
                    rf"(?:safely\s+)?(?:take|have|use)\b.{{0,50}}"
                    rf"{target}.{{0,30}}"
                    rf"\bagain\b",
                    re.IGNORECASE,
                ),
                True,
            ),
            (
                "wait_after_same_medicine_dose",
                re.compile(
                    rf"\bhow\s+(?:long|soon|many\s+hours|much\s+time)\b"
                    rf".{{0,100}}\bafter\b.{{0,50}}"
                    rf"\b(?:take|taking|took|have|having|had|use|using|used)\b"
                    rf".{{0,50}}{target}.{{0,120}}"
                    rf"\b(?:take|have|use)\b.{{0,50}}"
                    rf"(?:{target}|\bit\b).{{0,30}}\bagain\b",
                    re.IGNORECASE,
                ),
                False,
            ),
            (
                "wait_before_same_medicine_again",
                re.compile(
                    rf"\bhow\s+(?:long|soon|many\s+hours|much\s+time)\b"
                    rf".{{0,100}}\bwait\b.{{0,80}}\b(?:before|until)\b"
                    rf".{{0,60}}\b(?:take|taking|have|having|use|using)\b"
                    rf".{{0,45}}{target}.{{0,25}}"
                    rf"\b(?:again|next)\b",
                    re.IGNORECASE,
                ),
                True,
            ),
            (
                "take_more_same_medicine",
                re.compile(
                    rf"\b(?:can|could|should|may)\s+i\s+"
                    rf"(?:safely\s+|still\s+|now\s+)?"
                    rf"(?:take|have|use)\b.{{0,45}}"
                    rf"(?:"
                    rf"\bmore\b.{{0,25}}{target}|"
                    rf"\banother\b.{{0,55}}{target}|"
                    rf"{target}.{{0,30}}\b(?:again|another\s+time)\b"
                    rf")",
                    re.IGNORECASE,
                ),
                True,
            ),
            (
                "safe_to_take_same_medicine_again",
                re.compile(
                    rf"\bis\s+it\s+(?:safe|ok(?:ay)?|alright)\b.{{0,120}}"
                    rf"\b(?:take|have|use)\b.{{0,50}}{target}.{{0,30}}"
                    rf"\b(?:again|now|another\s+time)\b",
                    re.IGNORECASE,
                ),
                True,
            ),
            (
                "interval_between_same_medicine_doses",
                re.compile(
                    rf"(?:"
                    rf"\b(?:safe|minimum|recommended|right)\s+"
                    rf"(?:time\s+)?(?:gap|interval)\b.{{0,100}}\bbetween\b"
                    rf".{{0,60}}(?:"
                    rf"{target}.{{0,30}}\bdoses?\b|"
                    rf"\bdoses?\b.{{0,30}}{target}"
                    rf")|"
                    rf"\bhow\s+(?:many\s+hours|much\s+time|long)\b.{{0,100}}"
                    rf"\bbetween\b.{{0,60}}(?:"
                    rf"{target}.{{0,30}}\bdoses?\b|"
                    rf"\bdoses?\b.{{0,30}}{target}"
                    rf")"
                    rf")",
                    re.IGNORECASE,
                ),
                False,
            ),
            (
                "one_brand_to_another_same_medicine",
                re.compile(
                    rf"\bhow\s+(?:long|soon|much\s+time)\b.{{0,100}}"
                    rf"\bafter\b.{{0,60}}\b(?:take|taking|took)\b"
                    rf".{{0,60}}{target}.{{0,100}}"
                    rf"\b(?:take|taking)\b.{{0,50}}\banother\b.{{0,50}}"
                    rf"\bbrand\b",
                    re.IGNORECASE,
                ),
                False,
            ),
            (
                "consecutive_same_medicine_doses",
                re.compile(
                    rf"\bhow\s+(?:long|soon|many\s+hours|much\s+time)\b"
                    rf".{{0,100}}\b(?:wait|before|between)\b.{{0,80}}"
                    rf"\b(?:take|taking)?\b.{{0,30}}\bconsecutive\b"
                    rf".{{0,40}}{target}.{{0,30}}\bdoses?\b",
                    re.IGNORECASE,
                ),
                False,
            ),
            (
                "same_ingredient_product_interval",
                re.compile(
                    rf"\bhow\s+(?:long|soon|many\s+hours|much\s+time)\b"
                    rf".{{0,100}}\bafter\b.{{0,60}}\b(?:take|taking|took)\b"
                    rf".{{0,70}}\b(?:medication|medicine|product|brand)\b"
                    rf".{{0,40}}\bwith\b.{{0,30}}{target}.{{0,100}}"
                    rf"\b(?:before|until)\b.{{0,50}}\b(?:take|taking)\b"
                    rf".{{0,40}}\banother\b",
                    re.IGNORECASE,
                ),
                False,
            ),
        ]
        implicit_rules = [
            (
                "prior_dose_then_another_dose",
                re.compile(
                    r"\b(?:can|could|should|may)\s+i\b.{0,100}"
                    r"\b(?:take|have|use)\b.{0,45}"
                    r"\b(?:another|next|second|more)\b.{0,35}"
                    r"\b(?:dose|pill|tablet|capsule)s?\b",
                    re.IGNORECASE,
                ),
            ),
            (
                "prior_dose_then_wait_for_next",
                re.compile(
                    r"\b(?:how\s+(?:long|soon)|when\s+(?:can|could|should)\s+i)"
                    r"\b.{0,120}\b(?:wait|take|have|use)\b.{0,60}"
                    r"\b(?:another|next|second)\b.{0,30}"
                    r"\b(?:dose|pill|tablet|capsule)s?\b",
                    re.IGNORECASE,
                ),
            ),
            (
                "prior_dose_then_take_now",
                re.compile(
                    rf"(?:"
                    rf"{_QUESTION_LEAD_SOURCE}.{{0,100}}"
                    rf"\b(?:take|have|use)\b\s+"
                    rf"(?:(?:the|some)\s+)?"
                    rf"(?:{target}|\bit\b|\bone\b|\bmore\b).{{0,35}}"
                    rf"\b(?:now|today|tonight)\b|"
                    rf"\b(?:am\s+i|is\s+it|would\s+it)\b.{{0,55}}"
                    rf"\b{_SAFETY_SOURCE}\b.{{0,70}}"
                    rf"\b(?:take|have|use)\b\s+"
                    rf"(?:(?:the|some)\s+)?"
                    rf"(?:{target}|\bit\b|\bone\b|\bmore\b)"
                    rf".{{0,35}}\b(?:now|today|tonight|again)\b"
                    rf")",
                    re.IGNORECASE,
                ),
            ),
        ]
        compiled[medicine] = {
            "aliases": re.compile(target, re.IGNORECASE),
            "alias_source": target,
            "prior_dose": prior_dose,
            "contextual_prior_dose": contextual_prior_dose,
            "contextual_explicit_repeat": contextual_explicit_repeat,
            "contextual_followup_question": contextual_followup_question,
            "contextual_interval_question": contextual_interval_question,
            "dosing_amount_question": dosing_amount_question,
            "explicit_rules": explicit_rules,
            "implicit_rules": implicit_rules,
        }

    # Compile ordered transitions between research targets. These are allowed
    # even though they involve different active ingredients; transitions to any
    # non-target medicine remain unmatched (and other_medicine_terms still runs
    # before this classifier).
    for source_medicine, source_rules in compiled.items():
        switch_rules = []
        source = source_rules["alias_source"]
        for target_medicine, target_rules in compiled.items():
            if target_medicine == source_medicine:
                continue
            destination = target_rules["alias_source"]
            switch_rules.extend(
                [
                    (
                        target_medicine,
                        "switch_between_target_medicines",
                        re.compile(
                            rf"(?:"
                            rf"{_QUESTION_LEAD_SOURCE}[^?]{{0,100}}"
                            rf"\bswitch(?:ing)?\s+from\s+{source}"
                            rf"\s+to\s+{destination}\b|"
                            rf"\bis\s+switching\s+from\s+{source}\s+to\s+"
                            rf"{destination}.{{0,50}}\b{_SAFETY_SOURCE}\b"
                            rf")",
                            re.IGNORECASE,
                        ),
                    ),
                    (
                        target_medicine,
                        "replace_between_target_medicines",
                        re.compile(
                            rf"(?:"
                            rf"{_QUESTION_LEAD_SOURCE}[^?]{{0,100}}"
                            rf"\breplac(?:e|ing)\b.{{0,35}}{source}"
                            rf".{{0,25}}\bwith\b.{{0,25}}{destination}|"
                            rf"{_QUESTION_LEAD_SOURCE}[^?]{{0,100}}"
                            rf"\bsubstitut(?:e|ing)\b.{{0,35}}{source}"
                            rf".{{0,25}}\bwith\b.{{0,25}}{destination}|"
                            rf"{_QUESTION_LEAD_SOURCE}[^?]{{0,100}}"
                            rf"\bsubstitut(?:e|ing)\b.{{0,35}}{destination}"
                            rf".{{0,25}}\bfor\b.{{0,25}}{source}|"
                            rf"\bis\b[^?]{{0,50}}\breplacing\b.{{0,35}}"
                            rf"{source}.{{0,25}}\bwith\b.{{0,25}}"
                            rf"{destination}.{{0,50}}\b{_SAFETY_SOURCE}\b"
                            rf")",
                            re.IGNORECASE,
                        ),
                    ),
                    (
                        target_medicine,
                        "take_target_instead_of_other_target",
                        re.compile(
                            rf"(?:"
                            rf"{_QUESTION_LEAD_SOURCE}[^?]{{0,100}}"
                            rf"\b(?:take|have|use|taking|having|using)\b"
                            rf".{{0,45}}{destination}.{{0,40}}"
                            rf"\binstead\s+of\b.{{0,40}}{source}|"
                            rf"\bis\b.{{0,30}}\b(?:taking|having|using)\b"
                            rf".{{0,45}}{destination}.{{0,40}}"
                            rf"\binstead\s+of\b.{{0,40}}{source}"
                            rf".{{0,50}}\b{_SAFETY_SOURCE}\b"
                            rf")",
                            re.IGNORECASE,
                        ),
                    ),
                    (
                        target_medicine,
                        "alternate_between_target_medicines",
                        re.compile(
                            rf"(?:"
                            rf"{_QUESTION_LEAD_SOURCE}[^?]{{0,100}}"
                            rf"\balternat(?:e|ing)\b.{{0,35}}"
                            rf"{source}.{{0,35}}(?:and|with)\s+{destination}|"
                            rf"\bis\b.{{0,40}}\balternating\b.{{0,35}}"
                            rf"{source}.{{0,35}}(?:and|with)\s+{destination}"
                            rf".{{0,50}}\b{_SAFETY_SOURCE}\b"
                            rf")",
                            re.IGNORECASE,
                        ),
                    ),
                    (
                        target_medicine,
                        "prior_target_then_other_target",
                        re.compile(
                            rf"\b(?:i|we|he|she|they)\b.{{0,30}}"
                            rf"\b(?:{_PRIOR_DOSE_VERB_SOURCE}|had)\b"
                            rf".{{0,90}}{source}.{{0,180}}"
                            rf"(?:"
                            rf"{_QUESTION_LEAD_SOURCE}.{{0,90}}"
                            rf"\b(?:take|have|use)\b.{{0,55}}{destination}|"
                            rf"\b(?:is|would)\b.{{0,40}}{destination}"
                            rf".{{0,45}}\b{_SAFETY_SOURCE}\b"
                            rf")",
                            re.IGNORECASE,
                        ),
                    ),
                    (
                        target_medicine,
                        "interval_between_target_medicines",
                        re.compile(
                            rf"(?:"
                            rf"\bhow\s+(?:long|soon|many\s+hours|much\s+time)"
                            rf"\b.{{0,100}}\bafter\b.{{0,70}}"
                            rf"(?:\b(?:take|taking|took|have|having|had|use|"
                            rf"using|used)\b.{{0,50}})?{source}.{{0,130}}"
                            rf"(?:\b(?:can|could|should|may|would|do)\b"
                            rf".{{0,55}})?"
                            rf"\b(?:take|taking|have|having|use|using)\b"
                            rf".{{0,50}}{destination}|"
                            rf"{_QUESTION_LEAD_SOURCE}.{{0,100}}"
                            rf"\b(?:take|have|use|taking|having|using)\b"
                            rf".{{0,50}}{destination}.{{0,100}}"
                            rf"\bafter\b.{{0,90}}"
                            rf"(?:\b(?:take|taking|took|have|having|had|use|"
                            rf"using|used)\b.{{0,45}})?{source}"
                            rf")",
                            re.IGNORECASE,
                        ),
                    ),
                ]
            )
        source_rules["switch_rules"] = switch_rules
    return compiled


def _target_medicines_in(
    text: str,
    compiled_rules: dict[str, dict],
) -> list[str]:
    return [
        medicine
        for medicine, rules in compiled_rules.items()
        if rules["aliases"].search(text)
    ]


def _has_excluded_repeat_intent(
    text: str,
    compiled_rules: dict[str, dict],
) -> bool:
    """Reject out-of-scope intent while allowing target-to-target wording."""
    if _EXCLUDED_REPEAT_INTENT_RE.search(text):
        return True
    if not _CONDITIONAL_TRANSITION_INTENT_RE.search(text):
        return False

    target_medicines = _target_medicines_in(text, compiled_rules)
    if len(target_medicines) < 2:
        return True
    if _TARGET_PAIR_REPLACEMENT_RE.search(text):
        return False
    if (
        _TARGET_PAIR_COMBINATION_RE.search(text)
        and _TARGET_PAIR_TIMING_RE.search(text)
    ):
        return False
    return True


def _sentence_units(title: str, body: str) -> list[str]:
    units = [title.strip()] if title.strip() else []
    units.extend(
        part.strip() for part in _SENTENCE_SPLIT_RE.split(body) if part.strip()
    )
    return units


def _sentence_windows(title: str, body: str) -> list[str]:
    """Return unique one- and two-sentence windows, including title context."""
    units = _sentence_units(title, body)
    windows: list[str] = []
    seen: set[str] = set()
    for index, unit in enumerate(units):
        # Check the wider context first so a concise title cannot bypass an
        # overdose/interaction statement in the first body sentence.
        if index + 1 < len(units):
            separator = " " if re.search(r"[.!?]\s*$", unit) else ". "
            window = f"{unit}{separator}{units[index + 1]}"
        else:
            window = unit
        if window and window not in seen:
            seen.add(window)
            windows.append(window)
    return windows


def _context_around(text: str, start: int, end: int, radius: int = 220) -> str:
    return text[max(0, start - radius):min(len(text), end + radius)].strip()


def _local_question_windows_for_other_medicines(
    title: str,
    body: str,
) -> list[tuple[str, str]]:
    """Return local question context used only for other-medicine roles."""
    units = _sentence_units(title, body)
    windows: list[tuple[str, str]] = []
    for index, question_text in enumerate(units):
        if not _CONTEXTUAL_QUESTION_RE.search(question_text):
            continue
        if index == 0:
            context_units = units[:3]
            context = " ".join(context_units)[:650]
            local_question = question_text[:650]
        else:
            context_units = units[max(0, index - 2):index + 1]
            context = " ".join(context_units)[-650:]
            local_question = question_text[-650:]
        windows.append((local_question, context))
    return windows


def _contextual_question_windows(
    title: str,
    body: str,
) -> list[tuple[str, str]]:
    """Return every question unit paired with the full post context."""
    units = _sentence_units(title, body)
    context = " ".join(units)
    return [
        (question_text, context)
        for question_text in units
        if _CONTEXTUAL_QUESTION_RE.search(question_text)
    ]


def _other_medicines_in_question_context(
    title: str,
    body: str,
    other_medicine_patterns: dict[str, re.Pattern],
    compiled_rules: dict[str, dict],
) -> list[str]:
    """Find non-target medicines used as the asked-about or prior medicine."""
    matched: set[str] = set()
    for question_text, context in (
        _local_question_windows_for_other_medicines(title, body)
    ):
        if not _target_medicines_in(context, compiled_rules):
            continue
        for medicine, pattern in other_medicine_patterns.items():
            if pattern.search(question_text):
                matched.add(medicine)
                continue
            for item in pattern.finditer(context):
                prefix = context[max(0, item.start() - 120):item.start()]
                if re.search(
                    r"\b(?:took|taken|used|swallowed|ingested|had)\b",
                    prefix,
                    re.IGNORECASE,
                ):
                    matched.add(medicine)
                    break
                neighborhood = context[
                    max(0, item.start() - 100):min(
                        len(context),
                        item.end() + 100,
                    )
                ]
                if re.search(
                    r"\b(?:switch(?:ing)?|replac(?:e|ing)|"
                    r"substitut(?:e|ing)|instead\s+of|mix(?:ed|ing)?\s+with|"
                    r"combin(?:e|ing))\b",
                    neighborhood,
                    re.IGNORECASE,
                ):
                    matched.add(medicine)
                    break
    return sorted(matched)


def _contextual_transition(
    text: str,
    compiled_rules: dict[str, dict],
) -> tuple[str, str] | None:
    """Infer source and destination targets from their order in local text."""
    occurrences: list[tuple[int, str]] = []
    for medicine, rules in compiled_rules.items():
        occurrences.extend(
            (match.start(), medicine)
            for match in rules["aliases"].finditer(text)
        )
    occurrences.sort()
    ordered: list[str] = []
    for _, medicine in occurrences:
        if not ordered or ordered[-1] != medicine:
            ordered.append(medicine)
    if len(set(ordered)) < 2:
        return None
    return ordered[0], ordered[-1]


def _post_level_target_for_question(
    question_text: str,
    context: str,
    compiled_rules: dict[str, dict],
) -> str | None:
    """Choose the nearest post-level target when the question omits its name."""
    question_start = context.rfind(question_text)
    if question_start < 0:
        question_start = len(context)

    occurrences: list[tuple[int, str]] = []
    for medicine, rules in compiled_rules.items():
        occurrences.extend(
            (match.start(), medicine)
            for match in rules["aliases"].finditer(context)
        )
    if not occurrences:
        return None

    before_question = [
        item for item in occurrences if item[0] < question_start
    ]
    if before_question:
        return max(before_question)[1]
    return min(occurrences)[1]


def _has_direct_target_pair_transition(
    question_text: str,
    compiled_rules: dict[str, dict],
) -> bool:
    if len(_target_medicines_in(question_text, compiled_rules)) < 2:
        return False
    if _CONTEXTUAL_STRONG_TARGET_SWITCH_RE.search(question_text):
        return True
    if (
        _TARGET_PAIR_COMBINATION_RE.search(question_text)
        and _TARGET_PAIR_TIMING_RE.search(question_text)
    ):
        return True

    occurrences: list[tuple[int, int, str]] = []
    for medicine, rules in compiled_rules.items():
        occurrences.extend(
            (match.start(), match.end(), medicine)
            for match in rules["aliases"].finditer(question_text)
        )
    occurrences.sort()
    for left, right in zip(occurrences, occurrences[1:]):
        if left[2] == right[2]:
            continue
        between = question_text[left[1]:right[0]]
        if re.search(
            r"\b(?:after|before|then)\b",
            between,
            re.IGNORECASE,
        ):
            return True

    aliases = [
        rules["alias_source"]
        for rules in compiled_rules.values()
    ]
    if len(aliases) >= 2:
        for first in aliases:
            for second in aliases:
                if first == second:
                    continue
                if re.search(
                    rf"\bbetween\b.{{0,80}}{first}.{{0,45}}"
                    rf"(?:and|with)\s+{second}",
                    question_text,
                    re.IGNORECASE,
                ):
                    return True
    return False


def find_contextual_repeat_dose_question(
    title: str,
    body: str,
    compiled_rules: dict[str, dict],
) -> tuple[dict | None, bool]:
    """
    High-recall fallback using local signals instead of a fixed word order.

    It still requires a target-linked question plus either an explicit repeat
    cue, a target-specific prior dose, a dose interval, or a transition between
    the two configured research targets.
    """
    rejected_intent = False
    for question_text, context in _contextual_question_windows(title, body):
        if _has_excluded_repeat_intent(context, compiled_rules):
            rejected_intent = True
            continue

        context_medicines = _target_medicines_in(context, compiled_rules)
        if not context_medicines:
            continue

        question_medicines = _target_medicines_in(
            question_text,
            compiled_rules,
        )
        post_level_target = _post_level_target_for_question(
            question_text,
            context,
            compiled_rules,
        )
        transition = None
        if (
            len(question_medicines) >= 2
            and _has_direct_target_pair_transition(
                question_text,
                compiled_rules,
            )
        ):
            transition = _contextual_transition(
                question_text,
                compiled_rules,
            )
        elif len(question_medicines) == 1:
            destination = question_medicines[0]
            destination_rules = compiled_rules[destination]
            if destination_rules["contextual_followup_question"].search(
                question_text
            ):
                source = next(
                    (
                        medicine
                        for medicine in context_medicines
                        if medicine != destination
                        and compiled_rules[medicine][
                            "contextual_prior_dose"
                        ].search(context)
                    ),
                    None,
                )
                if source is not None:
                    transition = source, destination

        if transition is not None:
            source_medicine, target_medicine = transition
            source_rules = compiled_rules[source_medicine]
            target_rules = compiled_rules[target_medicine]
            return {
                "target_medicine": target_medicine,
                "source_medicine": source_medicine,
                "target_medicines": [
                    source_medicine,
                    target_medicine,
                ],
                "transition": (
                    f"{source_medicine}_to_{target_medicine}"
                ),
                "rule_id": "contextual_target_switch",
                "prior_dose_text": None,
                "time_expressions": cfg.find_all_matches(
                    _TIME_RE, context
                ),
                "source_terms": cfg.find_all_matches(
                    source_rules["aliases"], context
                ),
                "target_terms": cfg.find_all_matches(
                    target_rules["aliases"], context
                ),
                "question_text": question_text,
                "context_text": context,
            }, rejected_intent

        question_has_action = bool(
            _CONTEXTUAL_ACTION_RE.search(question_text)
        )
        for medicine in context_medicines:
            rules = compiled_rules[medicine]
            question_has_target = bool(
                rules["aliases"].search(question_text)
            )
            prior = rules["contextual_prior_dose"].search(context)
            explicit_repeat = rules["contextual_explicit_repeat"].search(
                question_text
            )

            if (
                question_has_target
                and explicit_repeat is not None
                and _CONTEXTUAL_DECISION_RE.search(question_text)
                and (
                    question_has_action
                    or _CONTEXTUAL_SAFETY_RE.search(question_text)
                )
            ):
                rule_id = "contextual_explicit_repeat_question"
            elif (
                rules["contextual_interval_question"].search(
                    question_text
                )
            ):
                rule_id = "contextual_dose_interval_question"
            elif (
                prior is not None
                and (
                    followup := rules[
                        "contextual_followup_question"
                    ].search(question_text)
                )
                and (
                    context.rfind(question_text) + followup.start()
                    >= prior.end()
                )
            ):
                rule_id = "contextual_prior_dose_followup"
            elif (
                not question_medicines
                and medicine == post_level_target
                and rules["contextual_followup_question"].search(
                    question_text
                )
            ):
                rule_id = "contextual_post_level_repeat_question"
            else:
                continue

            return {
                "target_medicine": medicine,
                "rule_id": rule_id,
                "prior_dose_text": (
                    prior.group().strip() if prior is not None else None
                ),
                "time_expressions": cfg.find_all_matches(_TIME_RE, context),
                "target_terms": cfg.find_all_matches(
                    rules["aliases"], context
                ),
                "question_text": question_text,
                "context_text": context,
            }, rejected_intent

    return None, rejected_intent


def find_repeat_dose_question(
    title: str,
    body: str,
    compiled_rules: dict[str, dict],
) -> tuple[dict | None, str]:
    """
    Find evidence for a same-medicine repeat-dose timing/safety question.

    Returns (evidence, reason). Evidence is returned only when a deterministic
    rule links the target medicine to a repeat-dose question. The reason is used
    for aggregate rejection statistics.
    """
    # The title normally states the question's intent. Rejecting these intents
    # up front prevents a later body-only window from bypassing the title.
    if _has_excluded_repeat_intent(title, compiled_rules):
        return None, "excluded_repeat_intent"

    rejected_intent = False
    for window in _sentence_windows(title, body):
        for source_medicine, source_rules in compiled_rules.items():
            for target_medicine, rule_id, pattern in source_rules[
                "switch_rules"
            ]:
                match = pattern.search(window)
                if not match:
                    continue
                context = _context_around(window, match.start(), match.end())
                if _has_excluded_repeat_intent(context, compiled_rules):
                    rejected_intent = True
                    continue
                target_rules = compiled_rules[target_medicine]
                return {
                    "target_medicine": target_medicine,
                    "source_medicine": source_medicine,
                    "target_medicines": [
                        source_medicine,
                        target_medicine,
                    ],
                    "transition": (
                        f"{source_medicine}_to_{target_medicine}"
                    ),
                    "rule_id": rule_id,
                    "prior_dose_text": (
                        match.group().strip()
                        if rule_id
                        in {
                            "prior_target_then_other_target",
                            "interval_between_target_medicines",
                        }
                        else None
                    ),
                    "time_expressions": cfg.find_all_matches(
                        _TIME_RE, context
                    ),
                    "source_terms": cfg.find_all_matches(
                        source_rules["aliases"], context
                    ),
                    "target_terms": cfg.find_all_matches(
                        target_rules["aliases"], context
                    ),
                    "question_text": match.group().strip(),
                    "context_text": context,
                }, "matched"

        for medicine, rules in compiled_rules.items():
            prior_matches = list(rules["prior_dose"].finditer(window))

            for rule_id, pattern, requires_prior in rules["explicit_rules"]:
                match = pattern.search(window)
                if not match:
                    continue
                prior = prior_matches[0] if prior_matches else None
                first_dose_sequence = False
                if requires_prior and prior is None:
                    # "another 500 mg ... if the first 500 mg did not work" is
                    # an explicit two-dose sequence even without "I took".
                    first_dose_sequence = (
                        rule_id == "take_more_same_medicine"
                        and re.search(
                            r"\bfirst\b.{0,80}\b(?:did(?:n't|\s+not)\s+work|"
                            r"wasn't\s+enough|dose|tablet|pill)\b",
                            window,
                            re.IGNORECASE,
                        )
                    )
                    if not first_dose_sequence:
                        continue
                context = _context_around(window, match.start(), match.end())
                if _has_excluded_repeat_intent(context, compiled_rules):
                    rejected_intent = True
                    continue
                time_terms = cfg.find_all_matches(_TIME_RE, context)
                if (
                    rule_id == "take_more_same_medicine"
                    and prior is not None
                    and not first_dose_sequence
                    and not _ELAPSED_OR_SCHEDULE_RE.search(context)
                ):
                    continue
                target_terms = cfg.find_all_matches(rules["aliases"], context)
                return {
                    "target_medicine": medicine,
                    "rule_id": rule_id,
                    "prior_dose_text": prior.group().strip() if prior else None,
                    "time_expressions": time_terms,
                    "target_terms": target_terms,
                    "question_text": match.group().strip(),
                    "context_text": context,
                }, "matched"

            for rule_id, pattern in rules["implicit_rules"]:
                match = pattern.search(window)
                if not match:
                    continue
                # An unnamed "another dose" can refer to the target only when a
                # target-specific prior-dose event appears before the question.
                prior = next(
                    (item for item in prior_matches if item.start() < match.start()),
                    None,
                )
                if prior is None:
                    continue
                context = _context_around(window, prior.start(), match.end())
                if _has_excluded_repeat_intent(context, compiled_rules):
                    rejected_intent = True
                    continue
                return {
                    "target_medicine": medicine,
                    "rule_id": rule_id,
                    "prior_dose_text": prior.group().strip(),
                    "time_expressions": cfg.find_all_matches(_TIME_RE, context),
                    "target_terms": cfg.find_all_matches(
                        rules["aliases"], context
                    ),
                    "question_text": match.group().strip(),
                    "context_text": context,
                }, "matched"

    contextual_evidence, contextual_rejected = (
        find_contextual_repeat_dose_question(
            title,
            body,
            compiled_rules,
        )
    )
    if contextual_evidence is not None:
        return contextual_evidence, "matched"
    rejected_intent = rejected_intent or contextual_rejected
    reason = "excluded_repeat_intent" if rejected_intent else "no_repeat_question"
    return None, reason


def find_dosing_amount_question(
    title: str,
    body: str,
    compiled_rules: dict[str, dict],
) -> dict | None:
    """
    Find a single-dose amount/limit question about a research target.

    This is a scope-broadening fallback used only after the repeat-dose rules
    fail. It keeps "how much X can I take", "max dose of X", and "is N mg of X
    too much" style questions that do not describe a prior dose. Off-topic
    intent (alcohol/cbd/mixing) is still rejected, and a non-target medicine
    used as the question subject is filtered downstream in ``filter_batch``.
    """
    if _has_excluded_repeat_intent(title, compiled_rules):
        return None
    for window in _sentence_windows(title, body):
        for medicine, rules in compiled_rules.items():
            match = rules["dosing_amount_question"].search(window)
            if not match:
                continue
            context = _context_around(window, match.start(), match.end())
            if _has_excluded_repeat_intent(context, compiled_rules):
                continue
            return {
                "target_medicine": medicine,
                "rule_id": "dosing_amount_question",
                "prior_dose_text": None,
                "time_expressions": cfg.find_all_matches(_TIME_RE, context),
                "target_terms": cfg.find_all_matches(rules["aliases"], context),
                "question_text": match.group().strip(),
                "context_text": context,
            }
    return None


def filter_batch(
    posts: list[dict],
    dosing_terms: list,
    exclude_terms: list,
    other_medicine_terms: dict[str, list[str]] | None = None,
    medicine_terms: dict[str, list[str]] | None = None,
) -> tuple[list[dict], dict]:
    """
    Apply the off-topic, repeat-dose intent, and contextual medicine filters.

    A post qualifies when either a strict deterministic rule or the local
    contextual fallback links a research target to an eligible re-dosing or
    target-switch question. `dosing_terms` remains descriptive evidence and is
    not, by itself, sufficient.
    """
    dosing_re = cfg.build_pattern(dosing_terms)
    exclude_re = cfg.build_pattern(exclude_terms)
    repeat_dose_rules = _compile_repeat_dose_rules(
        medicine_terms
        or {
            "acetaminophen": [
                "acetaminophen",
                "acetominophen",
                "acetaminaphen",
                "tylenol",
                "paracetamol",
                "apap",
                "panadol",
            ],
            "ibuprofen": [
                "ibuprofen",
                "ibuprophen",
                "ibufrofen",
                "ibufrofin",
                "advil",
                "motrin",
                "nurofen",
                "brufen",
            ],
        }
    )
    other_medicine_patterns = {
        medicine: cfg.build_pattern(synonyms)
        for medicine, synonyms in (other_medicine_terms or {}).items()
        if synonyms
    }

    candidates: list[dict] = []
    flagged_other_medicine = flagged_excluded = 0
    flagged_excluded_intent = no_repeat_dose_question = 0
    decidable_candidates = 0
    by_other_medicine: dict[str, int] = {}
    by_medicine: dict[str, int] = {}
    by_repeat_dose_rule: dict[str, int] = {}
    by_decidable_axis: dict[str, int] = {}

    for post in posts:
        title = post.get("title_clean")
        if title is None:
            title = post.get("title", "") or ""
        body = post.get("body_clean")
        if body is None:
            body = post.get("body", "") or ""
        text = post.get("clean_text") or f"{title} {body}"

        if exclude_re.search(text):
            flagged_excluded += 1
            continue

        matched_question_medicines = _other_medicines_in_question_context(
            title,
            body,
            other_medicine_patterns,
            repeat_dose_rules,
        )
        if matched_question_medicines:
            flagged_other_medicine += 1
            for other_medicine in matched_question_medicines:
                by_other_medicine[other_medicine] = (
                    by_other_medicine.get(other_medicine, 0) + 1
                )
            continue

        repeat_evidence, rejection_reason = find_repeat_dose_question(
            title, body, repeat_dose_rules
        )
        if repeat_evidence is None:
            if rejection_reason == "excluded_repeat_intent":
                flagged_excluded_intent += 1
                continue
            # Scope broadened: also keep single-dose amount/limit questions that
            # do not describe a prior dose (e.g. "how much X can I take?").
            repeat_evidence = find_dosing_amount_question(
                title, body, repeat_dose_rules
            )
            if repeat_evidence is None:
                no_repeat_dose_question += 1
                continue

        # Ignore unrelated medicines elsewhere in a long history or medication
        # list. Reject them only when they participate in the matched question
        # or in the prior-dose event used to resolve an unnamed follow-up.
        medicine_role_text = " ".join(
            part
            for part in (
                repeat_evidence.get("question_text"),
                repeat_evidence.get("prior_dose_text"),
            )
            if part
        )
        matched_other_medicines = [
            other_medicine
            for other_medicine, pattern in other_medicine_patterns.items()
            if pattern.search(medicine_role_text)
        ]
        if matched_other_medicines:
            flagged_other_medicine += 1
            for other_medicine in matched_other_medicines:
                by_other_medicine[other_medicine] = (
                    by_other_medicine.get(other_medicine, 0) + 1
                )
            continue

        dosing_matches = cfg.find_all_matches(dosing_re, text)
        medicine = repeat_evidence["target_medicine"]
        by_medicine[medicine] = by_medicine.get(medicine, 0) + 1
        rule_id = repeat_evidence["rule_id"]
        by_repeat_dose_rule[rule_id] = by_repeat_dose_rule.get(rule_id, 0) + 1

        decidability = _decidability(text)
        if decidability["decidable"]:
            decidable_candidates += 1
            axis = decidability["decidable_axis"]
            by_decidable_axis[axis] = by_decidable_axis.get(axis, 0) + 1

        candidate = dict(post)
        candidate["matched_dosing_terms"] = dosing_matches
        candidate["medicine_category"] = medicine
        candidate["repeat_dose_evidence"] = repeat_evidence
        candidate["decidability"] = decidability
        candidate["filter_status"] = "repeat_dose_candidate"
        candidates.append(candidate)

    stats = {
        "flagged_other_medicine": flagged_other_medicine,
        "by_other_medicine":      by_other_medicine,
        "flagged_excluded": flagged_excluded,
        "flagged_excluded_intent": flagged_excluded_intent,
        "no_repeat_dose_question": no_repeat_dose_question,
        "by_medicine": by_medicine,
        "by_repeat_dose_rule": by_repeat_dose_rule,
        "decidable": decidable_candidates,
        "undecidable": len(candidates) - decidable_candidates,
        "by_decidable_axis": by_decidable_axis,
    }
    return candidates, stats


def prepare_candidate_for_storage(candidate: dict) -> dict:
    """Remove filter-only metadata from a candidate before Step 3 persistence."""
    stored = dict(candidate)
    for field in (
        "medicine_category",
        "repeat_dose_evidence",
        "filter_status",
    ):
        stored.pop(field, None)
    return stored


def filter_one(subreddit: str) -> dict:
    """Filter one subreddit's posts_cleaned → posts_candidates. Returns stats."""
    keywords      = cfg.load_keywords()
    dosing_terms  = keywords["dosing_terms"]
    exclude_terms = keywords["exclude_terms"]
    medicine_terms = keywords["medicine_terms"]
    other_medicine_terms = keywords.get("other_medicine_terms", {})

    posts = cfg.read_json(cfg.step_path(cfg.DIR_STEP2, subreddit), default=None)
    if posts is None:
        raise FileNotFoundError(f"{cfg.DIR_STEP2}/{subreddit}.json not found")

    # Parallelize the regex filtering (order preserved); serial for small inputs.
    if len(posts) < cfg.MIN_PARALLEL_ROWS:
        batch_results = [
            filter_batch(
                posts,
                dosing_terms,
                exclude_terms,
                other_medicine_terms,
                medicine_terms,
            )
        ]
    else:
        batch_size = cfg.batch_size_for(len(posts))
        batch_results = Parallel(n_jobs=cfg.N_JOBS)(
            delayed(filter_batch)(
                chunk,
                dosing_terms,
                exclude_terms,
                other_medicine_terms,
                medicine_terms,
            )
            for chunk in cfg.chunked(posts, batch_size)
        )

    # Merge batches (order preserved).
    candidates: list[dict] = []
    flagged_other_medicine = flagged_excluded = 0
    flagged_excluded_intent = no_repeat_dose_question = 0
    decidable = undecidable = 0
    by_other_medicine: dict[str, int] = {}
    by_medicine: dict[str, int] = {}
    by_repeat_dose_rule: dict[str, int] = {}
    by_decidable_axis: dict[str, int] = {}
    for recs, st in batch_results:
        candidates.extend(recs)
        flagged_other_medicine += st["flagged_other_medicine"]
        flagged_excluded += st["flagged_excluded"]
        flagged_excluded_intent += st["flagged_excluded_intent"]
        no_repeat_dose_question += st["no_repeat_dose_question"]
        decidable += st["decidable"]
        undecidable += st["undecidable"]
        for med, n in st["by_other_medicine"].items():
            by_other_medicine[med] = by_other_medicine.get(med, 0) + n
        for med, n in st["by_medicine"].items():
            by_medicine[med] = by_medicine.get(med, 0) + n
        for rule_id, n in st["by_repeat_dose_rule"].items():
            by_repeat_dose_rule[rule_id] = (
                by_repeat_dose_rule.get(rule_id, 0) + n
            )
        for axis, n in st["by_decidable_axis"].items():
            by_decidable_axis[axis] = by_decidable_axis.get(axis, 0) + n

    stored_candidates = [
        prepare_candidate_for_storage(candidate)
        for candidate in candidates
    ]
    cfg.write_json(cfg.step_path(cfg.DIR_STEP3, subreddit), stored_candidates)

    stats = {
        "input":                    len(posts),
        "flagged_other_medicine":   flagged_other_medicine,
        "by_other_medicine":        by_other_medicine,
        "flagged_excluded":         flagged_excluded,
        "flagged_excluded_intent":  flagged_excluded_intent,
        "no_repeat_dose_question":  no_repeat_dose_question,
        "candidates":               len(candidates),
        "decidable":                decidable,
        "undecidable":              undecidable,
        "by_medicine":              by_medicine,
        "by_repeat_dose_rule":      by_repeat_dose_rule,
        "by_decidable_axis":        by_decidable_axis,
    }
    cfg.update_summary(subreddit, "step3_filter", stats)
    print(
        f"[step3] r/{subreddit}: {len(candidates):,} candidates "
        f"({decidable:,} decidable) / {len(posts):,}"
    )
    return stats


def run(subreddits: list[str] | None = None) -> None:
    subreddits = subreddits or cfg.load_subreddits()
    print(f"[step3] filter — subreddits: {subreddits}")
    for subreddit in subreddits:
        try:
            filter_one(subreddit)
        except FileNotFoundError as exc:
            print(f"[SKIP] r/{subreddit}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] r/{subreddit}: {exc}")


if __name__ == "__main__":
    run()
