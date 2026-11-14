"""Pre-registered evaluation of the three rules in docs/PREREGISTRATION.md (registered commit bdb36a4).

Written BEFORE any recorded data was examined. Do not change constants or logic after
results have been seen; bug fixes must be logged in the pre-registration change log.

Usage:
  python -m analysis.evaluate --data DECRYPTED_DIR --resolutions resolutions.json --out report.json

Inputs: books-*.jsonl.gz files (decrypted) and resolutions.json from analysis/resolve.py.
"""

import argparse
import datetime as dt
import glob
import gzip
import hashlib
import json
import os
import random
import sys
from collections import defaultdict
from decimal import ROUND_HALF_EVEN, Decimal as D

# ---- Pre-registered constants (do not edit after registration) ----
WINDOW_START = dt.datetime(2026, 11, 14, 21, 1, 38, tzinfo=dt.timezone.utc)  # registration commit time
WINDOW_DAYS = 56
NEXT_MAX = dt.timedelta(minutes=30)      # "next snapshot" must be within 30 min
EXIT_FALLBACK = dt.timedelta(minutes=60)  # exit fallback window
MIN_TO_END = dt.timedelta(hours=1)
VOID_AFTER = dt.timedelta(days=14)
SIZE = D(10)
T_BAR = 2.4
MIN_BETS = 100
MAX_CLUSTER_SHARE = D("0.25")
BOOT_N, BOOT_SEED = 10000, 20261114
LONG, SHORT = "LONG", "SHORT"


def ts(s):
    return dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc) if s else None


def money(x):
    return D(x).quantize(D("0.01"), rounding=ROUND_HALF_EVEN)


# ---------------- Book helpers ----------------
class Snap:
    """One market book at one time, with sorted Decimal levels."""

    def __init__(self, rec):
        self.rec = rec
        self.slug = rec["slug"]
        self.t = ts(rec["fetched_at"])
        self.bids = sorted(((D(p), D(q)) for p, q in rec.get("bids") or []), reverse=True)
        self.asks = sorted((D(p), D(q)) for p, q in rec.get("offers") or [])
        self.fee_coef = D(str(rec.get("fee_coefficient") or "0.095"))
        self.end = ts(rec.get("end_date"))
        self.game_start = ts(rec.get("game_start_time"))
        self.category = rec.get("category") or ""

    @property
    def two_sided(self):
        return bool(self.bids) and bool(self.asks)

    @property
    def best_bid(self):
        return self.bids[0][0]

    @property
    def best_ask(self):
        return self.asks[0][0]

    @property
    def spread(self):
        return self.best_ask - self.best_bid

    @property
    def mid(self):
        return (self.best_ask + self.best_bid) / 2


def levels_for(snap, side, action):
    """Levels as (price_paid_or_received_per_contract, qty, long_px) for the given trade.

    action 'buy' opens a position, 'sell' closes it.
    LONG buy lifts asks (pay ask); LONG sell hits bids (receive bid).
    SHORT buy hits bids (pay 1-bid); SHORT sell lifts asks (receive 1-ask).
    """
    if (side, action) == (LONG, "buy"):
        return [(p, q, p) for p, q in snap.asks]
    if (side, action) == (LONG, "sell"):
        return [(p, q, p) for p, q in snap.bids]
    if (side, action) == (SHORT, "buy"):
        return [(1 - p, q, p) for p, q in snap.bids]
    return [(1 - p, q, p) for p, q in snap.asks]


def fill(snap, side, action, qty):
    """Walk displayed levels. Returns (filled_qty, notional, raw_fee)."""
    left, notional, fee, got = qty, D(0), D(0), D(0)
    for px, q, long_px in levels_for(snap, side, action):
        if left <= 0:
            break
        take = min(q, left)
        notional += px * take
        fee += snap.fee_coef * take * long_px * (1 - long_px)
        got += take
        left -= take
    return got, notional, fee


# ---------------- Eligibility and rules ----------------
def eligible(s):
    if s.rec.get("state") != "MARKET_STATE_OPEN" or not s.two_sided or s.end is None:
        return False
    if s.t > s.end - MIN_TO_END:
        return False
    if s.category == "sports":
        if s.game_start is None or not (s.t < s.game_start):
            return False
    return True


def rule1(s, prev):
    if not (s.spread <= D("0.05") and D("0.10") <= s.mid <= D("0.90")):
        return None
    b = sum(q for _, q in s.bids[:3])
    a = sum(q for _, q in s.asks[:3])
    if b >= 3 * a and b >= 100:
        return LONG
    if a >= 3 * b and a >= 100:
        return SHORT
    return None


def rule2(s, prev):
    if not (MIN_TO_END <= s.end - s.t <= dt.timedelta(hours=24)):
        return None
    if s.spread > D("0.03"):
        return None
    if D("0.85") <= s.best_ask <= D("0.94"):
        return LONG
    if D("0.85") <= 1 - s.best_bid <= D("0.94"):
        return SHORT
    return None


def rule3(s, prev):
    if prev is None or s.t - prev.t > NEXT_MAX:
        return None
    if not (s.spread <= D("0.04") and D("0.10") <= s.mid <= D("0.90")):
        return None
    try:
        traded_now, traded_prev = D(s.rec["shares_traded"]), D(prev.rec["shares_traded"])
        lt_now, lt_prev = D(s.rec["last_trade_px"]), D(prev.rec["last_trade_px"])
    except (KeyError, TypeError, ArithmeticError):
        return None
    if not traded_now > traded_prev:
        return None
    move = lt_now - lt_prev
    if move >= D("0.03"):
        return LONG
    if move <= D("-0.03"):
        return SHORT
    return None


RULES = {
    "rule1_imbalance": (rule1, "short"),
    "rule2_favorites": (rule2, "hold"),
    "rule3_flow": (rule3, "short"),
}


def control_side(slug, rule):
    return LONG if hashlib.sha256((slug + rule).encode()).digest()[0] % 2 == 0 else SHORT


# ---------------- Bet simulation ----------------
def next_snap(series, i, within):
    """Index of the first snapshot after series[i] within `within`, else None."""
    if i + 1 < len(series) and series[i + 1].t - series[i].t <= within:
        return i + 1
    return None


def simulate(series, i, side, horizon, model, payout_long):
    """Simulate one bet entered at series[i]. Returns dict or None (no bet / void)."""
    if payout_long is None:
        return None
    s = series[i]
    if model == "optimistic":
        qty, cost, fee = fill(s, side, "buy", SIZE)
        exit_ref = i
    else:
        j = next_snap(series, i, NEXT_MAX)
        if j is None:
            return None
        q0, _, _ = fill(s, side, "buy", SIZE)
        q1, _, _ = fill(series[j], side, "buy", SIZE)
        qty = min(q0, q1)
        if qty < 1:
            return None
        a = fill(s, side, "buy", qty)
        b = fill(series[j], side, "buy", qty)
        _, cost, fee = max(a, b, key=lambda x: x[1])  # worse = higher cost
        exit_ref = j
    if qty < 1:
        return None
    proceeds, held = D(0), qty
    if horizon == "short":
        k = next_snap(series, exit_ref, NEXT_MAX)
        if k is None:
            k = next_snap(series, exit_ref, EXIT_FALLBACK)
        if k is not None:
            sold, notional, efee = fill(series[k], side, "sell", qty)
            proceeds += notional
            fee += efee
            held = qty - sold
    pay = D(payout_long) if side == LONG else 1 - D(payout_long)
    proceeds += held * pay
    net = proceeds - cost - money(fee)
    return {"slug": s.slug, "t": s.rec["fetched_at"], "side": side, "qty": str(qty),
            "cost": cost, "net": net, "fee": money(fee),
            "cluster": f"{s.category}|{s.end.date().isoformat()}"}


def resolution_payout(res, slug, end, as_of):
    r = res.get(slug)
    if r and r.get("payout_long") is not None:
        return r["payout_long"]
    return None  # unresolved or void -> dropped (counted separately)


# ---------------- Statistics ----------------
def cluster_stats(bets, seed=BOOT_SEED, n_boot=BOOT_N):
    n = len(bets)
    tot_cost = sum((b["cost"] for b in bets), D(0))
    tot_net = sum((b["net"] for b in bets), D(0))
    out = {"bets": n, "total_cost": str(tot_cost), "total_net": str(tot_net)}
    if n == 0 or tot_cost == 0:
        return dict(out, mean_return=None, t=None, clusters=0, max_cluster_share=None, boot_p=None)
    m = tot_net / tot_cost
    by = defaultdict(lambda: [D(0), D(0)])
    for b in bets:
        by[b["cluster"]][0] += b["net"]
        by[b["cluster"]][1] += b["cost"]
    g = len(by)
    resid = [net - m * cost for net, cost in by.values()]
    if g > 1:
        var = D(g) / D(g - 1) * sum(e * e for e in resid) / (tot_cost * tot_cost)
        se = var.sqrt() if var > 0 else D(0)
        t = float(m / se) if se > 0 else None
    else:
        t = None
    share = (max(v[0] for v in by.values()) / tot_net) if tot_net > 0 else None
    rng = random.Random(seed)
    keys = list(by)
    le0 = 0
    for _ in range(n_boot):
        sn = sc = D(0)
        for _k in range(g):
            v = by[keys[rng.randrange(g)]]
            sn += v[0]
            sc += v[1]
        if sc == 0 or sn / sc <= 0:
            le0 += 1
    return dict(out, mean_return=str(m), t=t, clusters=g,
                max_cluster_share=str(share) if share is not None else None, boot_p=le0 / n_boot)


def passes(st):
    return (st["bets"] >= MIN_BETS and D(st["total_net"]) > 0 and st["t"] is not None
            and st["t"] >= T_BAR and st["max_cluster_share"] is not None
            and D(st["max_cluster_share"]) <= MAX_CLUSTER_SHARE)


# ---------------- Driver ----------------
def load_series(records):
    by = defaultdict(list)
    for r in records:
        if r.get("slug") and r.get("fetched_at"):
            by[r["slug"]].append(Snap(r))
    for v in by.values():
        v.sort(key=lambda s: s.t)
    return by


def arbitrage_diagnostic(records):
    """Heuristic group = same (question, end_date); count group-snapshots with asks+fees <= 0.99."""
    groups = defaultdict(list)
    for r in records:
        if r.get("question") and r.get("end_date") and r.get("run_id"):
            groups[(r["run_id"], r["question"], r["end_date"])].append(Snap(r))
    hits = 0
    for snaps in groups.values():
        if len(snaps) < 2 or not all(s.asks for s in snaps):
            continue
        tot = sum(s.best_ask + s.fee_coef * s.best_ask * (1 - s.best_ask) for s in snaps)
        if tot <= D("0.99"):
            hits += 1
    return {"group_snapshots_checked": len(groups), "candidates": hits}


def evaluate(records, resolutions, window_start=WINDOW_START, window_days=WINDOW_DAYS, as_of=None):
    window_end = window_start + dt.timedelta(days=window_days)
    series = load_series(records)
    result = {"window_start": window_start.isoformat(), "window_end": window_end.isoformat(), "rules": {}}
    for name, (fn, horizon) in RULES.items():
        out = {}
        for model in ("optimistic", "pessimistic"):
            bets, ctrl, dropped = [], [], 0
            for slug, ser in series.items():
                for i, s in enumerate(ser):
                    if not (window_start <= s.t < window_end) or not eligible(s):
                        continue
                    prev = ser[i - 1] if i > 0 else None
                    side = fn(s, prev)
                    if side is None:
                        continue
                    payout = resolution_payout(resolutions, slug, s.end, as_of)
                    if payout is None:
                        dropped += 1
                    else:
                        b = simulate(ser, i, side, horizon, model, payout)
                        if b:
                            bets.append(b)
                        if horizon == "short":
                            c = simulate(ser, i, control_side(slug, name), horizon, model, payout)
                            if c:
                                ctrl.append(c)
                    break  # one entry per market per rule: first trigger only
            st = cluster_stats(bets)
            entry = {"stats": st, "passes_bar": passes(st), "dropped_unresolved_or_void": dropped}
            if horizon == "short":
                cst = cluster_stats(ctrl)
                entry["control"] = {"stats": cst, "passes_bar": passes(cst)}
            out[model] = entry
        pes = out["pessimistic"]
        harness_broken = bool(pes.get("control", {}).get("passes_bar"))
        out["verdict"] = ("HARNESS BROKEN (control passed)" if harness_broken
                          else "PASS" if pes["passes_bar"] else "FAIL")
        result["rules"][name] = out
    result["arbitrage_diagnostic"] = arbitrage_diagnostic(records)
    return result


def iter_records(path):
    for fn in sorted(glob.glob(os.path.join(path, "**", "books-*.jsonl.gz"), recursive=True)):
        with gzip.open(fn, "rt", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def main(argv=None):
    p = argparse.ArgumentParser(description="Pre-registered evaluation")
    p.add_argument("--data", required=True)
    p.add_argument("--resolutions", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    res = json.load(open(a.resolutions))
    report = evaluate(list(iter_records(a.data)), res)
    with open(a.out, "w") as f:
        json.dump(report, f, indent=1, default=str)
    for name, r in report["rules"].items():
        print(name, r["verdict"], r["pessimistic"]["stats"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
