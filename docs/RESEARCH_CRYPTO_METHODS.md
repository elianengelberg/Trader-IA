# What actually works in crypto trading — the evidence, and what this bot does with it

*Research pass of 2026-09-18. Every claim below is tied to a source; every source was read
for what it found, not for what its title promised. Where the evidence is weak, it says
so, and the bot does not act on it.*

The question asked was "the best method to trade cryptocurrencies". The honest answer is
that there is no single best method — there are a few **return sources with real
evidence behind them**, a longer list of effects that are real but too small to survive
costs, and a large body of methods that look profitable only because of how they were
tested. This document sorts them, and records what each one became in the code.

---

## 1. The verdicts, in one table

| Method | Evidence | Strength | What the bot does |
|---|---|---|---|
| Time-series momentum, 1–4 week horizons | Liu & Tsyvinski (RFS 2021); Liu, Tsyvinski & Wu (JF 2022); replications through 2026 incl. post-ETF | **Strong** — the one anomaly the literature agrees on | **Implemented** as the higher-timeframe tide: entries against an agreed 1w+4w trend are refused (`htf_mode=hard`) or halved (`soft`). |
| Cross-sectional momentum and size factors | Liu, Tsyvinski & Wu three-factor model (market, size, momentum) explains ten long-short characteristic strategies | Strong, but needs a basket of coins | **Not yet** — the session trades one symbol. Multi-symbol is the next structural step. |
| Volatility targeting | Bloomberg crypto insights (20% target: higher return, lower max drawdown, far less time underwater); adaptive trend paper (Sharpe 2.41, MDD -12.7% with vol targeting + trailing stops) | Strong for the *risk* profile; neutral for raw return | **Already implemented** — the risk budget scales size by `target_annual_volatility / realised` per profile; conviction sizing sits on top. |
| Fractional Kelly / evidence-scaled sizing | Practitioner literature: half-Kelly keeps ~75% of growth at ~half the drawdown; quarter-Kelly recommended for crypto because edge estimates are noisy | Sound arithmetic, universally endorsed | **Implemented** — conviction sizing scales the approved size by the edge's t-statistic; never above the risk engine's ceiling. |
| Trailing / break-even stops | Adaptive trend paper: dynamic trailing stop calibrated to volatility regimes is one of its three components | Moderate — improves the *distribution* (fewer full losses), not proven to raise expectancy in general | **Implemented and measured** — the Trade Journal's "By exit" table says what each stop kind is worth on this bot's own record. |
| Cash-and-carry / funding arbitrage | BIS WP 1087: carry averages >10%/yr, driven by retail leverage demand and scarce arbitrage capital; funding-arbitrage studies: 2–8% per six months on CEX, more on DEX with leverage; **high carry predicts crashes** | Real return stream; real venue, liquidation and settlement risk | **Measured, not traded** — the Carry card reads funding and basis, ranks today against a year of settlements, prices the net carry after fees, and repeats the BIS warning. Feeds the Advisor. |
| Funding rate as a positioning signal | Deeply negative funding has preceded squeezes; slight negative correlation between funding and forward returns | Weak — two or three episodes, not a rule | **Surfaced only** (stance: crowded long / short / balanced). Not a trading rule. |
| Intraday mean reversion (1–4 h) | Negative first-order autocorrelation at 1–4h; larger moves revert more; some strategies profitable after fees in-sample | Real but small; costs erode it over time ("not recommended in the long term") | **Not added as a rule.** The mean-reversion strategy already in the library covers it; the EV gate decides whether it clears costs. |
| Turn-of-the-candle effect | +0.58 bps/min at 15-minute boundaries since 2020 (Shanaev et al., Heliyon 2023), t > 9 | Real, tiny | **Rejected** — sub-basis-point per minute; the spread alone is larger. |
| Intraday / weekly seasonality | Best hours 22:00–23:00 UTC; weekend spreads double (0.012% → 0.028%) and volume falls 20–40%; post-ETF the weekend gap in returns is undetectable | Costs effect: strong. Return effect: fragile | **Costs handled** by the live-spread gate. **No return rule** — a 21:00→23:00 strategy is exactly the kind of pattern that dies out of sample. |
| Order-book imbalance | Robust predictor at seconds-to-minutes horizons across asset classes; linked to bitcoin crash risk | Strong at horizons this bot cannot execute on | **Partly** — the venue's top-of-book depth now prices impact; imbalance as a signal needs sub-second execution. |
| Machine learning forecasters | Most naive sign-based strategies fail at 10 bps of costs; profitability returns only with a cost-aware threshold (trade when forecast > cost); out-of-sample accuracy 52.9–54.1% | Weak as a direct signal; the *cost threshold* finding is the important one | **The bot's core rule already is the cost-aware threshold**: no entry without a measured edge that clears costs. No ML forecaster added. |
| Technical rules (MA crossovers etc.) | Rules profitable before Dec 2021 generally failed out of sample after data-snooping adjustment; White's Reality Check finds rare survivors | Weak | **Rejected as rules.** Strategies stay proposals; only measured evidence lets them trade. |
| Stop placement away from crowded levels | Practitioner: liquidation cascades trigger at clustered stops (round numbers, recent lows) | Anecdotal | **Not implemented** — no controlled evidence; noted for later. |

---

## 2. What the strongest evidence says, in detail

### 2.1 Time-series momentum at one to four weeks

Liu and Tsyvinski (*Risks and Returns of Cryptocurrency*, RFS 2021) find significant
time-series momentum at daily and weekly frequencies for bitcoin, ether and ripple: a
one-standard-deviation rise in today's bitcoin return predicts a 0.33% higher return
tomorrow, and the effect is strongest over one-to-four-week formation periods. Liu,
Tsyvinski and Wu (*Common Risk Factors in Cryptocurrency*, JF 2022) extend it to 1,827
coins: a long/short momentum strategy on one-to-four-week formation earns roughly 3%
excess weekly returns, and a three-factor model (market, size, momentum) absorbs ten
characteristic-sorted strategies. Independent replications (a 2018–2026 daily study with
monthly rebalancing: Sharpe 0.82 pre-ETF, 1.22 post-ETF; a 28-day lookback / 5-day hold
variant at Sharpe 1.51 vs 0.84 for the market) find it survives the spot-ETF era. The
weekly *reversal* some studies report turns out to live in small, illiquid coins only.

**What it means for a one-minute-bar bot:** the bot's signals live inside the hour; the
strongest documented force lives across weeks. Trading a one-minute short into a
four-week uptrend is fighting the only tide the evidence says exists. Hence the
higher-timeframe context: hourly bars, a one-week and a four-week return each expressed
in units of its own volatility, and a bias only when both agree beyond a threshold.

### 2.2 Carry, and why it is a warning as much as a yield

The BIS (Working Paper 1087, *Crypto carry*) measures the gap between crypto futures and
spot at above 10% a year on average — several times the carry of equities, bonds,
currencies or commodities. Interest-rate differentials explain almost none of it; what
does is the convenience yield of leverage: trend-chasing smaller investors paying for
upside exposure in booms, against too little arbitrage capital willing to take the other
side. Two findings follow that matter here: **high carry predicts future price
crashes**, and rises in carry track rises in the price of crash insurance.

Funding-rate arbitrage studies (Binance, Bitmex, ApolloX, Drift; 60 scenarios) report
six-month returns of roughly 2% (Bitmex) to 8% (Drift) unlevered, with drawdowns under 2%
in the best cases — and list how it fails: funding-spread compression, imperfect hedges,
execution frictions, forced liquidation, settlement and smart-contract disruption. One
2025 survey puts the carry strategy's Sharpe at 6.45 over 2020–2025, falling to 4.06 from
2024 and negative in 2025. A yield that averaged 8% with 0.8% volatility and then turned
negative is a yield whose risk is in the tail, not in the average.

### 2.3 Volatility targeting and sizing

Crypto volatility clusters and persists (GARCH-family and HAR models forecast it;
Realized-GARCH and component-GARCH do best), which is the precondition for volatility
targeting to work. Bloomberg's crypto research finds that targeting 20% annualised
volatility raised return by about 6% and cut maximum drawdown by 3% versus buy-and-hold,
with a large reduction in time underwater. The adaptive trend-following study (150+ pairs,
2022–2024, net of costs) combines vol targeting, a volatility-calibrated trailing stop
and a 70/30 long/short tilt to report Sharpe 2.41 and a maximum drawdown of -12.7%; read
it as "these components compose well", not as a forecast — it is one backtest.

On sizing, every serious treatment reaches the same place: full Kelly is fragile to
estimation error (overstating an edge by 10% doubles the bet), half-Kelly keeps about
three quarters of the growth at about half the drawdown, and quarter-Kelly is the sensible
setting where edges are as uncertain as they are in crypto. That is the shape of
conviction sizing here: full size only when the edge is several standard errors from zero.

### 2.4 The things that are real and still not worth trading

Intraday returns show both momentum and reversal depending on horizon; one-to-four-hour
returns are negatively autocorrelated; the turn of each 15-minute candle carries +0.58
bps per minute; 22:00–23:00 UTC has the highest average hourly return; weekends have
twice the spread and a fraction of the volume. All measured, all repeatable in sample.
None of them survives the arithmetic this bot lives by: a round trip at retail fees costs
15–20 bps with a maker entry, more without, and a signal worth a basis point or two is a
signal that pays the exchange.

### 2.5 Why most bots lose, and the discipline that follows

The public record of trading bots is filtered by survivorship — losers switch off
quietly, winners post screenshots. Backtests measure fit to the past, not the future;
strategies optimised on one period fail on the next, and rules that worked before
December 2021 generally did not after it once data-snooping is accounted for. The
practical consequences are already this system's rules: no trade without a measured edge
after costs; evidence only from closed trades; a decay guard that stops trading a bucket
whose recent trades disagree with its history; every strategy answerable for its own
record; and paper first, always.

---

## 3. How the findings became code

| Component | Module | Rule |
|---|---|---|
| Higher-timeframe tide | `tia.quant.trend_context`, `LiveRuntime._refresh_trend` | Hourly bars, refreshed hourly. Bias `up` when 1w and 4w z-scores both ≥ threshold, `down` when both ≤ −threshold, else `flat`. `hard`: refuse entries against it. `soft`: halve them. A feed that cannot serve hourly bars → context unavailable → no bias. |
| Carry monitor | `tia.data.funding`, `GET /api/funding` | Binance perpetual premium index + a year of funding settlements. Annualised funding, 7-day mean, percentile, stance, net carry after fees, verdict with the BIS warning. Read-only. |
| Volatility targeting | `tia.risk.budget` (`target_annual_volatility`) | Existing: size shrinks as realised volatility exceeds the profile's target. |
| Conviction sizing | `tia.economics.conviction` | Fraction of the approved size from the edge's t-statistic; pooled capped; exploration cheap; never above 1. |
| Exit discipline | `tia.execution.exits` | Break-even after 1R, trail at 2 ATR, tighter only; measured in the journal's "By exit" table. |
| Cost-aware threshold | `tia.economics.expected_value` | The gate every entry must clear: measured edge minus measured costs above a floor. |
| Evidence decay | `EdgeEstimator._with_recent` | The last sixty trades can cut an estimate; never raise it. |
| Strategy accountability | `tia.learning.scoreboard` | Thirty judged trades below zero beyond noise → muted. |
| Live spread | `LiveRuntime._refresh_quote` | Costs priced at the venue's spread; entries wait out a dislocated book. |

Everything in this table can only refuse, shrink or measure. Nothing in it invents an
edge, because nothing in the literature licenses one.

---

## 4. What would be next, and why it is not here yet

1. **A basket, not a symbol.** Cross-sectional momentum and the size factor need several
   coins; so does diversification, which is where volatility targeting earns most. This
   is a structural change to the session (one position per symbol, capital allocation
   across them) and deserves its own pass.
2. **Trading the carry.** The measured net carry could become a position — long spot,
   short perpetual — but that needs a futures execution provider, margin management, and
   a gate that reads the BIS crash warning. Measure first; the Carry card is that.
3. **Order-book imbalance as a signal.** Real, but at horizons that need a streaming
   book and sub-second execution, not a one-minute poll.

---

## 5. Sources

- Liu, Y., Tsyvinski, A. — *Risks and Returns of Cryptocurrency*, Review of Financial Studies 34(6), 2021. https://academic.oup.com/rfs/article-abstract/34/6/2689/5912024 · NBER w24877: https://www.nber.org/papers/w24877
- Liu, Y., Tsyvinski, A., Wu, X. — *Common Risk Factors in Cryptocurrency*, Journal of Finance 77(2), 2022. https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13119
- *Time-Series Momentum in Cryptocurrency Markets: A Pre and Post Spot Bitcoin ETF Analysis* (2026). https://zenodo.org/records/19671502
- *Time Series Momentum Trading Strategy for Cryptocurrencies* (2023). https://www.researchgate.net/publication/374536953
- Fičura, M. — *Impact of size and volume on cryptocurrency momentum and reversal*, FFA WP 2023. https://wp.ffu.vse.cz/pdfs/wps/2023/01/03.pdf
- Bank for International Settlements — *Crypto carry*, Working Paper 1087. https://www.bis.org/publ/work1087.htm · CEPR summary: https://cepr.org/voxeu/columns/crypto-carry-market-segmentation-and-price-distortions-digital-asset-markets
- *Exploring risk and return profiles of funding rate arbitrage on CEX and DEX* (2025). https://www.sciencedirect.com/science/article/pii/S2096720925000818
- *Cryptocurrency as an Investable Asset Class: Coming of Age* (arXiv 2510.14435) — carry Sharpe over 2020–2025. https://arxiv.org/pdf/2510.14435
- Ackerer, Hugonnier, Jermann — *Perpetual Futures Pricing*, Mathematical Finance 2026. https://onlinelibrary.wiley.com/doi/10.1111/mafi.70018
- Bloomberg Professional — *Crypto Insights: The Impact of Volatility Targeting*. https://assets.bbhub.io/professional/sites/10/Crypto-Insights-The-Impact-of-Volatility-Targeting.pdf
- *Systematic Trend-Following with Adaptive Portfolio Construction* (arXiv 2602.11708). https://arxiv.org/abs/2602.11708
- Wen, Bouri, Xu, Zhao — *Intraday return predictability in the cryptocurrency markets: Momentum, reversal, or both*, NAJEF 62, 2022. https://www.sciencedirect.com/science/article/abs/pii/S1062940822000833
- Shanaev, Vasenin, Stepanov — *Turn-of-the-candle effect in bitcoin returns*, Heliyon 2023. https://www.cell.com/heliyon/fulltext/S2405-8440(23)01443-3
- *Bitcoin's Weekend Effect: Returns, Volatility, and Volume (2014–2024)*. https://ojs.bbwpublisher.com/index.php/PBES/article/view/11691
- Quantpedia — *Are There Seasonal Intraday or Overnight Anomalies in Bitcoin?* https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/
- *Machine Learning-Based Bitcoin Trading Under Transaction Costs: Evidence From Walk-Forward Forecasting* (arXiv 2606.00060). https://arxiv.org/html/2606.00060v1
- *A novel approach to trading strategy parameter optimization, using double out-of-sample data and walk-forward techniques* (arXiv 2602.10785). https://arxiv.org/html/2602.10785
- *Nowcasting bitcoin's crash risk with order imbalance* (PMC). https://pmc.ncbi.nlm.nih.gov/articles/PMC10040314/
- *Explainable Patterns in Cryptocurrency Microstructure* (arXiv 2602.00776). https://arxiv.org/html/2602.00776v1
- *Predicting the Volatility of Cryptocurrencies' Returns Using High-Frequency Data* (MDPI 2026) and *Performance of the Realized-GARCH Model* (MDPI Risks 2023). https://www.mdpi.com/2227-7072/14/4/90 · https://www.mdpi.com/2227-9091/11/12/211
- Coriva — *Kelly Criterion and Position Sizing: From Formula to Quant Practice*. https://coriva.eu.org/en/kelly-criterion-position-sizing/
- Bitsgap — *Crypto Bot Backtesting 2026: What It Shows & Its Limits*; Coin Bureau — *Crypto Trading Bot Mistakes to Avoid*. https://bitsgap.com/blog/crypto-bot-backtesting-in-2026-what-it-shows-and-what-it-cannot-predict · https://coinbureau.com/guides/crypto-trading-bot-mistakes-to-avoid

*Access note: several publisher sites were unreachable from the build environment; where a
paper's full text could not be fetched, the figures quoted are those reported in its
abstract, publisher summary or a secondary summary, and are marked as such by their
precision.*
