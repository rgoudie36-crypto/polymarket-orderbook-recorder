"""Synthetic-data tests for the pre-registered evaluator. No real recorded data is used."""

import datetime as dt
import unittest
from decimal import Decimal as D

from analysis import evaluate as ev
from analysis.resolve import parse_resolution

T0 = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def rec(slug, minutes, bids, offers, *, end_h=12, cat="crypto", game=None, traded="0", last="0.50", run=None):
    t = T0 + dt.timedelta(minutes=minutes)
    return {"slug": slug, "fetched_at": iso(t), "run_id": run or iso(t), "state": "MARKET_STATE_OPEN",
            "bids": [[str(p), str(q)] for p, q in bids], "offers": [[str(p), str(q)] for p, q in offers],
            "fee_coefficient": 0.095, "end_date": iso(T0 + dt.timedelta(hours=end_h)), "category": cat,
            "game_start_time": iso(game) if game else None, "shares_traded": traded, "last_trade_px": last,
            "question": slug}


START = T0 - dt.timedelta(days=1)


class FillTests(unittest.TestCase):
    def test_long_buy_walks_levels_and_fee(self):
        s = ev.Snap(rec("m", 0, [(0.40, 5)], [(0.42, 4), (0.45, 10)]))
        q, notional, fee = ev.fill(s, ev.LONG, "buy", D(10))
        self.assertEqual(q, D(10))
        self.assertEqual(notional, D("0.42") * 4 + D("0.45") * 6)
        exp = D("0.095") * (4 * D("0.42") * D("0.58") + 6 * D("0.45") * D("0.55"))
        self.assertEqual(fee, exp)

    def test_short_buy_pays_one_minus_bid(self):
        s = ev.Snap(rec("m", 0, [(0.40, 3), (0.38, 100)], [(0.42, 4)]))
        q, notional, _ = ev.fill(s, ev.SHORT, "buy", D(10))
        self.assertEqual(notional, D("0.60") * 3 + D("0.62") * 7)

    def test_only_displayed_qty(self):
        s = ev.Snap(rec("m", 0, [(0.40, 3)], [(0.42, 2)]))
        self.assertEqual(ev.fill(s, ev.LONG, "buy", D(10))[0], D(2))

    def test_bankers_rounding(self):
        self.assertEqual(ev.money(D("0.125")), D("0.12"))
        self.assertEqual(ev.money(D("0.135")), D("0.14"))


class EligibilityAndRules(unittest.TestCase):
    def test_sports_must_be_pregame(self):
        pre = ev.Snap(rec("s", 0, [(0.4, 5)], [(0.42, 5)], cat="sports", game=T0 + dt.timedelta(hours=1)))
        live = ev.Snap(rec("s", 0, [(0.4, 5)], [(0.42, 5)], cat="sports", game=T0 - dt.timedelta(minutes=5)))
        nogame = ev.Snap(rec("s", 0, [(0.4, 5)], [(0.42, 5)], cat="sports"))
        self.assertTrue(ev.eligible(pre))
        self.assertFalse(ev.eligible(live))
        self.assertFalse(ev.eligible(nogame))

    def test_one_sided_and_too_close_to_end(self):
        self.assertFalse(ev.eligible(ev.Snap(rec("x", 0, [], [(0.5, 5)]))))
        self.assertFalse(ev.eligible(ev.Snap(rec("x", 0, [(0.4, 5)], [(0.42, 5)], end_h=0.5))))

    def test_rule1_directions(self):
        longs = ev.Snap(rec("a", 0, [(0.48, 100), (0.47, 50)], [(0.50, 20), (0.51, 20)]))
        shorts = ev.Snap(rec("a", 0, [(0.48, 10)], [(0.50, 200)]))
        thin = ev.Snap(rec("a", 0, [(0.48, 90)], [(0.50, 10)]))  # ratio ok, deep side < 100
        self.assertEqual(ev.rule1(longs, None), ev.LONG)
        self.assertEqual(ev.rule1(shorts, None), ev.SHORT)
        self.assertIsNone(ev.rule1(thin, None))

    def test_rule2_favorites(self):
        fav_long = ev.Snap(rec("b", 0, [(0.88, 5)], [(0.90, 5)]))
        fav_short = ev.Snap(rec("b", 0, [(0.10, 5)], [(0.12, 5)]))  # 1-0.10 = 0.90
        wide = ev.Snap(rec("b", 0, [(0.85, 5)], [(0.90, 5)]))
        far = ev.Snap(rec("b", 0, [(0.88, 5)], [(0.90, 5)], end_h=30))
        self.assertEqual(ev.rule2(fav_long, None), ev.LONG)
        self.assertEqual(ev.rule2(fav_short, None), ev.SHORT)
        self.assertIsNone(ev.rule2(wide, None))
        self.assertIsNone(ev.rule2(far, None))

    def test_rule3_flow(self):
        prev = ev.Snap(rec("c", 0, [(0.48, 5)], [(0.50, 5)], traded="100", last="0.45"))
        up = ev.Snap(rec("c", 15, [(0.48, 5)], [(0.50, 5)], traded="120", last="0.49"))
        notrade = ev.Snap(rec("c", 15, [(0.48, 5)], [(0.50, 5)], traded="100", last="0.49"))
        stale = ev.Snap(rec("c", 45, [(0.48, 5)], [(0.50, 5)], traded="120", last="0.49"))
        self.assertEqual(ev.rule3(up, prev), ev.LONG)
        self.assertIsNone(ev.rule3(notrade, prev))
        self.assertIsNone(ev.rule3(stale, prev))

    def test_control_side_deterministic(self):
        self.assertEqual(ev.control_side("abc", "r"), ev.control_side("abc", "r"))
        self.assertIn(ev.control_side("abc", "r"), (ev.LONG, ev.SHORT))


class SimulationTests(unittest.TestCase):
    def series(self):
        recs = [rec("m", 0, [(0.48, 100), (0.47, 50)], [(0.50, 20)]),
                rec("m", 15, [(0.49, 100)], [(0.52, 20)]),
                rec("m", 30, [(0.55, 100)], [(0.57, 20)])]
        return ev.load_series(recs)["m"]

    def test_optimistic_short_horizon(self):
        b = ev.simulate(self.series(), 0, ev.LONG, "short", "optimistic", "0")
        # buy 10 @0.50, sell 10 @0.49 at t+1
        fee = ev.money(D("0.095") * 10 * (D("0.50") * D("0.50") + D("0.49") * D("0.51")))
        self.assertEqual(b["cost"], D("5.00"))
        self.assertEqual(b["net"], D("4.90") - D("5.00") - fee)

    def test_pessimistic_worse_entry_and_t_plus_2_exit(self):
        b = ev.simulate(self.series(), 0, ev.LONG, "short", "pessimistic", "0")
        # entry worse of 0.50 and 0.52 -> 0.52; exit at t+2 bid 0.55
        self.assertEqual(b["cost"], D("5.20"))
        fee = ev.money(D("0.095") * 10 * (D("0.52") * D("0.48") + D("0.55") * D("0.45")))
        self.assertEqual(b["net"], D("5.50") - D("5.20") - fee)

    def test_pessimistic_requires_next_snapshot(self):
        ser = ev.load_series([rec("m", 0, [(0.48, 100)], [(0.50, 20)])])["m"]
        self.assertIsNone(ev.simulate(ser, 0, ev.LONG, "short", "pessimistic", "1"))

    def test_hold_to_resolution_short_side(self):
        ser = self.series()
        b = ev.simulate(ser, 0, ev.SHORT, "hold", "optimistic", "0")  # long lost -> short wins
        # buy short 10 @ (1-0.48)=0.52 -> pays 1 each
        fee = ev.money(D("0.095") * 10 * D("0.48") * D("0.52"))
        self.assertEqual(b["net"], D(10) - D("5.20") - fee)

    def test_no_exit_snapshot_falls_back_to_resolution(self):
        ser = ev.load_series([rec("m", 0, [(0.48, 100)], [(0.50, 20)]),
                              rec("m", 120, [(0.6, 100)], [(0.62, 20)])])["m"]
        b = ev.simulate(ser, 0, ev.LONG, "short", "optimistic", "1")
        fee = ev.money(D("0.095") * 10 * D("0.25"))
        self.assertEqual(b["net"], D(10) - D("5.00") - fee)


class StatsTests(unittest.TestCase):
    def test_cluster_stats_and_bar(self):
        bets = [{"cost": D(5), "net": D("0.5"), "cluster": f"c{i % 30}"} for i in range(120)]
        bets += [{"cost": D(5), "net": D("-0.2"), "cluster": f"c{i % 30}"} for i in range(30)]
        st = ev.cluster_stats(bets, n_boot=200)
        self.assertEqual(st["bets"], 150)
        self.assertEqual(st["clusters"], 30)
        self.assertGreater(D(st["total_net"]), 0)
        self.assertIsNone(st["t"])  # identical clusters -> zero variance -> no t
        varied = [{"cost": D(5), "net": D(str(0.5 if i % 3 else -0.6)), "cluster": f"c{i % 40}"} for i in range(150)]
        st2 = ev.cluster_stats(varied, n_boot=200)
        self.assertIsNotNone(st2["t"])
        self.assertEqual(ev.passes(st2), st2["t"] >= 2.4 and D(st2["max_cluster_share"]) <= D("0.25"))

    def test_fewer_than_100_bets_fails(self):
        bets = [{"cost": D(5), "net": D(str(1 + (i % 2) * 0.1)), "cluster": f"c{i}"} for i in range(50)]
        self.assertFalse(ev.passes(ev.cluster_stats(bets, n_boot=50)))


class EndToEnd(unittest.TestCase):
    def test_window_and_one_entry_per_market(self):
        recs = [rec("m", m, [(0.48, 100)], [(0.50, 20)]) for m in (0, 15, 30, 45)]
        recs.append(rec("old", -60 * 48, [(0.48, 100)], [(0.50, 20)]))  # before window start
        out = ev.evaluate(recs, {"m": {"payout_long": "1"}, "old": {"payout_long": "1"}}, window_start=START)
        r1 = out["rules"]["rule1_imbalance"]
        self.assertEqual(r1["optimistic"]["stats"]["bets"], 1)
        self.assertIn(r1["verdict"], ("PASS", "FAIL", "HARNESS BROKEN (control passed)"))

    def test_unresolved_dropped(self):
        recs = [rec("m", m, [(0.48, 100)], [(0.50, 20)]) for m in (0, 15, 30)]
        out = ev.evaluate(recs, {}, window_start=START)
        self.assertEqual(out["rules"]["rule1_imbalance"]["pessimistic"]["dropped_unresolved_or_void"], 1)


class ResolveTests(unittest.TestCase):
    def test_parse_resolution(self):
        m = {"closed": True, "status": "MARKET_STATUS_RESOLVED",
             "marketSides": [{"long": True, "price": "1"}, {"long": False, "price": "0"}]}
        self.assertEqual(parse_resolution(m)["payout_long"], "1")
        self.assertIsNone(parse_resolution(dict(m, closed=False))["payout_long"])


if __name__ == "__main__":
    unittest.main()
