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
    r"alcohol|beer|wine|liquor|drank|drinking|cbd|cannabis|weed|marijuana|"
    r"interaction|mixed?\s+with|combin(?:e|ing)|"
    r"substitut(?:e|ing)|replace|different\s+(?:drug|medicine|medication)|"
    r"how\s+many\s+(?:mg|milligrams?|pills?|tablets?|capsules?|doses?)|"
    r"how\s+much\s+(?!time\b)(?:acetaminophen|tylenol|paracetamol|apap|"
    r"panadol|ibuprofen|advil|motrin|nurofen|brufen)|"
    r"(?:increase|higher|double)\s+(?:the\s+)?dos(?:e|age)"
    r")\b",
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
_PRIOR_DOSE_VERB_SOURCE = (
    r"(?<!haven't\s)(?<!hasn't\s)(?<!hadn't\s)"
    r"(?<!not\s)(?<!never\s)"
    r"(?:took|taken|used|swallowed|ingested)"
)

_HIGH_RECALL_QUESTION_RE = re.compile(
    rf"(?:\?|{_QUESTION_LEAD_SOURCE})",
    re.IGNORECASE,
)
_HIGH_RECALL_REPEAT_RE = re.compile(
    rf"\b{_REPEAT_CUE_SOURCE}\b",
    re.IGNORECASE,
)
_HIGH_RECALL_TIME_RE = re.compile(
    r"\b(?:"
    r"(?:\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve)\s*(?:minutes?|mins?|hours?|hrs?|days?)\s*ago|"
    r"earlier|today|tonight|this\s+morning|this\s+afternoon|"
    r"last\s+night|yesterday|wait|after|before|until|between|"
    r"same\s+day|next\s+dose|last\s+dose|previous\s+dose"
    r")\b",
    re.IGNORECASE,
)
_HIGH_RECALL_ACTION_RE = re.compile(
    r"\b(?:"
    r"take|taking|took|taken|use|using|used|have|having|had|"
    r"dose|dosage|pill|tablet|capsule|mg|milligrams?"
    r")\b",
    re.IGNORECASE,
)


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


def _sentence_windows(title: str, body: str) -> list[str]:
    """Return unique one- and two-sentence windows, including title context."""
    units = [title.strip()] if title.strip() else []
    units.extend(
        part.strip() for part in _SENTENCE_SPLIT_RE.split(body) if part.strip()
    )
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
    if _EXCLUDED_REPEAT_INTENT_RE.search(title):
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
                if _EXCLUDED_REPEAT_INTENT_RE.search(context):
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
                if _EXCLUDED_REPEAT_INTENT_RE.search(context):
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
                if _EXCLUDED_REPEAT_INTENT_RE.search(context):
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

    reason = "excluded_repeat_intent" if rejected_intent else "no_repeat_question"
    return None, reason


def _high_recall_signals(text: str) -> dict[str, list[str]]:
    """Return the broad, auditable signals used by the medium-confidence tier."""
    return {
        "question": cfg.find_all_matches(_HIGH_RECALL_QUESTION_RE, text),
        "action": cfg.find_all_matches(_HIGH_RECALL_ACTION_RE, text),
        "repeat": cfg.find_all_matches(_HIGH_RECALL_REPEAT_RE, text),
        "time": cfg.find_all_matches(_HIGH_RECALL_TIME_RE, text),
    }


def find_high_recall_candidate(
    title: str,
    body: str,
    compiled_rules: dict[str, dict],
) -> tuple[dict | None, str]:
    """
    Find a medium-confidence candidate using a recall-oriented signal bundle.

    A two-sentence window must contain a research target, a dosing action, a
    question signal, and at least one repeat or time signal. The exact grammar
    is intentionally flexible; downstream records retain every matched signal
    so this lower-precision tier remains auditable.
    """
    if _EXCLUDED_REPEAT_INTENT_RE.search(title):
        return None, "excluded_repeat_intent"

    rejected_intent = False
    for window in _sentence_windows(title, body):
        matched_targets = []
        for medicine, rules in compiled_rules.items():
            matches = list(rules["aliases"].finditer(window))
            if matches:
                matched_targets.append((medicine, rules, matches))
        if not matched_targets:
            continue

        signals = _high_recall_signals(window)
        if (
            not signals["question"]
            or not signals["action"]
            or (not signals["repeat"] and not signals["time"])
        ):
            continue

        if _EXCLUDED_REPEAT_INTENT_RE.search(window):
            rejected_intent = True
            continue

        signal_matches = list(_HIGH_RECALL_ACTION_RE.finditer(window))
        signal_matches.extend(_HIGH_RECALL_REPEAT_RE.finditer(window))
        signal_matches.extend(_HIGH_RECALL_TIME_RE.finditer(window))

        def distance_to_signal(item) -> int:
            _, _, medicine_matches = item
            return min(
                abs(medicine_match.start() - signal_match.start())
                for medicine_match in medicine_matches
                for signal_match in signal_matches
            )

        matched_targets.sort(key=distance_to_signal)
        medicine, rules, _ = matched_targets[0]
        target_medicines = [item[0] for item in matched_targets]
        score = 0.75 if signals["repeat"] and signals["time"] else 0.65
        return {
            "target_medicine": medicine,
            "target_medicines": target_medicines,
            "rule_id": "high_recall_signal_combination",
            "confidence": "medium",
            "candidate_score": score,
            "prior_dose_text": None,
            "time_expressions": signals["time"],
            "target_terms": cfg.find_all_matches(rules["aliases"], window),
            "matched_signals": signals,
            "question_text": window,
            "context_text": window,
        }, "matched"

    reason = "excluded_repeat_intent" if rejected_intent else "no_repeat_question"
    return None, reason


def filter_batch(
    posts: list[dict],
    dosing_terms: list,
    exclude_terms: list,
    other_medicine_terms: dict[str, list[str]] | None = None,
    medicine_terms: dict[str, list[str]] | None = None,
) -> tuple[list[dict], dict]:
    """
    Apply the other-medicine, off-topic, and repeat-dose intent filters.

    Strict deterministic matches are retained as high-confidence candidates.
    A broad signal bundle adds medium-confidence candidates for high-recall
    collection. `dosing_terms` remains descriptive evidence and is not, by
    itself, sufficient to qualify a post.
    """
    dosing_re = cfg.build_pattern(dosing_terms)
    exclude_re = cfg.build_pattern(exclude_terms)
    repeat_dose_rules = _compile_repeat_dose_rules(
        medicine_terms
        or {
            "acetaminophen": [
                "acetaminophen",
                "tylenol",
                "paracetamol",
                "apap",
                "panadol",
            ],
            "ibuprofen": [
                "ibuprofen",
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
    by_other_medicine: dict[str, int] = {}
    by_medicine: dict[str, int] = {}
    by_repeat_dose_rule: dict[str, int] = {}
    by_confidence: dict[str, int] = {}

    for post in posts:
        title = post.get("title_clean")
        if title is None:
            title = post.get("title", "") or ""
        body = post.get("body_clean")
        if body is None:
            body = post.get("body", "") or ""
        text = post.get("clean_text") or f"{title} {body}"

        matched_other_medicines = [
            medicine
            for medicine, pattern in other_medicine_patterns.items()
            if pattern.search(title) or pattern.search(body)
        ]
        if matched_other_medicines:
            flagged_other_medicine += 1
            for medicine in matched_other_medicines:
                by_other_medicine[medicine] = (
                    by_other_medicine.get(medicine, 0) + 1
                )
            continue

        if exclude_re.search(text):
            flagged_excluded += 1
            continue

        repeat_evidence, rejection_reason = find_repeat_dose_question(
            title, body, repeat_dose_rules
        )
        confidence = "high"
        candidate_score = 1.0
        if repeat_evidence is None:
            if rejection_reason == "excluded_repeat_intent":
                flagged_excluded_intent += 1
                continue

            repeat_evidence, rejection_reason = find_high_recall_candidate(
                title, body, repeat_dose_rules
            )
            if repeat_evidence is None:
                if rejection_reason == "excluded_repeat_intent":
                    flagged_excluded_intent += 1
                else:
                    no_repeat_dose_question += 1
                continue
            confidence = "medium"
            candidate_score = repeat_evidence["candidate_score"]
        else:
            repeat_evidence["confidence"] = confidence
            repeat_evidence["candidate_score"] = candidate_score
            repeat_evidence["matched_signals"] = _high_recall_signals(
                repeat_evidence.get("context_text", "")
            )

        dosing_matches = cfg.find_all_matches(dosing_re, text)
        medicine = repeat_evidence["target_medicine"]
        by_medicine[medicine] = by_medicine.get(medicine, 0) + 1
        by_confidence[confidence] = by_confidence.get(confidence, 0) + 1
        rule_id = repeat_evidence["rule_id"]
        by_repeat_dose_rule[rule_id] = by_repeat_dose_rule.get(rule_id, 0) + 1

        candidate = dict(post)
        candidate["matched_dosing_terms"] = dosing_matches
        candidate["medicine_category"] = medicine
        candidate["repeat_dose_evidence"] = repeat_evidence
        candidate["candidate_confidence"] = confidence
        candidate["candidate_score"] = candidate_score
        candidate["matched_signals"] = repeat_evidence["matched_signals"]
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
        "by_confidence": by_confidence,
    }
    return candidates, stats


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
    by_other_medicine: dict[str, int] = {}
    by_medicine: dict[str, int] = {}
    by_repeat_dose_rule: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    for recs, st in batch_results:
        candidates.extend(recs)
        flagged_other_medicine += st["flagged_other_medicine"]
        flagged_excluded += st["flagged_excluded"]
        flagged_excluded_intent += st["flagged_excluded_intent"]
        no_repeat_dose_question += st["no_repeat_dose_question"]
        for med, n in st["by_other_medicine"].items():
            by_other_medicine[med] = by_other_medicine.get(med, 0) + n
        for med, n in st["by_medicine"].items():
            by_medicine[med] = by_medicine.get(med, 0) + n
        for rule_id, n in st["by_repeat_dose_rule"].items():
            by_repeat_dose_rule[rule_id] = (
                by_repeat_dose_rule.get(rule_id, 0) + n
            )
        for confidence, n in st["by_confidence"].items():
            by_confidence[confidence] = by_confidence.get(confidence, 0) + n

    cfg.write_json(cfg.step_path(cfg.DIR_STEP3, subreddit), candidates)

    stats = {
        "input":                    len(posts),
        "flagged_other_medicine":   flagged_other_medicine,
        "by_other_medicine":        by_other_medicine,
        "flagged_excluded":         flagged_excluded,
        "flagged_excluded_intent":  flagged_excluded_intent,
        "no_repeat_dose_question":  no_repeat_dose_question,
        "candidates":               len(candidates),
        "by_medicine":              by_medicine,
        "by_repeat_dose_rule":      by_repeat_dose_rule,
        "by_confidence":             by_confidence,
    }
    cfg.update_summary(subreddit, "step3_filter", stats)
    print(f"[step3] r/{subreddit}: {len(candidates):,} candidates / {len(posts):,}")
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
