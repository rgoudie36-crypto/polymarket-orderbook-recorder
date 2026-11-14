# Pre-registration: three order-book rules, paper forward test

> **PROPOSED — awaiting operator's final "register it". NOT YET REGISTERED.**
>
> This file becomes binding when a commit changes this banner to `REGISTERED <date>`. That commit's hash is the registration.
> - Data recorded **before** that commit may be used only to check plumbing (does the code run), never to choose or change anything here.
> - Disclosure: before drafting, one snapshot's *structure* was inspected (2026-11-14: 221/800 books one-sided, median 7 price levels). No prices were compared with outcomes.
> - Rule selection: an advisory council, recorded in `docs/council/2026-11-14-strategy-council.md`.

## 0. Prior and what a null result means
- [Guessing] The most likely outcome is that **all three rules fail**.
- [Likely] Passing needs a real edge of several cents per contract after costs, which is rare on thin books.
- A pass would be evidence worth a second, independent forward test. It would **not** be a green light for money.
- If all three fail, the conclusion is: *at this scale, none of these simple order-book rules beats the spread plus the taker fee on Polymarket US.*

## 1. Data and universe
- **Data:** every recorder snapshot (see `docs/PLAN.md`), recorded every ~15 min for open markets ending within 72 h, up to 800 books per run.
- **Next snapshot of a market:** the next recorder run that contains it, if that run's `fetched_at` is within 30 minutes. If there is none, the next snapshot is "missing".

**Common eligibility.** A snapshot at time t is eligible only if all of these hold:
- `state` is `MARKET_STATE_OPEN`.
- Both sides have at least one level.
- t ≤ `end_date` − 1 h.
- **Sports:** t < `game_start_time`. Sports markets without `game_start_time` are excluded.

## 2. Common mechanics
**Sides.**
- *LONG* = buy the market's long side at the offers.
- *SHORT* = sell long into the bids, which is the same as buying the other side. Price paid per contract = 1 − bid.

**Fills.**
- **Size** is 10 contracts.
- Fill by walking the displayed levels of the snapshot, only up to the quantity shown.
- Fewer than 1 contract shown means no bet.
- No queue priority, no price improvement.

**Fees.** On every taker fill, entry and exit: `fee = fee_coefficient × qty × p × (1 − p)` per level, where p is the long-side price of that level. The total per bet is rounded to $0.01 using banker's rounding (docs.polymarket.us/fees, effective Nov 11, 2026).

**Limits.** One entry per market per rule: the first trigger only.

**Two fill models.** Every bet is computed both ways. **Pass or fail is judged on PESSIMISTIC only.**
- **OPTIMISTIC:** enter at snapshot t's book.
- **PESSIMISTIC:**
  - The entry price is the worse of the fill prices at t and at the next snapshot (t+1).
  - The size is the smaller of the two fillable sizes.
  - If t+1 is missing or shows nothing fillable, there is no bet.

**Short-horizon exit (rules 1 and 3).** Close by crossing the spread, walking the displayed levels:
- **Where:**
  - OPTIMISTIC exits at t+1.
  - PESSIMISTIC exits at t+2, the snapshot after the confirmation.
- **How:** LONG sells into bids; SHORT buys back at offers.
- **Fallbacks:**
  - If the exit snapshot is missing, use the next available snapshot within 60 minutes.
  - If there is still none, hold to resolution.
  - Quantity the exit book can't absorb is held to resolution.

**Resolution.**
- Pays 1 per contract to the winning side, 0 to the losing side, and 0.5 each on a 50-50.
- Markets that are void or unresolved 14 days after `end_date` are dropped and reported.

## 3. The three rules

### Rule 1: Imbalance, short horizon
- **Depth:** B = summed quantity of the top 3 bid levels; A = the same for the top 3 offer levels.
- **Filters:** spread ≤ 0.05; mid in [0.10, 0.90].
- **Trigger:**
  - **LONG** if B ≥ 3 × A and B ≥ 100.
  - **SHORT** if A ≥ 3 × B and A ≥ 100.
- **Exit:** short-horizon exit.

### Rule 2: Favorites, hold to resolution
- **Window:** 1 h ≤ `end_date` − t ≤ 24 h, with the sports pre-game rule from §1.
- **Filter:** spread ≤ 0.03.
- **Trigger:**
  - **LONG** if best ask ∈ [0.85, 0.94].
  - Otherwise **SHORT** if 1 − best bid ∈ [0.85, 0.94].
- **Exit:** hold to resolution.

### Rule 3: Follow the trades, short horizon
- **Compare** with the market's previous snapshot, which must be within 30 minutes.
- **Trigger requires all of these:**
  - `shares_traded` increased.
  - `last_trade_px` moved by at least 0.03.
  - Spread ≤ 0.04 now.
  - Mid in [0.10, 0.90] now.
- **Direction:** price moved up → **LONG**; moved down → **SHORT**.
- **Exit:** short-horizon exit.

## 4. Controls (logged, never counted toward a pass)
- **Random-side control:** for every rule-1 and rule-3 entry, take the same market and snapshot with a side chosen by `sha256(slug + rule)` (first byte even → LONG). Evaluate it the same way.
  - **If any control clears the pass bar, the test harness is declared broken and every result is void until it is fixed.**
- **Arbitrage diagnostic:** count snapshots in which an event's mutually exclusive markets have asks summing (plus fees) to ≤ 0.99. Report the count only; no P&L claims.

## 5. Pass bar (per rule, PESSIMISTIC fills; all must hold)
1. **At least 100 bets.**
2. **Total net P&L > 0.**
3. **Stake-weighted mean return t-statistic ≥ 2.4.**
   - Return = net P&L ÷ entry cost.
   - Standard errors are cluster-robust, with **cluster = (category, UTC date of `end_date`)**. That grouping is coarser than event because same-day outcomes move together.
   - 2.4 roughly holds the family-wise false-pass rate near 2.5% across three rules.
4. **No single cluster contributes more than 25% of total net P&L.**

Also reported, not pass criteria:
- OPTIMISTIC results.
- A cluster-bootstrap one-sided p-value (10,000 resamples, seed 20261114).
- Bets per day.
- Fill rates.

## 6. Test window
- **Start:** the first recorder run after the registration commit.
- **End:** **56 days** later. No extensions.
- Fewer than 100 bets for a rule counts as **inconclusive = fail** for that rule.
- **Analysis:** after the last market in the window resolves, at most 14 days after the end.
- Raw snapshots expire 90 days after they are recorded, so encrypted copies go to the operator's Drive `data/` folder before day 75.
- **Code changes during the window:**
  - Recorder code may change only to fix bugs, each logged here with its date.
  - The universe, the parameters above and the evaluation code do not change.
  - The evaluation code is committed before the window ends, without looking at any results.

## 7. Failure
- A rule that fails is dead. Nothing above is re-tuned on this data.
- New ideas need a new registration and new forward data.

## 8. Out of scope
Real money. That needs the operator's explicit go-ahead and a separate pre-registration.

## Change log
- (none yet)
