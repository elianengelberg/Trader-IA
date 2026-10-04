# Evidence

Records produced by running Trader-IA against a real venue or a real host, kept here so
that a claim in the documentation can be traced to the run that produced it. A file in
this directory is immutable once committed: a later run adds a new file and the
documentation points at the newer one.

## What belongs here

| Producer | File name | What it holds |
|---|---|---|
| `scripts/validate_mm_testnet.py --json-out` | `mm_testnet_<UTC stamp>.json` | the verdict per item (PASS / FAIL / NOT TESTED) with its note, the commands issued, the venue's responses that were recorded (Testnet balances for USDT and BTC, exchange filters, the top of book, order states), every execution report received, the latency legs, the adapter's counters and the ledger snapshot |
| `scripts/validate_mm_live_service_testnet.py --json-out` | `mm_service_testnet_<UTC stamp>.json` | the live market-making **service** run against Testnet for a few minutes: initial and final reconciliation, the engine's counts and the reasons it did or did not quote, the adapter's counters, the kill switch, the account stream, samples every few seconds, the journal tail |
| `scripts/validate_binance.py --json-out` | `binance_validation_<UTC stamp>.json` | the fingerprinted validation record the activation gate reads (public data, account facts, permissions) |
| `scripts/mm_market_data_check.py` / `scripts/mm_replay_check.py` | `mm_market_data_<UTC stamp>.json` | the Phase 2 market-data run and its replay verification |

## What never belongs here

API keys, secrets, signatures, signed request parameters, session cookies or tokens. The
Testnet harness records none of them by construction: the subscription request is logged
by parameter *names* only, and the account rows it keeps are the two balances it quotes.
Before committing a file, grep it for the first characters of the key you used; if they
appear, do not commit it and report the leak as a defect of the script.

## How to add a run from the VPS

```
cd /home/tia/Trader-IA
cp "$HOME/tia-testnet/mm_testnet_<stamp>.json" docs/evidence/
git add docs/evidence/mm_testnet_<stamp>.json
git commit -m "Evidence: Binance Testnet validation <stamp>"
git push origin claude/algo-trading-simulation-platform-ngf7xo
```

Then reference the file from the section of the phase document that claims the result.

## Index

| Date (UTC) | File | Commit validated | Documented in |
|---|---|---|---|
| 2026-10-03 21:51 | `mm_testnet_20261003T215105Z.json` | `1ebc584` | `docs/MARKET_MAKING_PHASE4_LIVE_ARCHITECTURE.md` §10. Block validation; no fill by design |
| 2026-10-04 | `mm_service_testnet_20261003T235710Z.json` — **still on the VPS**, under the `$HOME/tia-testnet` its shell mounted as `/out` (a root shell: `/root/tia-testnet/`), not yet copied here | `8608db6` | `docs/MARKET_MAKING_PHASE4_LIVE_ARCHITECTURE.md` §10.5. Service run, 180 s: every item PASS except S8 NOT TESTED (no fill) and S10b FAIL (a ghost transient after the stop and the stop recorded as a sticky kill), root-caused as a state-model ambiguity and fixed in the following commit |
| 2026-10-04 | `mm_service_testnet_<stamp>.json` — **still on the VPS**, under the `$HOME/tia-testnet` its shell mounted as `/out` (a root shell: `/root/tia-testnet/`), not yet copied here | `8e058f7` | `docs/MARKET_MAKING_PHASE4_LIVE_ARCHITECTURE.md` §10.4. Service run, 3 min: every item PASS except S8 NOT TESTED (no fill) and S10 FAIL, whose root cause (a reconciliation false positive) is fixed in the following commit |
| 2026-10-03 22:41 | `mm_testnet_20261003T224159Z.json` | `9cac585` | `docs/MARKET_MAKING_PHASE4_LIVE_ARCHITECTURE.md` §10.1. Block validation plus `--fill-probe 300`: bid 8e-05 BTC @ 84792.00 at the best bid, no print in 300 s, fill items NOT TESTED |
