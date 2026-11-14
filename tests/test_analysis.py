import gzip
import json
import os
import tempfile
import unittest
from decimal import Decimal

from analysis.load import book_summary, iter_books

REC = {"slug": "a", "fetched_at": "t", "bids": [["0.38", "5"], ["0.40", "10"]], "offers": [["0.45", "1"], ["0.42", "3"]]}


class AnalysisTests(unittest.TestCase):
    def test_summary_sorts_levels(self):
        s = book_summary(REC)
        self.assertEqual((s["best_bid"], s["best_ask"]), (Decimal("0.40"), Decimal("0.42")))
        self.assertEqual(s["spread"], Decimal("0.02"))
        self.assertEqual((s["bid_depth"], s["ask_depth"]), (Decimal(15), Decimal(4)))

    def test_summary_top_levels_and_one_sided(self):
        self.assertEqual(book_summary(REC, levels=1)["bid_depth"], Decimal(10))
        s = book_summary({"bids": [], "offers": [["0.9", "2"]]})
        self.assertIsNone(s["spread"])
        self.assertEqual(s["ask_depth"], Decimal(2))

    def test_iter_books_dir(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "run1"))
            with gzip.open(os.path.join(d, "run1", "books-x.jsonl.gz"), "wt") as f:
                f.write(json.dumps(REC) + "\n" + json.dumps(REC) + "\n")
            self.assertEqual(len(list(iter_books(d))), 2)


if __name__ == "__main__":
    unittest.main()
