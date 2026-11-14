# Plan: Polymarket US order-book recorder

Status: Phase 1 code written. Recording is not switched on yet; it waits on the storage decision below.

## What this is, and what it is not

This repo is a passive recorder of **public, unauthenticated** Polymarket US order books (`https://gateway.polymarket.us`). Later, the recorded data will be used to paper-test **one** pre-registered order-book-imbalance rule.

It does not:
- use keys or accounts
- place or simulate orders
- track wallets or on-chain data
- read X/Twitter
- run LLM "crowd simulation"
- send real-time alerts

GitHub Actions cannot react inside 10 seconds. This is a recorder, not an alert bot.

## Phases

1. **Record (2–4 weeks, $0).** Snapshot books about every 15 minutes.
2. **Pre-register.** Write the single rule and its pass bar in `docs/PREREGISTRATION.md`, then commit it *before* anyone looks at recorded data for signal.
3. **Forward paper test.** Run the rule against the bar on data recorded *after* the pre-registration commit.

Honest prior:
- [Guessing] Imbalance signals on thin books usually disappear once you pay the spread and the taker fee.
- [Certain] These books are thin. In the first test snapshot, 221 of 800 quoted near-expiry markets had only one side quoted, and the median book had 7 price levels in total.

## Universe: why not "all open markets"

[Certain] On 2026-11-14 the gateway listed **~79,800 markets** as `active=true&closed=false`.

At our pace of ~0.1 s per request, fetching a book for every one of them would take more than 2 hours per run. Most of those markets also resolve in 2027, so a 2–4-week paper test could never score them.

The recorder therefore samples, each run:
1. **Listing.** It lists open markets whose `endDate` falls in the next **72 hours** (`endDateMin`/`endDateMax` filters, pages of 500). That is about 2,800 markets in ~6 requests.
2. **Filtering.** It keeps those with at least one quoted side in the listing. That is about 1,150 markets.
3. **Fetching.** It fetches full-depth books for the **800 soonest-ending** of them, stopping early if it exceeds a 240 s time budget.

Known bias [Certain]:
- The sample is near-expiry markets only. In the test it was mostly sports, crypto and climate.
- Markets ending 2–3 days out are sometimes dropped when the cap binds. They get picked up as they approach expiry.

Pre-registration must describe the rule's results in terms of this universe and nothing wider.

## Data schema (schema version 1)

Each run writes two files.

**`books-<run_id>.jsonl.gz`** holds one JSON object per market:

| field | meaning |
|---|---|
| `schema`, `run_id`, `fetched_at` | version; run start (UTC); time this book was fetched (UTC) |
| `slug`, `market_id`, `question`, `title`, `long_side`, `outcomes` | identity. `bids`/`offers` are for the **long** side named in `long_side`. |
| `category`, `subcategory`, `market_type`, `sports_market_type` | classification |
| `start_date`, `end_date`, `game_start_time` | market metadata timestamps |
| `fee_coefficient`, `tick`, `min_trade_qty` | trading parameters as listed |
| `listing_best_bid`, `listing_best_ask` | top of book from the listing call. It can differ slightly from the book fetched a few seconds later. |
| `state`, `transact_time` | book state (e.g. `MARKET_STATE_OPEN`); gateway timestamp |
| `bids`, `offers` | full depth, as `[[price, qty], ...]`. Values are decimal **strings**, exactly as served. |
| `last_trade_px`, `current_px`, `shares_traded`, `notional_traded`, `open_interest` | stats from the book endpoint |

**`run-<run_id>.json`** holds run metadata:
- counts: listed, quoted, selected and written markets
- errors, with slug and HTTP status
- request count, retries and bytes
- timings, and whether the time budget truncated the run
- parameters

Resolution outcomes are **not** recorded each run. At analysis time, one call per distinct slug to `GET /v1/market/slug/{slug}` gives `closed`, `status` (e.g. `MARKET_STATUS_RESOLVED`) and `outcomePrices`. [Certain] That endpoint returned resolved state for a resolved market in testing.

## Cadence, run time and storage (measured, not guessed)

Local test run on 2026-11-14 (800 books, 0.1 s pacing):

| measure | result |
|---|---|
| total time | **87 s** (listing 4 s) |
| requests | 806, with **0 retries** and 0 errors |
| data downloaded | 9.7 MB |
| snapshot size | **69 KB gzipped** |

| item | estimate |
|---|---|
| Actions time per run | [Likely] ~2 min including runner setup. To be confirmed from the first GitHub-hosted run. |
| Runs per day at 15-min cadence | 96 |
| Storage per day | [Likely] ~7 MB (96 × ~70 KB); ~200 MB over 4 weeks |
| Actions cost | [Likely] $0. Standard GitHub-hosted runners are free for public repos. |

Rate limit:
- [Certain] The public limit is documented as **25 req/s** per IP (docs.polymarket.us, rate-limits page), not 20.
- We run at ≤10 req/s.
- On 429 or 5xx we wait 1 s, then back off exponentially up to 4 retries, as the docs ask.

Scheduling:
- **Primary:** cron-job.org calls the GitHub API `workflow_dispatch` endpoint every 15 minutes.
- **Backup:** GitHub `schedule` runs hourly at :41. It only fires from the default branch and only when `RECORDING_ENABLED=true`.
- The `concurrency` group stops runs from overlapping.

## Storage and the terms question (unresolved, needs the operator)

What I found (checked 2026-11-14):
- [Certain] The **Polymarket US Rulebook** (polymarketexchange.com/files/legal/latest/rulebook, dated Sept 30, 2026) says: *"Any Person receiving information through the Trading System is expressly prohibited from redistributing such information unless expressly permitted by the Company."* "Trading System" is defined to include API connectivity.
- [Certain] The **Participant Agreement** (¶22) says data "may not be redistributed except as PMUS expressly permits". That binds account holders.
- [Certain] The docs route market-data use to a **Market Data Agreement**: "Contact data@polymarket.us". Its text is not public.
- [Likely] Recording public book data for private research is not prohibited by anything I could read.
- [Likely] Publishing it is: committing it to a public repo is redistribution.
- [Guessing] Whether the Rulebook binds an anonymous API reader is untested. I would not rely on it not binding.
- Not checked: the polymarket.us/tos body did not render. I found no scraping or automated-access clause in the documents I could read.

Consequences:
1. **Never commit recorded data to this repo.** `.gitignore` excludes `out/` and data files.
2. **GitHub Actions artifacts are not private on a public repo.** [Certain] Any signed-in GitHub user can download a public repo's artifacts. Storing snapshots as artifacts here is therefore close to publishing them. Upload is off by default, gated by the `RECORDING_ENABLED` repository variable.
3. Options for the operator, with my ranking:
   - **(a) Email data@polymarket.us** and ask whether private recording for personal research is fine and whether artifacts are OK. Free, and slow. Do it regardless of which option you pick.
   - **(b) Make this repo private.** Then artifacts are private. The cost is that Actions minutes count against the 2,000 free minutes per month. At ~2 billed minutes × 96 runs/day that is about 5,800 minutes per month, so it **exceeds the free tier**. A 30-minute cadence still exceeds it (~2,900). Hourly fits (~1,450).
   - **(c) Keep the repo public and encrypt artifacts** with a public key stored in the repo. Only the operator's offline private key can decrypt them. This needs no Polymarket keys and no GitHub secrets, because the private key never touches GitHub. The cost is one small dependency (`age` or `openssl`, which is preinstalled on runners).
   - **(d) Run the recorder on the operator's own machine** (cron or Task Scheduler). Fully private and free, but it depends on that machine being on.
   - **My pick:** (c) plus (a). Encrypt with `openssl` and keep 15-minute public-repo runs. I'll build it if you agree.

## Analysis (Phases 2–3)

- `analysis/load.py` reads snapshot files into rows and computes generic per-book quantities: depth by side, spread and mid.
- It contains **no rule and no signal search**.
- Rule code gets written only after `docs/PREREGISTRATION.md` is committed and frozen.
