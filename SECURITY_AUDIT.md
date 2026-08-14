# Security Audit

**Date:** 2026-08-14 · **Commit at audit:** 02a401e (plus uncommitted hardening work, committed immediately after)

Every finding below was produced by *executing* the stated command or test in this
environment, not by reading code. Where a category is covered by a named test, the
test is the durable form of the audit — it re-runs on every `make verify`.

## 1. Fund movement — the capability must not exist

| Search | Method | Result |
|---|---|---|
| Withdrawal/transfer endpoint paths in the package | `test_nothing_in_the_package_names_a_way_to_move_funds` (grep over every source file, **no allowance list**) | **NONE** |
| Withdrawal-shaped API routes | `test_no_withdrawal_endpoint` (walks the FastAPI route table) | **NONE** |
| Transfer/deposit/bank/card routes | `test_no_transfer_endpoint` | **NONE** |
| Fund-moving methods on the execution adapter | `test_the_adapter_has_no_method_that_moves_funds` (public surface scan) | **NONE** |
| Key permissions that allow fund movement | `check_permissions` refuses enableWithdrawals/InternalTransfer/UniversalTransfer, futures/margin, and **unrecognised flags whose names suggest movement**; unverified = refused | enforced at runtime |

Boundary suite: 18 tests walking every module, class and source file.

## 2. Secrets

- **Confinement:** only `binance_signing.py` (uses) and `core/config.py` (loads) may name a trading credential — `test_only_the_signing_module_carries_a_trading_credential_shape`. This check caught the API layer itself during this hardening (it briefly read the secret to build the signer); the fix moved extraction into the signing module rather than widening the allowance.
- **No secret in any HTTP response, error paths included:** `test_no_endpoint_leaks_the_venue_secret` scans whole bodies for the configured value across /api/live/gate, /api/settings, /api/health, /api/system/status and the arm failure path.
- **No secret via the browser:** `POST /api/live/arm` takes a confirmation phrase only; extra fields (a smuggled secret, a capital override) are ignored — `test_the_arm_request_has_no_field_for_a_secret_or_a_capital_amount`. The frontend has no credential input field and no signing header — `test_api_secret_never_frontend` (source AND built bundle).
- **Redacted by construction:** the secret lives in a wrapper whose repr/str/format print `***redacted***`; reading it requires `.reveal()`, greppable at every use site.
- **Logs:** key identified only by BLAKE2s fingerprint (`key:xxxxxxxx`).

## 3. Injection and transport

Re-verified green in this run (Part I table still applies): SQL injection via path/query
(8 payloads, no effect), path traversal (5 encodings, no host file), oversized body 413,
no traceback/path/driver in error bodies, CSP + X-Frame-Options + nosniff + Referrer-Policy
on every response. SSRF surface: the server makes outbound requests only to the configured
venue base URL; no endpoint accepts a URL to fetch.

## 4. Replay, duplicates, races

- Signed requests: HMAC over the exact sent bytes; `recvWindow` capped at 60 s (`test_the_receive_window_cannot_be_widened_without_limit`).
- Duplicate orders: deterministic `clientOrderId`; local mirror answers repeats (`test_duplicate_order_protection_is_venue_id_based`); venue-side rejection must be *demonstrated* on testnet before the gate passes (`order_idempotency` check).
- Timeout ambiguity: never retried blind — resolved against the venue by our own id first (`test_timeout_does_not_duplicate_order`); entries halt meanwhile.
- Webhook (disabled by default): HMAC + timestamp + replay window + IP allowlist; not on the execution path.
- Event redelivery: unique idempotency key at the database level.

## 5. AuthN / AuthZ

PBKDF2-HMAC-SHA256, per-password salt, constant-time compare; login is not a username
oracle; JWT in HttpOnly SameSite=Strict cookie; wrong-secret/tampered/alg:none/expired all
rejected; rate limits on login and API. Operator role required for: arm, stop, kill switch,
flatten, profile change, reset. The kill switch requires a *named* actor and no code path
connects the LLM layer to it.

## 6. Deserialization / command injection

- No pickle/eval/exec/yaml.load on any input path (checked by grep in this audit run).
- Subprocess use: two sites, fixed argv, no shell, local git metadata only.
- All inbound JSON goes through pydantic models with `extra="forbid"` on frozen configs; the venue-validation record is schema-validated with extra="forbid" and a content fingerprint, so a tampered file fails (`test_binance_validation_schema`).

## 7. Findings from this audit

1. **(fixed)** The API layer briefly touched the venue secret outside the signing module — caught by the boundary test during development, moved into `signer_from_live_config`.
2. **(fixed)** Decision-journal writes had been failing silently since the economics wiring (missing columns; logged-but-quiet). Found by the endurance harness, fixed with schema columns + migration guard (D12).
3. **(accepted, documented)** Fire-and-forget persistence can drop a row under a rare FK ordering race (1 fill row in ~2,100 endurance bars). By design persistence never blocks trading; the durable journal for reconciliation is the venue + event log, and the endurance coherence check watches the evidence store.
4. **(open, external)** Everything Binance-facing remains REQUIRES VALIDATION until `validate_binance.py` runs with egress; the gate enforces exactly this.
