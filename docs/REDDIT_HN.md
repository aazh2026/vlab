# Reddit posts — vlab

> Copy-paste ready. Post manually (accounts need real login + karma).
> Rules honoured: no stock picks, no return promises, no DM spam, disclose affiliation.

---

## A) r/algotrading

**Title**

`I refactored my own backtest script and it had a bug that made cash look like a 13x return`

**Body**

```markdown
I wrote a small backtest script for my own asset allocation. It produced a nice
equity curve and I was about to make real investment decisions based on the
number it gave me.

Then I started rewriting it properly — real data sources, holiday alignment,
transaction costs, metric unit tests. The tests immediately caught four bugs.
Each one was severe enough to invert the conclusion.

| Bug | What it produced |
|---|---|
| A-share and US holidays not aligned | -90% drawdown, 1618% volatility |
| Money-market ETF yield evaporated | "all cash" showed 0% CAGR (true: 1.67%) |
| Weights over-normalised | a fake -30% year in 2008 |
| Window bias (not a code bug) | backtested 2001 using ETFs that listed in 2014 |

The last one is the nastiest: the code was completely correct and the
conclusion was still completely wrong. It let assets that did not exist yet
enter the backtest early, which *understated* drawdown. So I split the
evaluation into two windows that are never mixed:

- **Investable Reality** — starts when every tradable asset already exists
- **Index-Proxy Long Window** — indices stand in for pre-listing ETFs, so
  2008 is covered

The honest conclusion from my own allocation, across 18 years containing the
2008 crisis: drawdown held to **-9.96%** vs **-52.89%** for the CSI 300 ETF
and **-47.27%** for the S&P 500. The price is 5.7 percentage points of annual
return (4.77% vs 10.56%).

So the value of the allocation is **drawdown control, not return maximisation**.

Two more honest negatives that I did not hide: a gold-banding overlay adds
only ~0.3pp of CAGR, and an MA200 trend-risk layer I added measurably does
nothing. Both are documented in the "known limitations" section.

I also introduced the fifth bug *during* the refactor, which is the part I
find most humbling: I extracted the rebalance function and passed `cash` as a
float, so `cash -= cost` mutated a local copy and buying never actually
deducted money. The cash strategy reported **23.65% CAGR against a true
1.8%**. The regression test caught it. Without that test I would have
published it as an improvement.

Repo: https://github.com/aazh2026/vlab
Live dashboard: https://postcodeengineering.com/vlab/

- Python standard library only, zero runtime dependencies
- Zero CDN, single-file dashboard that opens offline
- 93 regression tests, CI on Python 3.9–3.12
- Includes a cash-vs-house module (mortgage amortisation, rent tax, vacancy,
  break-even rent, and a price × rent × rate sensitivity grid) — it ingests no
  listing data, because asking prices are not transaction prices

Standard disclaimer: all results are backtests on historical data. Past
performance does not predict future returns, and nothing here is investment
advice, an offer, or a recommendation. Investing involves risk — you are
solely responsible for your own decisions.

I am the author of this project. Happy to answer questions about the engine
or the bugs.
```

---

## B) r/Python

**Title**

`Zero-dependency backtesting lab in pure stdlib — including the regression test that caught a cash-accounting bug I introduced myself`

**Body**

```markdown
Sharing a project I built for myself that others might find useful: **vlab**,
a multi-asset allocation backtesting lab with **zero third-party runtime
dependencies** — Python standard library only.

Why zero dependencies: I wanted to open the dashboard on a plane, and I
wanted the thing to still work in five years. It also forced a design where
every number is computed by code I can read.

```python
from vlab import engine, strategies, windows

series = engine.load_series()
dates  = engine.trading_dates(series)
mat    = engine.align(series, dates)
D, M = windows.slice_window(dates, mat, "A")   # investable-reality window

res = engine.backtest(strategies.STRATEGIES["steve"].fn, M, D,
                       start_cash=1_000_000, fee_bps=5, slip_bps=3)
metrics = engine.metrics_of(res["curve"])
```

The dashboard is a single self-contained HTML file with hand-drawn inline SVG
(no charting library, no CDN) — it opens offline from a `file://` URL.

The part I actually want to talk about is the testing. I refactored my own
throwaway backtest script into something real, and the regression tests
immediately caught four bugs that each inverted the conclusions:

```python
def test_cash_conservation(self):
    # BUG: cash was passed as a float, so `cash -= cost` mutated a local
    # copy and buying never deducted money. The cash strategy reported
    # 23.65% CAGR against a true 1.8%.
    ...
```

That one was introduced *by me, during the refactor*. I had written the test
for the previous bug class and it caught the new one anyway, which is the
whole argument for having it.

Three other things worth stealing:

1. **Holiday alignment.** A-shares and US equities have different holidays.
   Forward-fill onto a unified trading axis. Forgetting this produces a
   -90% drawdown from nothing.
2. **Two windows, never mixed.** If some assets listed later than others, a
   single backtest window lets assets that didn't exist yet enter early.
   Separate "what you could actually buy" from "a longer history using
   index proxies".
3. **Money-market ETFs don't look like they earn.** Net asset value is
   constant at 100 and distributions come as units, so price series show
   literally 0% return. Synthesise the yield.

93 tests, ~0.3s, CI across Python 3.9–3.12.

Repo: https://github.com/aazh2026/vlab
Live dashboard: https://postcodeengineering.com/vlab/

Standard disclaimer: all results are backtests on historical data. Past
performance does not predict future returns, and nothing here is investment
advice, an offer, or a recommendation. Investing involves risk — you are
solely responsible for your own decisions.

I am the author of this project.
```

---

## C) r/fintech

**Title**

`Backtesting infrastructure is where the real bugs live — I built a lab that audits its own assumptions`

**Body**

```markdown
Most backtest bugs are not in the strategy logic. They are in the
**assumptions the data layer makes silently**. I built
[vlab](https://github.com/aazh2026/vlab) specifically to audit those, and
the four bugs it surfaced are a decent catalogue of what goes wrong.

1. **Cross-market holiday mismatch.** US and Chinese markets close on
   different days. Unaligned calendars turn a missing quote into a zero
   position value: -90% drawdown, 1618% volatility.
2. **Yield-bearing instruments that don't look like they yield.** Money
   market ETFs hold a constant NAV of 100 and pay distributions as units, so
   the price series is flat. A "100% cash" portfolio showed 0% CAGR against a
   real 1.67%.
3. **Weight renormalisation.** If some assets aren't yet listed and you
   normalise weights to sum to 1, the unbuyable assets' weight spills onto
   the buyable ones. This manufactured a fake -30% year in 2008 that had
   nothing to do with the strategy.
4. **Look-ahead through the data window.** This one is the most dangerous
   because the code is correct. Backtesting from 2001 with ETFs that listed
   in 2014 means assets enter before they exist, which *understates* the
   drawdown. The fix isn't a bug fix, it's a methodology change: separate an
   "investable reality" window from an "index proxy" long window, and never
   quote them together.

And the one I gave myself while refactoring: extracting the rebalance
function and passing `cash` as a float meant `cash -= cost` mutated a local
copy. Buying never deducted money. The cash strategy reported **23.65% CAGR
against a true 1.8%**.

Design choices I'd argue for:

- **Regression tests as the product.** Each historical defect has a named
  test. That suite is the most valuable artifact in the repo, because
  without it the next person can reintroduce any of them silently.
- **Zero runtime dependencies.** Pure stdlib, so the dependency surface
  can't silently change your results.
- **Machine-checked artifacts.** A script verifies the published dashboard:
  both windows present, disclaimer present in all four required places, zero
  CDN references.
- **Report the negatives.** Gold banding adds ~0.3pp of CAGR. An MA200 trend
  overlay measurably does nothing. Both are in "known limitations", not
  quietly retained.

There's also a cash-vs-house module: mortgage amortisation, rent tax, vacancy,
management fees, buy/sell costs, break-even rent, and a price × rent × rate
sensitivity grid where a conclusion only counts if the whole grid has one
sign. It ingests no listing data — asking prices are not transaction prices.

Repo: https://github.com/aazh2026/vlab
Live dashboard: https://postcodeengineering.com/vlab/

Standard disclaimer: all results are backtests on historical data. Past
performance does not predict future returns, and nothing here is investment
advice, an offer, or a recommendation. Investing involves risk — you are
solely responsible for your own decisions.

I am the author of this project.
```

---

## D) Hacker News (Show HN)

**Title**

`Show HN: vlab – zero-dependency portfolio backtesting lab that audits its own assumptions`

**Body**

```markdown
I built a multi-asset allocation backtesting lab with **zero third-party
runtime dependencies** (Python standard library only) and a dashboard that is
a single self-contained HTML file with hand-drawn inline SVG — no CDN, opens
offline.

https://github.com/aazh2026/vlab
https://postcodeengineering.com/vlab/

The interesting part isn't the backtester. It's that I made the thing audit
its own assumptions, and the tests caught four bugs that each inverted the
conclusion:

| Bug | What it produced |
|---|---|
| Cross-market holidays not aligned (US vs China) | -90% drawdown, 1618% volatility |
| Money-market ETF yield evaporated (flat NAV, paid as units) | "all cash" showed 0% CAGR vs a real 1.67% |
| Weights over-normalised | a fake -30% year in 2008 |
| Look-ahead via the data window | backtested 2001 with ETFs that listed in 2014 |

The fourth one isn't a code bug — the code was correct and the conclusion was
still wrong. It lets assets that didn't exist yet enter early, understating
drawdown. The fix was methodological: separate an "investable reality"
window (starts when every tradable asset exists) from an "index proxy" long
window (indices stand in for pre-listing ETFs, covering 2008), and never
quote them together.

Then, while refactoring, I introduced a fifth bug myself. I extracted the
rebalance function and passed `cash` as a float, so `cash -= cost` mutated a
local copy and buying never deducted money. The cash strategy reported 23.65%
CAGR against a true 1.8%. A regression test caught it. Without that test I
would have shipped it as an improvement.

The result, honestly stated: this allocation's value is **drawdown control,
not return maximisation** — -9.96% max drawdown over an 18-year window
containing 2008, versus -52.89% for the CSI 300 ETF and -47.27% for the S&P
500, at a cost of 5.7 percentage points of annual return. Two of my own
additions turned out to be worthless (a gold-banding overlay adds ~0.3pp of
CAGR; an MA200 trend layer measurably does nothing) and are documented as
such rather than quietly kept.

93 regression tests, ~0.3s, CI on Python 3.9–3.12.

There's also a cash-vs-house module (mortgage amortisation, rent tax,
vacancy, break-even rent, price × rent × rate sensitivity grid). It ingests
no listing data — asking prices are not transaction prices, and loan terms
and taxes have to come from bank pre-approval and registered contracts.

All results are backtests on historical data. Past performance does not
predict future returns, and nothing here is investment advice, an offer, or
a recommendation.
```

---

## Posting notes

- **r/Python, r/fintech** — self-promotion is usually restricted to
  accounts with real karma/comment history. Spend a few days commenting
  normally first, or post from an account that already has standing.
- **r/algotrading** — allows self-promotion more readily, but the audience is
  technical and will check the code. The bug table is the hook.
- **Hacker News** — post during US Eastern morning hours (the front page
  window is roughly 5 minutes of attention). Expect tough questions about
  the data source and the survivorship/look-ahead handling; the README
  already answers them.
- **Do not** cross-post the same text to multiple subreddits on the same day
  — it reads as spam and gets flagged.
- Every post carries the disclaimer and states that I'm the author.
