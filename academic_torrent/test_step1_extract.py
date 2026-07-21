import json
import unittest

import step1_extract


class Step1BodyTests(unittest.TestCase):
    def test_deleted_and_removed_markers_are_preserved(self):
        lines = [
            json.dumps(
                {
                    "id": "deleted",
                    "created_utc": 1,
                    "title": "Tylenol question",
                    "selftext": "[deleted]",
                }
            ),
            json.dumps(
                {
                    "id": "removed",
                    "created_utc": 1,
                    "title": "Ibuprofen question",
                    "selftext": "[removed]",
                }
            ),
        ]
        medicine_terms = {
            "acetaminophen": ["tylenol"],
            "ibuprofen": ["ibuprofen"],
        }

        records, _ = step1_extract.process_batch(
            lines,
            medicine_terms,
            start_ts=0,
            end_ts=2,
            subreddit="AskDocs",
            crawl_ts="test",
        )

        self.assertEqual(
            [record["body"] for record in records],
            ["[deleted]", "[removed]"],
        )


if __name__ == "__main__":
    unittest.main()
