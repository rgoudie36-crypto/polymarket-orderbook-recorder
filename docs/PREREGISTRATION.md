# Pre-registration: order-book imbalance paper test

> **PROPOSED — awaiting operator approval. NOT YET REGISTERED.**
>
> This file becomes binding when a commit changes this banner to `REGISTERED <date>`. That commit's hash is the registration.
> - Data recorded **before** that commit may be used only to check plumbing (does the code run), never to choose or change numbers.
> - Disclosure: before drafting, one snapshot's *structure* was inspected (2026-11-14: 221/800 books one-sided, median 7 price levels). No prices were compared with outcomes. No signal was looked at.

## 1. Hypothesis
When displayed depth near the top of a Polymarket US book is heavily lopsided, the price tends to resolve in the direction of the deep side. The effect is large enough to beat the spread plus the taker fee.

Prior, stated up front:
- [Guessing] This most likely fails.
- [Certain] These books are thin, and imbalance on thin books is often stale or spoofed.

## 2. Universe
Every book the recorder writes (see `docs/PLAN.md`): open markets ending within 72 h, at least one side quoted, up to 800 per run. A snapshot is **eligible** only if all of these hold:
- `state` is `MARKET_STATE_OPEN`.
- Both sides have at least one level.
- Spread (best ask − best bid) ≤ 0.05.
- Mid price is between 0.05 and 0.95.
- The snapshot is at least 1 hour before `end_date`.

No category filter: all categories count.

## 3. The one rule
**Depth.** Sum the displayed quantity of the **top 3 price levels** on each side:
- B = bid depth (buyers of the long side)
- A = offer depth (sellers of the long side)

**Trigger.** A snapshot triggers when **B ≥ 3 × A** or **A ≥ 3 × B**, and the deep side has **≥ 100 contracts** in its top 3 levels.

**Action.** Take the deep side:
- **B ≥ 3A → buy LONG.** Lift the offers from the best ask upward.
- **A ≥ 3B → buy SHORT**, i.e. sell long into the bids. Price paid per short contract = 1 − bid price.

**Size and fills.**
- Size is **10 contracts**.
- Fill by walking the displayed levels in the same snapshot, only up to the quantity shown.
- If fewer than 10 are shown, fill what is shown. Fewer than 1 means no bet.
- No partial-level assumptions, no queue priority, no price improvement.

**Frequency and exit.**
- **One bet per market:** the first trigger only. Later triggers on the same market are ignored.
- **Exit:** hold to resolution.
  - Payout is 1 per contract if the chosen side wins and 0 otherwise.
  - A 50-50 resolution pays 0.5.
  - A market voided or still unresolved 14 days after `end_date` is dropped and counted in the report.

## 4. Costs
- **Taker fee:** `fee = Θ × C × p × (1 − p)`, using each market's listed `fee_coefficient` (0.095 in testing, the new-account tier). Per docs.polymarket.us/fees, effective Nov 11, 2026.
  - C = contracts.
  - p = the fill price **of the side bought**, applied per level filled.
  - Total fee per bet is rounded to $0.01 using banker's rounding.
- **Spread** is paid implicitly by crossing to the far side.
- **No maker rebates.** No funding or interest.
- **Net P&L per bet** = payout × C − sum(fill price × qty) − fee.

## 5. Pass bar (all must hold)
1. **At least 100 bets.**
2. **Total net P&L > 0.**
3. **Stake-weighted t-statistic ≥ 2.**
   - Each bet's return is net P&L ÷ cost, weighted by cost.
   - Standard errors are clustered by **event**: an event = (`category`, `end_date`), so markets that resolve at the same instant in the same category form one cluster.
4. **No single event contributes more than 25% of total net P&L.**

## 6. Test window
- **Start:** the first recorder run after the registration commit.
- **End:** 28 days later.
- If fewer than 100 bets exist at day 28, extend **once** to day 56. If still under 100, the verdict is **inconclusive**, which counts as a fail.
- No other extensions.
- Recorder code may change during the window only to fix bugs. Each fix must be logged here with its date. Universe and parameters may not change.

## 7. Failure
- If the bar is not met, the rule is dead.
- No re-tuning of the 3× ratio, the 3 levels, the 100-contract minimum, the filters or the size on the same data.
- A new idea needs a new registration and new forward data.

## 8. Out of scope
Real money. That needs the operator's explicit go-ahead and a separate pre-registration.
