"""Load recorded snapshots and compute generic book quantities.

Deliberately contains no trading rule and no signal search: see docs/PREREGISTRATION.md.
"""

import glob
import gzip
import json
import os
from decimal import Decimal


def iter_books(path):
    """Yield book records from a books-*.jsonl.gz file or a directory tree of them."""
    files = [path] if os.path.isfile(path) else sorted(glob.glob(os.path.join(path, "**", "books-*.jsonl.gz"), recursive=True))
    for fn in files:
        with gzip.open(fn, "rt", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def book_summary(rec, levels=None):
    """Best bid/ask, spread, mid and displayed depth (qty) per side over the top `levels` levels."""
    bids = sorted(((Decimal(p), Decimal(q)) for p, q in rec.get("bids", [])), reverse=True)
    offers = sorted((Decimal(p), Decimal(q)) for p, q in rec.get("offers", []))
    if levels is not None:
        bids, offers = bids[:levels], offers[:levels]
    best_bid = bids[0][0] if bids else None
    best_ask = offers[0][0] if offers else None
    return {
        "slug": rec.get("slug"),
        "fetched_at": rec.get("fetched_at"),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": (best_ask - best_bid) if bids and offers else None,
        "mid": (best_ask + best_bid) / 2 if bids and offers else None,
        "bid_depth": sum((q for _, q in bids), Decimal(0)),
        "ask_depth": sum((q for _, q in offers), Decimal(0)),
    }
