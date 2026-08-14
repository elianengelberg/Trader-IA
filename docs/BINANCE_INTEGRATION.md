# Binance integration

**Status: REQUIRES VALIDATION.**

Not one request in this integration has ever been sent. The environment this code was
written in blocks every Binance host — `api.binance.com`, `api1.binance.com`,
`data-api.binance.vision`, `testnet.binance.vision`, and `developers.binance.com` all fail
to connect. Verified empirically, not assumed:

```
$ curl -s -o /dev/null -w "%{http_code}" https://api.binance.com/api/v3/ping
000
```

So every endpoint path, parameter name, response field and array position below was written
from documentation and **confirmed against nothing**. This document says so at the top
rather than in a footnote because the alternative — presenting unverified field names as if
they were facts — is exactly the failure mode that produces a system that looks like it
works and silently does the wrong thing.

`scripts/validate_binance.py` is what closes the gap. Run it before anything here is
trusted.

---

## 1. Files

| File | Role | Verified? |
|---|---|---|
| `data/providers/binance_public.py` | Public market data. No key, no signature. | No |
| `data/providers/binance_signing.py` | HMAC signing. The only module that touches a secret. | No |
| `data/providers/binance_live.py` | Spot execution. Requires an activation token. | No |
| `live/permissions.py` | What the key is allowed to do. | No |
| `scripts/validate_binance.py` | Turns all of the above into checked facts. | n/a |

---

## 2. Endpoints used

Every one is read-or-trade. The list is exhaustive, and there is nothing here that moves
funds off the exchange.

| Endpoint | Signed | Purpose |
|---|---|---|
| `GET /api/v3/ping` | no | Reachability |
| `GET /api/v3/time` | no | Clock skew |
| `GET /api/v3/klines` | no | Historical candles |
| `GET /api/v3/ticker/bookTicker` | no | Best bid/ask |
| `GET /api/v3/exchangeInfo` | no | Lot size, tick size, minimum notional |
| `POST /api/v3/order` | yes | Place an order |
| `DELETE /api/v3/order` | yes | Cancel an order |
| `GET /api/v3/order` | yes | Read one order |
| `GET /api/v3/openOrders` | yes | Read open orders |
| `GET /api/v3/account` | yes | Balances and fee tier |
| `GET /api/v3/myTrades` | yes | Executed trades |
| `GET /sapi/v1/account/apiRestrictions` | yes | Key permissions |

---

## 3. Assumptions that must be verified

Each of these is a specific claim that could be wrong, with the specific damage it would do.

### The kline array layout

Documented as:

```
[openTime, open, high, low, close, volume, closeTime, quoteAssetVolume, numberOfTrades, ...]
```

Every field is a **position**, not a name. A reordering would produce candles that parse
cleanly and are wrong — high and low swapped, or volume read as a trade count — and every
indicator downstream would be quietly computed on garbage. `_parse_kline` raises on a shape
mismatch rather than guessing, and the validation script checks that high and low actually
bracket open and close.

### The fee tier encoding

`makerCommission` and `takerCommission` from `/api/v3/account` are documented as basis
points. **This is the single most dangerous number in the integration.** If they are
actually tenths of a basis point, or if your account's real tier differs from the standard
one, every cost estimate downstream is wrong in the flattering direction — and a strategy
that loses money looks like one that makes it.

The activation gate refuses to arm while `fees_verified_at_source` is false, and the
validation script prints the number alongside an instruction to confirm it against the fee
page in the Binance UI. Do that. Do not skip it.

### Venue-side idempotency

Every order carries `newClientOrderId`, derived deterministically from the signal's content.
The assumption is that Binance **rejects** a second order with the same id. If it does not,
venue-side idempotency cannot be relied on, and a retry after a timeout could open a second
position.

`validate_binance.py --order --testnet` tests this specifically, by submitting the same id
twice and checking that the second is refused. It is the single most valuable thing that
script does.

### Order status values

The status → state map covers `NEW`, `PARTIALLY_FILLED`, `FILLED`, `CANCELED`,
`PENDING_CANCEL`, `REJECTED`, `EXPIRED`, `EXPIRED_IN_MATCH`. An unmapped status **raises**
rather than defaulting. Defaulting to `ACKNOWLEDGED` would mean the system believes an order
is live when the venue may have killed it.

### Exchange filters

`LOT_SIZE.stepSize`, `PRICE_FILTER.tickSize` and the minimum notional must be applied before
submitting. An order rounded to the wrong step is rejected with an unhelpful message that
sends people looking in the wrong place for an afternoon.

---

## 4. Signing

```
canonical  = urlencode(params + {timestamp, recvWindow})
signature  = HMAC_SHA256(secret, canonical)
sent       = canonical + "&signature=" + signature
header     = X-MBX-APIKEY: <api key>
```

Three properties, each because the alternative has burned somebody:

**The signed string and the sent string are the same object**, built once. A signature over
a differently-ordered or differently-encoded rendering of the same parameters fails with an
opaque venue error.

**`timestamp` comes from an injected clock**, not `datetime.now()`, so a replayed session
signs the same requests. Clock skew past `recvWindow` produces a rejection from the venue
rather than a silent mis-ordering — the failure mode to prefer, though the rejection does
not mention the clock, which is why the validation script checks skew explicitly.

**`recvWindow` is bounded at 60 seconds.** Widening it to tolerate a broken clock trades a
correct rejection for an unbounded replay window.

---

## 5. Failure handling

The distinction that matters is between *the venue said no* and *the venue did not answer*:

| Failure | Meaning | Response |
|---|---|---|
| HTTP 4xx with a code | Rejected. The order did not happen. | `OrderRejectedError` — safe to say it failed |
| HTTP 429 / 418 | Rate limited | `ProviderUnavailableError` — back off, do not retry immediately |
| HTTP 401 / 403 | Key refused | `LiveActivationError` naming the key, not the order |
| **Timeout** | **Unknown.** The venue may or may not have the order. | `ReconciliationError`. **No retry.** |
| Connection error | Transport failed before a response | `ProviderUnavailableError` |

The timeout row is the important one. Retrying after a timeout is how one signal becomes two
positions; assuming it failed is how a real position goes untracked. The only correct move
is to say the state is unknown, stop, and reconcile against the venue.

---

## 6. Running the validation

```bash
# Public data only. No key needed, touches nothing.
python scripts/validate_binance.py

# Add account checks: signing, fee tier, key permissions.
export TIA_BINANCE_API_KEY=...        # never as an argument — those land in shell history
export TIA_BINANCE_API_SECRET=...
python scripts/validate_binance.py --account

# Add an order round trip. Testnet only, and the restriction is not overridable.
python scripts/validate_binance.py --account --order --testnet

# Record what was confirmed, where the activation gate reads it.
python scripts/validate_binance.py --account \
  --json-out data/runtime/binance_validation.json
```

Exit code is 0 when every attempted check passed and 1 otherwise, so it can gate a deploy.

---

## 7. Known gaps

**No WebSocket streaming.** Market data is polled. For a strategy on 1-minute bars this is
adequate; for anything faster it is not, and the latency component of the cost model would
need to account for the polling interval as well.

**`myTrades` requires a symbol**, so `get_trades()` returns trades only for symbols this
adapter has orders for. A symbol traded by something else on the same account will not
appear — stated here rather than discovered during a reconciliation mismatch.

**Spot only.** No margin, no futures, no options. The risk engine's sizing assumes no
leverage and no liquidation, and the permission checker refuses a key that has those
enabled precisely so that assumption cannot be violated by accident.

**Position cost basis is not read from the venue.** `get_positions()` reports quantities
with `average_price=0.0`; cost basis comes from the fill journal, because the venue reports
balances rather than positions and has no notion of what you paid.
