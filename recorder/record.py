"""Record one snapshot of public Polymarket US order books.

Usage: python -m recorder.record --out out/ [--horizon-hours 72] [--max-books 800]

Writes, into --out:
  books-<run_id>.jsonl.gz   one JSON object per market book (schema in docs/PLAN.md)
  run-<run_id>.json         run metadata: counts, timings, errors, parameters
"""

import argparse
import datetime as dt
import gzip
import json
import os
import sys
import time

from recorder.client import Client, HttpError

SCHEMA_VERSION = 1
PAGE_LIMIT = 500  # largest page size the gateway returned in testing


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def list_universe(client, now, horizon_hours, max_pages=40):
    """Open markets whose endDate falls within [now, now + horizon]."""
    params = {
        "active": "true",
        "closed": "false",
        "limit": PAGE_LIMIT,
        "endDateMin": iso(now),
        "endDateMax": iso(now + dt.timedelta(hours=horizon_hours)),
    }
    markets, offset = [], 0
    for _ in range(max_pages):
        page = client.get_json("/v1/markets", dict(params, offset=offset)).get("markets", [])
        markets.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
    # De-duplicate by slug (offset paging can shift if markets change mid-listing).
    seen, out = set(), []
    for m in markets:
        if m.get("slug") and m["slug"] not in seen:
            seen.add(m["slug"])
            out.append(m)
    return out


def _quote(m, key):
    q = m.get(key)
    return q.get("value") if isinstance(q, dict) else None


def select_for_books(markets, max_books):
    """Markets with at least one quoted side, soonest endDate first, capped."""
    quoted = [m for m in markets if _quote(m, "bestBidQuote") or _quote(m, "bestAskQuote")]
    quoted.sort(key=lambda m: (m.get("endDate") or "", m["slug"]))
    return quoted[:max_books], len(quoted)


def _levels(levels):
    return [[lv.get("px", {}).get("value"), lv.get("qty")] for lv in levels or []]


def _px(stats, key):
    v = stats.get(key)
    return v.get("value") if isinstance(v, dict) else v


def normalize(market, book, run_id, fetched_at):
    md = (book or {}).get("marketData", {}) or {}
    stats = md.get("stats") or {}
    long_side = next((s for s in market.get("marketSides") or [] if s.get("long")), {})
    return {
        "schema": SCHEMA_VERSION,
        "run_id": run_id,
        "fetched_at": fetched_at,
        "slug": market.get("slug"),
        "market_id": market.get("id"),
        "question": market.get("question"),
        "title": market.get("title"),
        "long_side": long_side.get("description"),
        "outcomes": market.get("outcomes"),
        "category": market.get("category"),
        "subcategory": market.get("eventSubcategory"),
        "market_type": market.get("marketType"),
        "sports_market_type": market.get("sportsMarketType"),
        "start_date": market.get("startDate"),
        "end_date": market.get("endDate"),
        "game_start_time": market.get("gameStartTime"),
        "fee_coefficient": market.get("feeCoefficient"),
        "tick": market.get("orderPriceMinTickSize"),
        "min_trade_qty": market.get("minimumTradeQty"),
        "listing_best_bid": _quote(market, "bestBidQuote"),
        "listing_best_ask": _quote(market, "bestAskQuote"),
        "state": md.get("state"),
        "transact_time": md.get("transactTime"),
        "bids": _levels(md.get("bids")),
        "offers": _levels(md.get("offers")),
        "last_trade_px": _px(stats, "lastTradePx"),
        "current_px": _px(stats, "currentPx"),
        "shares_traded": stats.get("sharesTraded"),
        "notional_traded": _px(stats, "notionalTraded"),
        "open_interest": stats.get("openInterest"),
    }


def run(client, out_dir, horizon_hours=72, max_books=800, time_budget=240.0,
        now=None, clock=time.monotonic, wallclock=None):
    wallclock = wallclock or (lambda: dt.datetime.now(dt.timezone.utc))
    now = now or wallclock()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    t0 = clock()
    os.makedirs(out_dir, exist_ok=True)
    books_path = os.path.join(out_dir, f"books-{run_id}.jsonl.gz")

    markets = list_universe(client, now, horizon_hours)
    chosen, n_quoted = select_for_books(markets, max_books)
    t_list = clock() - t0

    errors, written, truncated = [], 0, False
    with gzip.open(books_path, "wt", encoding="utf-8") as f:
        for m in chosen:
            if clock() - t0 > time_budget:
                truncated = True
                break
            try:
                book = client.get_json(f"/v1/markets/{m['slug']}/book")
            except HttpError as e:
                errors.append({"slug": m["slug"], "status": e.status})
                continue
            rec = normalize(m, book, run_id, iso(wallclock()))
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
            written += 1

    meta = {
        "schema": SCHEMA_VERSION,
        "run_id": run_id,
        "started_at": iso(now),
        "finished_at": iso(wallclock()),
        "params": {"horizon_hours": horizon_hours, "max_books": max_books, "time_budget_s": time_budget,
                   "min_interval_s": client.min_interval},
        "markets_listed": len(markets),
        "markets_quoted": n_quoted,
        "books_selected": len(chosen),
        "books_written": written,
        "truncated_by_time_budget": truncated,
        "errors": errors,
        "requests": client.requests_made,
        "retries": client.retries,
        "bytes_received": client.bytes_received,
        "listing_seconds": round(t_list, 2),
        "total_seconds": round(clock() - t0, 2),
        "books_file_bytes": os.path.getsize(books_path),
    }
    with open(os.path.join(out_dir, f"run-{run_id}.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="out")
    p.add_argument("--horizon-hours", type=float, default=72)
    p.add_argument("--max-books", type=int, default=800)
    p.add_argument("--time-budget", type=float, default=240.0)
    p.add_argument("--min-interval", type=float, default=0.1)
    a = p.parse_args(argv)
    meta = run(Client(min_interval=a.min_interval), a.out, a.horizon_hours, a.max_books, a.time_budget)
    print(json.dumps({k: v for k, v in meta.items() if k != "errors"} | {"n_errors": len(meta["errors"])}, indent=2))
    # Fail the job only if nothing useful was recorded.
    return 0 if meta["books_written"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
