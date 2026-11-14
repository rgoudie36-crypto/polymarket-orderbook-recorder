# Pre-registration: order-book imbalance paper test

> **DRAFT. NOT REGISTERED.** No rule numbers have been chosen. Nobody has looked at the recorded data for signal.
>
> This file becomes binding when a commit changes this banner to `REGISTERED <date>` and fills in every `TBD`. That commit's hash is the registration. Data recorded **before** that commit may be used only to check the plumbing, never to choose numbers.

## 1. Hypothesis
TBD. One sentence, for example: "When the long side's displayed depth is much larger than the short side's, the price tends to move toward the deep side's direction before expiry, by more than the cost of crossing the spread plus fees."

## 2. Universe
The markets the recorder samples (see `docs/PLAN.md`): open Polymarket US markets ending within 72 h, with at least one side quoted, and up to 800 per run.
- Categories in or out: TBD.
- Minimum depth or book-state filters: TBD.

## 3. The one rule
- **Imbalance measure:** TBD. Which levels count (top N or within X ticks of the best price), and whether depth is measured in quantity or in notional.
- **Threshold:** TBD (e.g. ratio > k). k is chosen **once**, here, before looking at data.
- **Action:** take the deep side at the best displayed price. Fill only quantity that the book showed. No partial-level fantasy and no queue priority.
- **Stake:** TBD (fixed contracts, or fixed $).
- **One bet per market:** TBD (first trigger only?).
- **Exit:** hold to resolution. Any other exit is TBD and must be fixed here.

## 4. Costs
- **Taker fee** per docs.polymarket.us/fees (effective Nov 11, 2026): `fee = Θ × C × p × (1 − p)`, rounded to $0.01 using banker's rounding.
- Use the **listed** `feeCoefficient` per market. That was 0.095 in testing, the lowest-volume tier, which is the honest tier for a new account.
- **Spread** is paid implicitly by buying at the ask.
- **No maker rebates.**

## 5. Pass bar (all must hold)
- At least 100 paper bets.
- Net P&L > 0 after fees and spread.
- Stake-weighted t-statistic ≥ 2, with standard errors clustered by **event** (TBD: how markets map to events, e.g. a game with multiple markets counts as one cluster).
- TBD: a maximum share of P&L from any single event.

## 6. Test window
Forward only. The test uses data recorded after the registration commit, from TBD to TBD, or until N bets, whichever comes first. No extensions.

## 7. What counts as failure
If the bar is not met, the rule is dead. No re-tuning of k, levels or filters on the same data. A new rule needs a new registration and new forward data.

## 8. Out of scope
Real money. That would need the operator's explicit go-ahead and a separate pre-registration.
