# Question
Which top 3 order-book-based paper-trading strategies should be pre-registered for a 28-day forward test on Polymarket US public order book snapshots? (15-min snapshots of ~800 markets ending within 72h; sports/crypto/climate; thin books, ~28% one-sided, median 7 levels; taker fee 0.095·C·p(1−p); paper fills only up to displayed size; pass bar per rule ≥100 bets, net>0, stake-weighted t≥2 clustered by event, ~2.4 if 3 rules; no parameters from recorded data; no external feeds. Current candidate: top-3-level depth imbalance ≥3x, deep side ≥100, buy deep side 10 contracts, hold to resolution, spread≤0.05, mid 0.05–0.95, ≥1h before end.)

## Response A
Pick three rules that share one fill engine (signal → depth-walk fill up to 10 contracts → fee → ledger by event_id → resolution fetch → clustered stake-weighted t-test). Universal: one entry per market (first trigger), two-sided book, ≥1h to end.
1. Imbalance as written + require both sides ≥1 level.
2. Favorite-longshot: buy YES at ask when 0.85≤ask≤0.95, spread≤0.03, ends in 2–24h; hold, 10 contracts. Fee ~0.0086/contract at 0.9.
3. 1-hour momentum: |mid_now − mid 4 snapshots ago| ≥0.10, both mids in 0.10–0.90, buy direction, spread≤0.05, hold.
Monday: signals.py with constants hard-coded and hash in PREREG; fill_sim.py; resolve.py nightly; daily bets-per-rule count (flag if <100 projected by day 14, no changes). Skip YES/NO arbitrage pairing — complement mapping isn't guaranteed in the API.

## Response B
Imbalance rule has a fatal flaw: "buy the deep side" is ambiguous; deep bids means lifting a thin ask; deep resting walls are usually one stale MM quote. One-sided books make ratio infinite — exclude.
Bigger: power. Held to resolution at p≈0.5, per-bet SD ~0.5; with ~100 event clusters, t≥2.4 needs ~0.12/contract edge after fees. Mid-priced hold-to-resolution rules are near-unpassable.
1. Extreme favorites: first snapshot with 1–6h to end (sports: pre game_start_time), buy side with ask in [0.85,0.94], spread≤0.03, min(10, displayed), hold.
2. Imbalance rewritten: bid depth L1–3 ≥3× ask depth, bid depth ≥100, both sides non-empty → buy YES at ask, exit at the bid ONE snapshot later (microstructure, not outcome noise). Spread≤0.05, mid 0.10–0.90.
3. Kill the third slot — two rules lowers bar to ~t≥2.24.
Also: complement sanity check; report trigger rate before day 7.

## Response C
Insider blind spots: (1) spell out the action ("if bid depth ≥3× ask depth, buy YES at best ask up to 10; mirror for NO"). (2) one bet per market or counts are inflated. (3) for sports, end_date can be days after the game; require now < game_start_time − 15min or skip markets lacking it. (4) fee math: at p=0.5, 10 contracts ≈ $0.24 fee on $5 stake (~5%) before spread.
Picks: A. imbalance made explicit. B. favorite at extremes: pre-game, ask 0.85–0.95, spread≤0.03, buy 10, hold, one per market. C. stale-quote: if last_trade − mid ≥0.05 and shares traded increased since previous snapshot, buy toward last trade up to displayed size.
Plus a non-counted random-side control on every market where any rule fires; if the control "passes", the harness is broken.

## Response D
Real question: where is price wrong by more than spread+fee? Depth imbalance on a 7-level book is just where one MM sits — drop it. Each pick needs a named mechanism:
1. Cross-market coherence arbitrage (no outcome risk): totals ladder YES(L1)+NO(L2) asks + fees ≤0.99; two-sided moneylines sum of asks + fees ≤0.99; size min(displayed,10) both legs; hold. May not reach 100 bets but positive result is real by construction.
2. Favorite-longshot: favorite ask in [0.80,0.92], spread≤0.03, sports only, after game_start_time, 1–6h before end_date; one entry, 10 contracts, hold.
3. Informed-flow follow: notional traded rises ≥$250 between consecutive snapshots and last trade moves ≥0.03 → buy in that direction if ask ≤ new last trade + 0.01, spread≤0.04, mid 0.10–0.90, ≥1h before end.
t≥2.4 clustered; one position per market; log outcomes even when fill impossible.

## Response E
Imbalance is the least interesting idea; bigger edges are in fee/event-structure/timing interactions.
1. Late-favorite harvest: first snapshot with 1h ≤ time-to-end ≤ 6h, best ask 0.85–0.95, spread≤0.03, displayed ask qty ≥10; buy 10, hold. Most bets, best power.
2. Cross-market overround arbitrage: events with ≥2 mutually exclusive markets, sum of best asks + fees ≤0.98 → buy min(10, smallest displayed) of every outcome. Cheap to register; trigger count itself is informative.
3. In-play momentum: sports after game_start_time, mid moved ≥0.15 from last pre-game snapshot, mid 0.20–0.85, spread≤0.05, ≥1h to end → buy toward the move, hold.
Keep imbalance as logged shadow rule only (no multiple-testing cost). Keep recording full books after failures — maker strategies (posting inside wide spreads) are the real upside next round.

## Anonymization key
A = Executor, B = Contrarian, C = Outsider, D = First Principles, E = Expansionist.

## Peer reviews (summarized)
- All five reviewers rated **B** the strongest response. It was the only one that checked whether a rule could actually pass the bar: hold-to-resolution bets near p≈0.5 need about 12¢ per contract of edge.
- All five rated **D** as having the biggest blind spot, with E's arbitrage close behind. Multi-leg "riskless" arbitrage on 15-minute snapshots mostly catches stale quotes, and it can't reach 100 bets.
- What every advisor missed:
  1. **Stale fills and adverse selection.** A quote worth taking is the one most likely to vanish. Pre-register a pessimistic fill: the quote must still be shown at the next snapshot, and the fill is at the worse of the two prices and the smaller of the two sizes.
  2. **The favorite rule is underpowered too.** At p≈0.9 the per-bet SD is about 0.3, so passing needs about 7¢ per contract versus the typical 1–3¢ bias.
  3. **The effective sample is smaller than the event count.** Crypto strikes resolve on one underlying, and sports share league-day shocks. Cluster more coarsely.
  4. **Rules overlap on the same markets.**
  5. **Nobody said what a null result means.**
  6. **Skewed payoffs at extreme prices make a t-test at n≈100 fragile.**

## Chairman verdict
**Agree:**
- One entry per market.
- Both sides of the book must be non-empty.
- Spell out the action direction.
- Sports entries happen before game start.
- Add a non-counted random-side control.
- Imbalance held to resolution is close to untestable.

**Clash:**
- Two rules or three.
- Whether arbitrage gets a slot.
- In-play versus pre-game.

**Recommendation (pending operator approval):**
1. **Imbalance, short horizon (B's rewrite).** Buy the side the deep book leans toward, at the ask. Exit at the opposite best quote in the next snapshot.
2. **Favorite-longshot (pre-game / ≥1h before end).** Ask in [0.85, 0.94], spread ≤0.03, hold to resolution.
3. **Flow-follow, short horizon (D's #3).**
   - Enter when shares traded rose and last trade moved ≥0.03 since the previous snapshot. Buy in that direction.
   - Exit at the next snapshot.

**Also:**
- Arbitrage and the random-side control are logged and do not count.
- Every rule must pass under the pessimistic fill.
- The bar is t ≥ 2.4, with clusters = (category, UTC date of end_date).
- The window is 56 days, not 28, for power.
- A null result is stated in advance: none of these simple rules beats costs at this scale.
