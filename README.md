# polymarket-orderbook-recorder

This project records public Polymarket US order books on a schedule. The recordings are for a pre-registered paper test of order-book imbalance.

It uses no keys and places no trades. It never sends orders.

- `recorder/`: snapshot code. It uses only the Python standard library and only the public, unauthenticated `gateway.polymarket.us` endpoints, at 10 requests per second or less.
- `analysis/`: loaders and generic book statistics. It contains no rule until the pre-registration is frozen.
- `tests/`: offline tests. Run them with `python -m unittest discover -s tests -t .`
- `docs/PLAN.md`: the design, data schema, cost and storage estimates, and the terms-of-service findings.
- `docs/PREREGISTRATION.md`: the Phase 2 rule and pass bar. It is a draft until registered.

Recorded data is **not** committed here. Raw books are encrypted to the operator's public key before they are stored as Actions artifacts, because Polymarket US rules restrict redistribution. See `docs/PLAN.md`.

Run it locally:

```
python -m recorder.record --out out
```
