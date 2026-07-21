import os
import tempfile
import unittest

import step0_config as cfg


class ComprehensiveSummaryTests(unittest.TestCase):
    def test_combines_available_subreddit_summaries_and_totals(self):
        original_output_base = cfg.OUTPUT_BASE
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                cfg.OUTPUT_BASE = temp_dir
                summary_dir = os.path.join(temp_dir, cfg.DIR_SUMMARY)
                os.makedirs(summary_dir, exist_ok=True)

                cfg.write_json(
                    os.path.join(summary_dir, "Alpha.json"),
                    {
                        "subreddit": "Alpha",
                        "steps": {
                            "step1_extract": {"kept_all": 10},
                            "step2_clean": {"kept": 9},
                            "step3_filter": {"candidates": 2},
                        },
                    },
                )
                cfg.write_json(
                    os.path.join(summary_dir, "Beta.json"),
                    {
                        "subreddit": "Beta",
                        "steps": {
                            "step1_extract": {"kept_all": 20},
                            "step2_clean": {"kept": 18},
                            "step3_filter": {"candidates": 3},
                        },
                    },
                )

                combined = cfg.write_comprehensive_summary(
                    ["Alpha", "Beta", "Missing"]
                )

                self.assertEqual(combined["subreddits"], 2)
                self.assertEqual(
                    combined["subreddits_missing_summary"],
                    ["Missing"],
                )
                self.assertEqual(
                    combined["posts_by_step"],
                    {
                        "step1_extract": 30,
                        "step2_clean": 27,
                        "step3_filter": 5,
                    },
                )
                stored = cfg.read_json(
                    os.path.join(
                        summary_dir,
                        cfg.COMPREHENSIVE_SUMMARY_FILE,
                    )
                )
                self.assertEqual(stored, combined)
        finally:
            cfg.OUTPUT_BASE = original_output_base


if __name__ == "__main__":
    unittest.main()
