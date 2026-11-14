"""Fetch resolution outcomes for recorded markets (public endpoint, no keys).

Usage: python -m analysis.resolve --slugs slugs.txt --out resolutions.json

Output: {slug: {"payout_long": "1"|"0"|"0.5"|..., "status": ..., "checked_at": ...}}
payout_long is the settled price of the market's LONG side (marketSides[long=true].price),
present only when the market is closed with status MARKET_STATUS_RESOLVED.
"""

import argparse
import datetime as dt
import json
import sys

from recorder.client import Client, HttpError


def parse_resolution(market):
    long_side = next((s for s in market.get("marketSides") or [] if s.get("long")), None)
    resolved = market.get("closed") and market.get("status") == "MARKET_STATUS_RESOLVED"
    return {
        "status": market.get("status"),
        "payout_long": long_side.get("price") if (resolved and long_side) else None,
    }


def fetch(client, slugs):
    out, now = {}, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for s in slugs:
        try:
            m = client.get_json(f"/v1/market/slug/{s}").get("market", {})
            out[s] = dict(parse_resolution(m), checked_at=now)
        except HttpError as e:
            out[s] = {"status": f"HTTP_{e.status}", "payout_long": None, "checked_at": now}
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--slugs", required=True, help="file with one slug per line")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    slugs = sorted({l.strip() for l in open(a.slugs) if l.strip()})
    res = fetch(Client(), slugs)
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    print(f"{sum(1 for r in res.values() if r['payout_long'] is not None)}/{len(res)} resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
