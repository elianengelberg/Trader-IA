# Security

The threat model here is unusual in one respect: the worst outcome is not a data breach. It
is an API key with withdrawal permission ending up somewhere it should not be. A losing
trade costs a fraction of the account. A compromised withdrawal key costs all of it,
instantly and irreversibly, with no recourse.

Everything below is ordered by that.

---

## 1. Custody: there is none

This platform never holds, receives, or stores money.

There is no wallet, no account it controls, no address it can pay into, and no balance it
owns. Your funds are at Binance, in your account, at all times. The system reads that
balance and places orders against it; that is the entire relationship.

This is not a policy that could be relaxed by a configuration change. There is no code that
would implement custody if it were switched on.

---

## 2. Fund movement: three independent barriers

**No code path.** `tests/unit/test_scope_boundary.py` greps every source file in the
package for withdrawal and transfer endpoint paths and fails the build on any match. The
list has **no allowance entries** and is not getting any — unlike the order-endpoint and
credential checks, which do have narrow, named exemptions for the files whose job requires
them. A path string is one edit away from a request, and the edit that adds one should have
to delete a test first.

**No permission.** `tia/live/permissions.py` reads the key's actual permissions from Binance
and refuses if any of these are enabled:

```
enableWithdrawals        enableInternalTransfer     permitsUniversalTransfer
enableFutures            enableMargin               enableVanillaOptions
```

The last three are refused because this system models spot positions only and its sizing
assumes no leverage and no liquidation.

**No unknown permission.** Venues add permissions. A checker that enumerates only the flags
it knows about will silently approve a flag invented after it was written — and the flag
most likely to be invented is another way to move money. So an *unrecognised* flag that is
enabled and whose name matches a fund-movement shape (`withdraw`, `transfer`, `payout`,
`remit`, `send`, `redeem`, `convert`, `borrow`, `repay`, `loan`, `lend`) is treated as
forbidden. False positives cost someone a message and a list entry. A false negative costs
the account.

**Unverified is not permitted.** If permissions have never been read from the venue, the
system treats the key as potentially able to withdraw and refuses to trade. Not having
asked is not the same as having asked and been told no.

---

## 3. Secrets

### Where they live

| | |
|---|---|
| **Yes** | Process environment (`.env`, gitignored) or a secret manager |
| **No** | The frontend bundle |
| **No** | The database |
| **No** | Redis |
| **No** | Logs |
| **No** | API responses, including error bodies |
| **No** | Git, including `.env.example` |
| **No** | A chat message to anyone, including an AI assistant |

### How they are handled in code

**One module touches the secret.** `tia/data/providers/binance_signing.py` is the only file
permitted to name a trading credential, alongside `core/config.py`, which loads it. The
boundary test enforces exactly those two and fails on a third. "Which code can see the
secret?" has a one-line answer, and both files are short enough to read in full.

**The secret refuses to print itself.** It is held in a wrapper whose `__repr__`,
`__str__` and `__format__` all return `***redacted***`. This does not make it secret — it
is in memory either way — it stops the ordinary accident: an exception with request context
attached, a debug log, a `repr` in a traceback frame. Those are how secrets actually leak.
Reading the value requires calling `.reveal()`, which is named that way so every use site
is greppable.

**Keys are identified by fingerprint.** `key:a1b2c3d4`, a truncated BLAKE2s digest, so
"which key is this?" is answerable in logs and in the UI without the key appearing.

**Redaction is tested by scanning, not by field.** The security tests search entire
response bodies for the configured secret value, including on error paths — because
redaction is usually forgotten exactly there, where nobody looks until something is already
going wrong. Asserting on the fields someone remembered to redact misses the one they added
last week.

**No endpoint accepts a credential.** `POST /api/live/arm` takes a confirmation phrase and
nothing else — no key, no secret, no capital amount. A secret sent through a browser passes
through a request log, a proxy, and the page's memory on the way. And accepting a capital
amount over HTTP would let whoever can reach the endpoint choose how much is at risk.

---

## 4. What the AI layer may and may not do

The language model is advisory and is never on the critical path of a decision.

**The asymmetry rule.** Model output is clamped to `[-1, 0]`, so `final_confidence <=
base_confidence` **always**. The model can remove conviction; it can never add any. This is
structural, not a guideline — the clamp is in the type.

**Claude may never:**

- modify the risk engine or any of its limits
- raise `MAX_LIVE_CAPITAL`
- change loss limits
- access an API secret
- place an order
- withdraw or transfer funds
- change Binance permissions

**No financial secret ever enters a prompt.** No key, no secret, no account number, no
balance that could identify an account.

**A model timeout produces a neutral assessment, not a delay.** The fast loop does not wait
on the slow loop. A model having a bad minute cannot stall the deterministic pipeline and
cannot change what it decides beyond removing risk.

---

## 5. Application security

**Sessions.** JWT in an `HttpOnly`, `SameSite=Strict` cookie; `Secure` when served over
HTTPS. No token is ever readable by JavaScript, so an XSS that gets script execution still
does not get the session.

**Passwords.** PBKDF2-HMAC-SHA256 with a per-password salt. The demo password is
*generated* and printed once to the server log rather than defaulting to something
guessable — a demo whose password is `admin/admin` is a demo that will be deployed with
`admin/admin`.

**The login endpoint is not a username oracle.** A missing user and a wrong password return
the same message and take the same time, because the missing-user path hashes a dummy
anyway.

**Rate limiting.** Eight login attempts per five minutes per client; 600 API requests per
minute.

**One origin.** The frontend is served statically by the same FastAPI process, so there is
no CORS surface at all in the default deployment.

**Request signing.** HMAC-SHA256 over the exact query string that is sent, byte for byte,
built from the same object so the signed string and the sent string cannot drift.
`recvWindow` is bounded at 60 seconds and cannot be widened past it — widening it to
tolerate a broken clock trades a correct rejection for an unbounded replay window.

---

## 6. Operational rules

**Never share the API secret with anyone**, including an AI assistant, including in a
screenshot, including "just to debug something". If it is exposed, delete the key in Binance
immediately and create a new one. That is the whole remedy and it takes thirty seconds; it
is always cheaper than deciding whether the exposure mattered.

**Restrict the key to your server's IP.** The single cheapest reduction in blast radius
available.

**Never enable withdrawals on the key**, even temporarily, even "just to test". The system
will refuse to trade with it, and that refusal is the feature.

**Rotate keys periodically**, and immediately if a machine that held one is decommissioned,
sold, or compromised.

**Set `TIA_SECURITY__JWT_SECRET`.** The default in `config.py` is a placeholder and the
activation gate refuses to arm while it is still in place.

---

## 7. Reporting a vulnerability

If you find a way to make this system move funds, leak a secret, or trade without a valid
activation token, that is the interesting class of bug. Open an issue describing the
reproduction — without including any real credential in it.
