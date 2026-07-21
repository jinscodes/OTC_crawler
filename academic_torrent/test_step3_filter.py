import unittest

import step3_filter


DOSING_TERMS = ["dose", "mg", "wait", "hours ago", "can I take"]
EXCLUDE_TERMS = ["meme"]
OTHER_MEDICINE_TERMS = {
    "aspirin": ["aspirin", "bayer"],
    "naproxen": ["naproxen", "aleve"],
}
MEDICINE_TERMS = {
    "acetaminophen": [
        "acetaminophen",
        "tylenol",
        "paracetamol",
        "apap",
        "panadol",
    ],
    "ibuprofen": ["ibuprofen", "advil", "motrin", "nurofen", "brufen"],
}


def make_post(
    post_id: str,
    title: str,
    body: str,
    medicine: str = "acetaminophen",
) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "body": body,
        "title_clean": title,
        "body_clean": body,
        "clean_text": f"{title} {body}",
        "matched_medicine": medicine,
    }


def run_filter(posts: list[dict], other_medicines=None):
    return step3_filter.filter_batch(
        posts,
        DOSING_TERMS,
        EXCLUDE_TERMS,
        OTHER_MEDICINE_TERMS if other_medicines is None else other_medicines,
        MEDICINE_TERMS,
    )


class RepeatDoseFilterTests(unittest.TestCase):
    def test_keeps_prior_dose_then_unnamed_repeat_dose_question(self):
        posts = [
            make_post(
                "1",
                "Tylenol timing",
                "I took two Tylenol four hours ago. "
                "Can I take another dose now?",
            )
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual([post["post_id"] for post in candidates], ["1"])
        evidence = candidates[0]["repeat_dose_evidence"]
        self.assertEqual(evidence["target_medicine"], "acetaminophen")
        self.assertEqual(evidence["rule_id"], "prior_dose_then_another_dose")
        self.assertIn("four hours ago", evidence["time_expressions"])
        self.assertEqual(stats["by_medicine"], {"acetaminophen": 1})

    def test_keeps_explicit_repeat_questions_without_prior_dose_history(self):
        posts = [
            make_post(
                "1",
                "When can I take ibuprofen again?",
                "The pain has returned.",
                medicine="ibuprofen",
            ),
            make_post(
                "2",
                "Would taking another Tylenol be dangerous?",
                "I still have a headache.",
            ),
            make_post(
                "3",
                "Is a second dose of paracetamol okay?",
                "The label is unclear.",
            ),
            make_post(
                "4",
                "Can I retake Advil?",
                "I need help with the timing.",
                medicine="ibuprofen",
            ),
        ]

        candidates, _ = run_filter(posts)

        self.assertEqual(
            [post["post_id"] for post in candidates],
            ["1", "2", "3", "4"],
        )
        self.assertEqual(candidates[0]["medicine_category"], "ibuprofen")

    def test_recognizes_target_aliases_and_uses_question_target(self):
        posts = [
            make_post(
                "1",
                "Can I redose?",
                "I took Panadol earlier. "
                "Should I take more paracetamol now?",
                medicine="ibuprofen",
            )
        ]

        candidates, _ = run_filter(posts)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["medicine_category"], "acetaminophen")
        self.assertIn(
            "paracetamol",
            candidates[0]["repeat_dose_evidence"]["target_terms"],
        )

    def test_recognizes_common_target_medicine_misspellings(self):
        posts = [
            make_post(
                "acetaminophen_typo",
                "Can I take acetominophen again?",
                "The first dose did not help.",
            ),
            make_post(
                "ibuprofen_typo",
                "Can I take ibufrofin again?",
                "It has been several hours.",
                medicine="ibuprofen",
            ),
        ]
        medicine_terms = {
            "acetaminophen": MEDICINE_TERMS["acetaminophen"]
            + ["acetominophen", "acetaminaphen"],
            "ibuprofen": MEDICINE_TERMS["ibuprofen"]
            + ["ibuprophen", "ibufrofen", "ibufrofin"],
        }

        candidates, _ = step3_filter.filter_batch(
            posts,
            DOSING_TERMS,
            EXCLUDE_TERMS,
            OTHER_MEDICINE_TERMS,
            medicine_terms,
        )

        self.assertEqual(
            [post["post_id"] for post in candidates],
            ["acetaminophen_typo", "ibuprofen_typo"],
        )

    def test_broad_dosing_words_do_not_qualify_unrelated_posts(self):
        posts = [
            make_post(
                "wait",
                "Tylenol and a rash",
                "Should I wait for the rash to go away?",
            ),
            make_post(
                "first",
                "Can I take Tylenol?",
                "The bottle says a 500 mg dose.",
            ),
            make_post(
                "repeat_statement",
                "Ibuprofen usage",
                "I take ibuprofen and the pain starts again later.",
                medicine="ibuprofen",
            ),
            make_post(
                "not_enough_signals",
                "Can you overdose on ibuprofen?",
                "This is a general information question.",
                medicine="ibuprofen",
            ),
            make_post(
                "borrowed_body_words",
                "Can you overdose on ibuprofen",
                "My friend told me she is taking more ibuprofen than directed.",
                medicine="ibuprofen",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(candidates, [])
        self.assertEqual(
            stats["no_repeat_dose_question"]
            + stats["flagged_excluded_intent"],
            5,
        )

    def test_keeps_single_dose_amount_questions(self):
        posts = [
            make_post(
                "how_much",
                "How much ibuprofen can I take?",
                "200 mg pills.",
                medicine="ibuprofen",
            ),
            make_post(
                "how_many_mg",
                "How many mg of Tylenol is safe?",
                "I have a bad headache.",
            ),
            make_post(
                "max_dose",
                "What is the maximum daily dose of paracetamol?",
                "Trying to stay under the limit.",
            ),
            make_post(
                "is_n_mg_ok",
                "Is 800 mg of ibuprofen too much?",
                "That is what I have on hand.",
                medicine="ibuprofen",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(
            [post["post_id"] for post in candidates],
            ["how_much", "how_many_mg", "max_dose", "is_n_mg_ok"],
        )
        self.assertEqual(
            stats["by_repeat_dose_rule"],
            {"dosing_amount_question": 4},
        )

    def test_single_dose_scope_still_excludes_other_medicine_subject(self):
        posts = [
            make_post(
                "other_subject",
                "How much aspirin can I take with Tylenol on hand?",
                "I have both in the cabinet.",
            ),
            make_post(
                "general_info",
                "What does Tylenol treat?",
                "Just curious about it.",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(candidates, [])
        self.assertEqual(stats["flagged_other_medicine"], 1)
        self.assertEqual(stats["no_repeat_dose_question"], 1)

    def test_overdose_and_long_term_words_are_not_automatic_exclusions(self):
        posts = [
            make_post(
                "overdose",
                "Can I take Tylenol again?",
                "I accidentally took too much Tylenol earlier.",
            ),
            make_post(
                "alcohol",
                "When can I take Tylenol again after drinking?",
                "I took Tylenol this morning.",
            ),
            make_post(
                "long_repeat",
                "Can I take ibuprofen again today?",
                "I have taken ibuprofen every day for two weeks.",
                medicine="ibuprofen",
            ),
            make_post(
                "long_without_repeat",
                "How long can I take ibuprofen?",
                "I have used it every day.",
                medicine="ibuprofen",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(
            [post["post_id"] for post in candidates],
            ["overdose", "long_repeat"],
        )
        self.assertEqual(stats["flagged_excluded_intent"], 1)
        self.assertEqual(stats["no_repeat_dose_question"], 1)

    def test_keeps_switches_between_the_two_research_targets(self):
        posts = [
            make_post(
                "direct",
                "Can I switch from Tylenol to Advil?",
                "My headache is still present.",
            ),
            make_post(
                "timed",
                "Pain reliever timing",
                "I took ibuprofen four hours ago. "
                "Can I take Tylenol now?",
                medicine="ibuprofen",
            ),
            make_post(
                "alternate",
                "Can I alternate between paracetamol and Motrin?",
                "I want to follow a safe schedule.",
            ),
            make_post(
                "destination_first",
                "Can I take paracetamol after taking ibuprofen 3 hours ago?",
                "The cramps are still painful.",
                medicine="ibuprofen",
            ),
            make_post(
                "relaxed_interval",
                "How long after Tylenol do I take Advil?",
                "I need to plan the next dose.",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(
            [post["post_id"] for post in candidates],
            [
                "direct",
                "timed",
                "alternate",
                "destination_first",
                "relaxed_interval",
            ],
        )
        self.assertEqual(
            candidates[0]["repeat_dose_evidence"]["transition"],
            "acetaminophen_to_ibuprofen",
        )
        self.assertEqual(
            candidates[1]["repeat_dose_evidence"]["transition"],
            "ibuprofen_to_acetaminophen",
        )
        self.assertEqual(stats["by_medicine"], {"ibuprofen": 3, "acetaminophen": 2})

    def test_keeps_prior_dose_then_take_now_without_repeat_word(self):
        posts = [
            make_post(
                "1",
                "Tylenol timing",
                "I took Tylenol four hours ago. Is it safe to take it now?",
            )
        ]

        candidates, _ = run_filter(posts)

        self.assertEqual([post["post_id"] for post in candidates], ["1"])
        self.assertEqual(
            candidates[0]["repeat_dose_evidence"]["rule_id"],
            "prior_dose_then_take_now",
        )

    def test_still_excludes_switches_to_non_target_medicines(self):
        posts = [
            make_post(
                "known_other",
                "Can I switch from Tylenol to aspirin?",
                "I need another pain reliever.",
            ),
            make_post(
                "unknown_other",
                "Can I switch from Tylenol to amoxicillin?",
                "This is a medication question.",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(candidates, [])
        self.assertEqual(stats["flagged_other_medicine"], 1)
        self.assertEqual(stats["no_repeat_dose_question"], 1)

    def test_incidental_other_medicine_outside_question_does_not_exclude(self):
        posts = [
            make_post(
                "1",
                "Tylenol and aspirin",
                "I took Tylenol four hours ago. "
                "Can I take another dose now?",
            )
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual([post["post_id"] for post in candidates], ["1"])
        self.assertEqual(stats["flagged_other_medicine"], 0)
        self.assertEqual(stats["by_other_medicine"], {})

    def test_contextual_fallback_keeps_flexible_repeat_wording(self):
        posts = [
            make_post(
                "explicit",
                "Tylenol again tonight—okay?",
                "The headache came back.",
            ),
            make_post(
                "implicit",
                "Pain relief timing",
                "I took Tylenol after lunch. "
                "The headache returned. "
                "Could I have one more now?",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(
            [post["post_id"] for post in candidates],
            ["explicit", "implicit"],
        )
        self.assertEqual(
            stats["by_repeat_dose_rule"],
            {
                "contextual_explicit_repeat_question": 1,
                "contextual_prior_dose_followup": 1,
            },
        )

    def test_allows_replace_between_research_targets(self):
        posts = [
            make_post(
                "replace",
                "Can I replace Tylenol with Advil?",
                "The first one did not help.",
            ),
            make_post(
                "substitute",
                "Could I substitute Motrin for Panadol?",
                "I need to change pain relievers.",
            ),
        ]

        candidates, _ = run_filter(posts)

        self.assertEqual(
            [post["post_id"] for post in candidates],
            ["replace", "substitute"],
        )

    def test_target_pair_combination_requires_timing_context(self):
        posts = [
            make_post(
                "timed",
                "Can I combine Tylenol and Advil by alternating doses?",
                "I need a safe schedule.",
            ),
            make_post(
                "interaction",
                "Do Tylenol and Advil combine well?",
                "I am asking about their interaction.",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual([post["post_id"] for post in candidates], ["timed"])
        self.assertEqual(stats["flagged_excluded_intent"], 1)

    def test_contextual_fallback_rejects_unrelated_nearby_questions(self):
        posts = [
            make_post(
                "symptom",
                "Is this ER worthy?",
                "I have taken Tylenol and Advil but the pain remains. "
                "Should I go to the ER?",
            ),
            make_post(
                "vaccine",
                "Could this be related to the second dose?",
                "The vaccine symptoms went away with Advil.",
                medicine="ibuprofen",
            ),
            make_post(
                "first_dose",
                "How soon after surgery is it okay to take Advil?",
                "I have not taken any pain medicine yet.",
                medicine="ibuprofen",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(candidates, [])
        self.assertEqual(stats["no_repeat_dose_question"], 3)

    def test_alcohol_drink_wording_is_excluded(self):
        posts = [
            make_post(
                "drink",
                "How long after taking Tylenol can I drink?",
                "I took another Tylenol this morning.",
            )
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(candidates, [])
        self.assertEqual(stats["flagged_excluded_intent"], 1)

    def test_full_post_context_can_resolve_a_distant_unnamed_question(self):
        body = (
            "Tylenol is listed earlier in the post. "
            + ("Background details without a medicine question. " * 20)
            + "More unrelated history. Another unrelated sentence. "
            "Can I take another dose now?"
        )
        posts = [
            make_post(
                "distant",
                "Medication question",
                body,
            )
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual([post["post_id"] for post in candidates], ["distant"])
        self.assertEqual(
            stats["by_repeat_dose_rule"],
            {"contextual_post_level_repeat_question": 1},
        )

    def test_released_intent_terms_do_not_automatically_exclude_redosing(self):
        posts = [
            make_post(
                "interaction",
                "Is there an interaction if I take Tylenol again?",
                "This is about another dose.",
            ),
            make_post(
                "how_many",
                "How many doses of Tylenol can I take again?",
                "I need another dose.",
            ),
            make_post(
                "how_much",
                "How much ibuprofen can I take again?",
                "I took it previously.",
                medicine="ibuprofen",
            ),
            make_post(
                "higher",
                "Can I take a higher dose of Tylenol again?",
                "The earlier dose did not work.",
            ),
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual(
            [post["post_id"] for post in candidates],
            ["interaction", "how_many", "how_much", "higher"],
        )
        self.assertEqual(stats["flagged_excluded_intent"], 0)

    def test_other_medicine_match_is_word_bounded(self):
        posts = [
            make_post(
                "1",
                "Tylenol timing for an aspiring runner",
                "I took Tylenol four hours ago. "
                "Can I take another dose now?",
            )
        ]

        candidates, stats = run_filter(posts)

        self.assertEqual([post["post_id"] for post in candidates], ["1"])
        self.assertEqual(stats["flagged_other_medicine"], 0)

    def test_stats_partition_all_input_posts(self):
        posts = [
            make_post(
                "keep",
                "When can I take Tylenol again?",
                "My headache returned.",
            ),
            make_post("other", "Tylenol and Aleve", "Can I take another dose?"),
            make_post("topic", "Tylenol meme", "Can I take another dose?"),
            make_post(
                "intent",
                "When can I take Tylenol again after drinking?",
                "I took it earlier.",
            ),
            make_post("none", "Tylenol question", "The dose is 500 mg."),
        ]

        candidates, stats = run_filter(posts)
        partitioned = (
            len(candidates)
            + stats["flagged_other_medicine"]
            + stats["flagged_excluded"]
            + stats["flagged_excluded_intent"]
            + stats["no_repeat_dose_question"]
        )

        self.assertEqual(partitioned, len(posts))

    def test_storage_removes_filter_only_metadata(self):
        candidate = make_post(
            "keep",
            "When can I take Tylenol again?",
            "My headache returned.",
        )
        candidate.update(
            {
                "medicine_category": "acetaminophen",
                "repeat_dose_evidence": {"rule_id": "test"},
                "filter_status": "repeat_dose_candidate",
            }
        )

        stored = step3_filter.prepare_candidate_for_storage(candidate)

        self.assertNotIn("medicine_category", stored)
        self.assertNotIn("repeat_dose_evidence", stored)
        self.assertNotIn("filter_status", stored)
        self.assertEqual(stored["post_id"], "keep")
        self.assertIn("medicine_category", candidate)


if __name__ == "__main__":
    unittest.main()
