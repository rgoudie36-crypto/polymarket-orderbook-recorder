"""Offline tests: no network. Run with `python -m unittest discover -s tests`."""

import datetime as dt
import gzip
import json
import os
import tempfile
import unittest
import urllib.parse

from recorder.client import Client, HttpError
from recorder import record


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def market(slug, end, bid="0.40", ask="0.42"):
    m = {"slug": slug, "id": slug, "endDate": end, "category": "sports", "feeCoefficient": 0.095,
         "marketSides": [{"long": True, "description": "Home"}, {"long": False, "description": "Away"}]}
    if bid:
        m["bestBidQuote"] = {"value": bid, "currency": "USD"}
    if ask:
        m["bestAskQuote"] = {"value": ask, "currency": "USD"}
    return m


BOOK = {"marketData": {"marketSlug": "a", "state": "MARKET_STATE_OPEN", "transactTime": "2026-11-14T00:00:00Z",
                       "bids": [{"px": {"value": "0.40", "currency": "USD"}, "qty": "100.0000"}],
                       "offers": [{"px": {"value": "0.42", "currency": "USD"}, "qty": "30.0000"},
                                  {"px": {"value": "0.45", "currency": "USD"}, "qty": "5.0000"}],
                       "stats": {"lastTradePx": {"value": "0.41", "currency": "USD"}, "openInterest": "12.0000"}}}


class ClientTests(unittest.TestCase):
    def test_paces_requests(self):
        fc = FakeClock()
        c = Client(min_interval=0.1, fetch=lambda u, t: (200, b"{}"), clock=fc.clock, sleep=fc.sleep)
        for _ in range(3):
            c.get_json("/x")
        self.assertEqual(len(fc.sleeps), 2)
        self.assertTrue(all(abs(s - 0.1) < 1e-9 for s in fc.sleeps))

    def test_retries_429_then_succeeds(self):
        fc = FakeClock()
        responses = iter([(429, b""), (503, b""), (200, b'{"ok": 1}')])
        c = Client(min_interval=0, fetch=lambda u, t: next(responses), clock=fc.clock, sleep=fc.sleep)
        self.assertEqual(c.get_json("/x"), {"ok": 1})
        self.assertEqual(c.retries, 2)
        self.assertGreaterEqual(fc.sleeps[0], 1.0)  # docs: wait at least 1 s after a 429

    def test_404_not_retried(self):
        fc = FakeClock()
        calls = []
        c = Client(min_interval=0, fetch=lambda u, t: calls.append(u) or (404, b""), clock=fc.clock, sleep=fc.sleep)
        with self.assertRaises(HttpError):
            c.get_json("/x")
        self.assertEqual(len(calls), 1)

    def test_gives_up_after_max_retries(self):
        fc = FakeClock()
        c = Client(min_interval=0, max_retries=2, fetch=lambda u, t: (429, b""), clock=fc.clock, sleep=fc.sleep)
        with self.assertRaises(HttpError):
            c.get_json("/x")
        self.assertEqual(c.requests_made, 3)


class RecordTests(unittest.TestCase):
    def test_select_skips_unquoted_and_orders_by_end(self):
        ms = [market("late", "2026-11-16T00:00:00Z"), market("none", "2026-11-14T01:00:00Z", None, None),
              market("soon", "2026-11-14T02:00:00Z"), market("onesided", "2026-11-15T00:00:00Z", None, "0.9")]
        chosen, n = record.select_for_books(ms, 2)
        self.assertEqual(n, 3)
        self.assertEqual([m["slug"] for m in chosen], ["soon", "onesided"])

    def test_normalize(self):
        r = record.normalize(market("a", "2026-11-15T00:00:00Z"), BOOK, "RID", "2026-11-14T00:00:01Z")
        self.assertEqual(r["bids"], [["0.40", "100.0000"]])
        self.assertEqual(r["offers"][1], ["0.45", "5.0000"])
        self.assertEqual(r["long_side"], "Home")
        self.assertEqual(r["last_trade_px"], "0.41")
        self.assertEqual(r["listing_best_ask"], "0.42")
        self.assertEqual(r["schema"], record.SCHEMA_VERSION)

    def test_normalize_empty_book(self):
        r = record.normalize(market("a", "x"), {}, "RID", "t")
        self.assertEqual((r["bids"], r["offers"], r["state"]), ([], [], None))

    def _fake_gateway(self, markets, failing=()):
        def fetch(url, timeout):
            u = urllib.parse.urlparse(url)
            if u.path == "/v1/markets":
                q = urllib.parse.parse_qs(u.query)
                assert "endDateMin" in q and q["closed"] == ["false"]
                off = int(q["offset"][0])
                return 200, json.dumps({"markets": markets[off:off + record.PAGE_LIMIT]}).encode()
            slug = u.path.split("/")[3]
            if slug in failing:
                return 404, b""
            return 200, json.dumps(BOOK).encode()
        return fetch

    def test_run_end_to_end_offline(self):
        ms = [market(f"m{i}", f"2026-11-14T{i % 24:02d}:00:00Z") for i in range(5)]
        fc = FakeClock()
        c = Client(min_interval=0, fetch=self._fake_gateway(ms, failing={"m2"}), clock=fc.clock, sleep=fc.sleep)
        now = dt.datetime(2026, 11, 14, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            meta = record.run(c, d, now=now, clock=fc.clock, wallclock=lambda: now)
            self.assertEqual(meta["books_written"], 4)
            self.assertEqual(meta["errors"], [{"slug": "m2", "status": 404}])
            with gzip.open(os.path.join(d, f"books-{meta['run_id']}.jsonl.gz"), "rt") as f:
                rows = [json.loads(l) for l in f]
            self.assertEqual(len(rows), 4)
            self.assertTrue(os.path.exists(os.path.join(d, f"run-{meta['run_id']}.json")))

    def test_pagination_and_dedupe(self):
        ms = [market(f"m{i}", "2026-11-14T05:00:00Z") for i in range(record.PAGE_LIMIT + 3)]
        fc = FakeClock()
        c = Client(min_interval=0, fetch=self._fake_gateway(ms + ms[:2]), clock=fc.clock, sleep=fc.sleep)
        got = record.list_universe(c, dt.datetime(2026, 11, 14, tzinfo=dt.timezone.utc), 72)
        self.assertEqual(len(got), record.PAGE_LIMIT + 3)

    def test_time_budget_truncates(self):
        ms = [market(f"m{i}", "2026-11-14T05:00:00Z") for i in range(10)]
        fc = FakeClock()
        gw = self._fake_gateway(ms)

        def slow(url, timeout):
            fc.t += 1.0
            return gw(url, timeout)
        c = Client(min_interval=0, fetch=slow, clock=fc.clock, sleep=fc.sleep)
        now = dt.datetime(2026, 11, 14, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            meta = record.run(c, d, time_budget=4.5, now=now, clock=fc.clock, wallclock=lambda: now)
        self.assertTrue(meta["truncated_by_time_budget"])
        self.assertLess(meta["books_written"], 10)


if __name__ == "__main__":
    unittest.main()
