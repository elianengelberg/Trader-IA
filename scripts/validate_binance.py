#!/usr/bin/env python3
"""Validate every Binance assumption this repository makes — from a machine with egress.

**Why this script exists.** The Binance adapters in this repository were written from
documentation and never executed. Every Binance host is blocked in the environment they
were built in: ``api.binance.com``, ``api1.binance.com``, ``data-api.binance.vision``,
``testnet.binance.vision`` and ``developers.binance.com`` all fail to connect. So every
endpoint path, parameter name, response field and array position in
``tia/data/providers/binance_*.py`` is an *unverified claim*.

This script turns those claims into checked facts, or tells you exactly which one is wrong.
Run it before the activation gate is allowed to arm — two of the gate's checks
(``fees_verified_at_source`` and ``credentials_scoped``) are meant to be fed from its
output, and both fail closed until they are.

    # Public data only. No key needed, touches nothing.
    python scripts/validate_binance.py

    # Add account checks. Reads permissions and the real fee tier.
    export TIA_BINANCE_API_KEY=...          # never pass these as arguments:
    export TIA_BINANCE_API_SECRET=...       # arguments land in your shell history
    python scripts/validate_binance.py --account

    # Add a live order round trip. TESTNET ONLY, and it says so.
    python scripts/validate_binance.py --account --order --testnet

**What this script will not do.** It will not place an order against mainnet. ``--order``
requires ``--testnet``, and the check is here rather than in a comment because a validation
script that can spend money is a validation script nobody should run.

Exit code is 0 when every attempted check passed, 1 otherwise, so it can gate a deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "tia" / "src"))

import httpx

from tia.core.clock import SystemClock
from tia.data.providers.binance_signing import (
    BinanceCredentials,
    BinanceSigner,
)
from tia.live.permissions import check_permissions

#: Bumped when the envelope or the fact set changes. The gate refuses records from any
#: other version rather than reinterpreting them.
VALIDATOR_VERSION = 2

MAINNET = "https://api.binance.com"
TESTNET = "https://testnet.binance.vision"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


@dataclass
class Results:
    passed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    def ok(self, name: str, detail: str = "") -> None:
        self.passed.append(name)
        print(f"  {GREEN}PASS{RESET}  {name}" + (f"  {DIM}{detail}{RESET}" if detail else ""))

    def bad(self, name: str, detail: str) -> None:
        self.failed.append((name, detail))
        print(f"  {RED}FAIL{RESET}  {name}\n        {detail}")

    def skip(self, name: str, why: str) -> None:
        self.skipped.append((name, why))
        print(f"  {YELLOW}SKIP{RESET}  {name}  {DIM}{why}{RESET}")


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


# --------------------------------------------------------------------------- public


async def validate_public(client: httpx.AsyncClient, results: Results, symbol: str) -> None:
    """Confirm the shapes the market-data client depends on.

    The kline endpoint returns a bare array, so every field is a *position*. A reordering
    would produce candles that parse cleanly and are wrong — high and low swapped, or
    volume read as a trade count — which is the failure this section exists to catch.
    """
    section("Public market data")

    try:
        response = await client.get("/api/v3/ping")
        response.raise_for_status()
        results.ok("reachable", f"{client.base_url}")
    except httpx.HTTPError as exc:
        results.bad("reachable", f"cannot reach {client.base_url}: {exc}")
        return

    try:
        response = await client.get("/api/v3/time")
        server_ms = int(response.json()["serverTime"])
        local_ms = int(datetime.now(UTC).timestamp() * 1000)
        skew = abs(server_ms - local_ms)
        results.facts["clock_skew_ms"] = skew
        if skew < 1000:
            results.ok("clock skew", f"{skew} ms")
        else:
            results.bad(
                "clock skew",
                f"{skew} ms between this machine and the venue. Signed requests carry a "
                "timestamp and are rejected outside recvWindow (default 5000 ms). Fix NTP "
                "before trading — the rejection message does not mention the clock.",
            )
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        results.bad("clock skew", f"could not read server time: {exc}")

    try:
        response = await client.get(
            "/api/v3/klines", params={"symbol": symbol, "interval": "1m", "limit": 3}
        )
        rows = response.json()
        row = rows[0]
        if not isinstance(row, list) or len(row) < 9:
            results.bad("kline shape", f"expected an array of >=9 elements, got {row!r}")
        else:
            open_ms, o, h, low, c, volume = row[0], *map(float, row[1:6])
            plausible = low <= min(o, c) and h >= max(o, c) and volume >= 0
            if plausible and isinstance(open_ms, int):
                results.ok(
                    "kline shape",
                    f"[openTime, o={o}, h={h}, l={low}, c={c}, v={volume}] — positions confirmed",
                )
                results.facts["kline_columns"] = len(row)
            else:
                results.bad(
                    "kline shape",
                    f"positional layout looks wrong: high {h} / low {low} do not bracket "
                    f"open {o} and close {c}. The array order may have changed. Do not trust "
                    "the parser until this is resolved.",
                )
    except (httpx.HTTPError, IndexError, TypeError, ValueError) as exc:
        results.bad("kline shape", f"{exc}")

    try:
        response = await client.get("/api/v3/ticker/bookTicker", params={"symbol": symbol})
        data = response.json()
        missing = {"bidPrice", "askPrice", "bidQty", "askQty"} - set(data)
        if missing:
            results.bad("bookTicker fields", f"missing {sorted(missing)}")
        else:
            spread_bps = (
                (float(data["askPrice"]) - float(data["bidPrice"]))
                / float(data["askPrice"])
                * 10_000
            )
            results.facts["observed_spread_bps"] = round(spread_bps, 4)
            results.ok("bookTicker fields", f"live spread {spread_bps:.2f} bps")
    except (httpx.HTTPError, KeyError, ValueError, ZeroDivisionError) as exc:
        results.bad("bookTicker fields", f"{exc}")

    try:
        response = await client.get("/api/v3/exchangeInfo", params={"symbol": symbol})
        info = response.json()["symbols"][0]
        filters = {f["filterType"]: f for f in info.get("filters", [])}
        needed = {"LOT_SIZE", "PRICE_FILTER"}
        missing = needed - set(filters)
        if missing:
            results.bad(
                "exchange filters",
                f"missing {sorted(missing)} — an order rounded to the wrong step size is "
                "rejected by the venue with an unhelpful message",
            )
        else:
            step = filters["LOT_SIZE"]["stepSize"]
            tick = filters["PRICE_FILTER"]["tickSize"]
            notional = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
            min_notional = notional.get("minNotional", "unknown")
            results.facts["lot_step_size"] = step
            results.facts["price_tick_size"] = tick
            results.facts["min_notional"] = min_notional
            results.ok("exchange filters", f"step={step} tick={tick} minNotional={min_notional}")
            print(
                f"        {DIM}Round every quantity to {step} and every price to {tick} before "
                f"submitting, and refuse any order below {min_notional} quote.{RESET}"
            )
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        results.bad("exchange filters", f"{exc}")


# --------------------------------------------------------------------------- account


async def validate_account(
    client: httpx.AsyncClient, signer: BinanceSigner, results: Results
) -> None:
    """Confirm signing works, and read the two facts the activation gate needs."""
    section("Account (signed)")

    try:
        signed = signer.sign({})
        response = await client.get(
            f"/api/v3/account?{signed.query_string}", headers=signed.headers
        )
        if response.status_code >= 400:
            body = response.text[:300]
            results.bad(
                "signature accepted",
                f"HTTP {response.status_code}: {body}\n        A -1022 means the signature "
                "did not match; a -1021 means the clock is out of window; a -2015 means the "
                "key, its IP restriction or its permissions are wrong.",
            )
            return
        account = response.json()
        results.ok("signature accepted", "the HMAC scheme in binance_signing.py is correct")
    except httpx.HTTPError as exc:
        results.bad("signature accepted", f"{exc}")
        return

    maker = account.get("makerCommission")
    taker = account.get("takerCommission")
    if maker is None or taker is None:
        results.bad(
            "fee tier",
            "the account response did not carry makerCommission/takerCommission. The cost "
            "model cannot be verified from configuration, and the activation gate will "
            "keep refusing to arm.",
        )
    else:
        # Documented as basis points * 10 (i.e. 10 == 10 bps == 0.1%). REQUIRES CONFIRMATION
        # against your own account's fee page — this is the single number most likely to be
        # misread, and reading it 10x low makes every strategy look profitable.
        maker_bps, taker_bps = float(maker), float(taker)
        results.facts["maker_bps"] = maker_bps
        results.facts["taker_bps"] = taker_bps
        results.facts["round_trip_taker_bps"] = taker_bps * 2
        results.ok("fee tier", f"maker {maker_bps} bps, taker {taker_bps} bps")
        print(
            f"        {DIM}Round trip at taker on both legs: {taker_bps * 2:.1f} bps. "
            f"A strategy must produce more gross edge than this per trade, before spread "
            f"and slippage, simply to break even.{RESET}"
        )
        print(
            f"        {DIM}CONFIRM this against your account's fee page in the Binance UI "
            f"before trusting it. If these are tenths of a basis point rather than basis "
            f"points, every cost number downstream is 10x wrong in the flattering "
            f"direction.{RESET}"
        )

    section("API key permissions")
    try:
        signed = signer.sign({})
        response = await client.get(
            f"/sapi/v1/account/apiRestrictions?{signed.query_string}", headers=signed.headers
        )
        if response.status_code >= 400:
            results.bad(
                "permissions readable",
                f"HTTP {response.status_code}: {response.text[:200]}. Until permissions can "
                "be read from the venue, the system treats the key as potentially able to "
                "withdraw and refuses to trade.",
            )
            return
        restrictions = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        results.bad("permissions readable", f"{exc}")
        return

    section("User data stream")
    try:
        listen = await client.post(
            "/api/v3/userDataStream", headers=signer.key_header()
        )
        if listen.status_code < 400 and "listenKey" in listen.json():
            key = listen.json()["listenKey"]
            closed = await client.delete(
                f"/api/v3/userDataStream?listenKey={key}",
                headers=signer.key_header(),
            )
            results.facts["user_data_stream_ok"] = closed.status_code < 400
            if closed.status_code < 400:
                results.ok("user data stream", "listenKey opened and closed cleanly")
            else:
                results.bad(
                    "user data stream",
                    f"listenKey opened but close returned HTTP {closed.status_code}",
                )
        else:
            results.facts["user_data_stream_ok"] = False
            results.bad(
                "user data stream",
                f"HTTP {listen.status_code}: {listen.text[:200]} — without it, fills are "
                "discovered only by polling",
            )
    except httpx.HTTPError as exc:
        results.facts["user_data_stream_ok"] = False
        results.bad("user data stream", str(exc))

    report = check_permissions(restrictions, verified_at_source=True)
    results.facts["permissions"] = report.as_dict()
    if report.acceptable:
        results.ok("permissions scoped", "can trade, cannot move funds")
        if not report.ip_restricted:
            print(
                f"        {YELLOW}Recommended:{RESET} restrict this key to your server's IP. "
                "It is the cheapest reduction in blast radius available."
            )
    else:
        results.bad("permissions scoped", report.explain())


# --------------------------------------------------------------------------- order


async def validate_order(
    client: httpx.AsyncClient, signer: BinanceSigner, results: Results, symbol: str
) -> None:
    """Place, read back and cancel one small limit order on the **testnet**.

    A limit order priced far from the market, so it rests instead of filling. The point is
    to confirm the request and response shapes, not to trade.
    """
    section("Order round trip (testnet)")

    try:
        book = (
            await client.get("/api/v3/ticker/bookTicker", params={"symbol": symbol})
        ).json()
        far_below = float(book["bidPrice"]) * 0.5
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        results.bad("order round trip", f"could not read the book: {exc}")
        return

    client_order_id = f"tia-validate-{int(datetime.now(UTC).timestamp())}"
    params = {
        "symbol": symbol,
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.001",
        "price": f"{far_below:.2f}",
        "newClientOrderId": client_order_id,
        "newOrderRespType": "FULL",
    }

    try:
        signed = signer.sign(params)
        response = await client.post(
            f"/api/v3/order?{signed.query_string}", headers=signed.headers
        )
        if response.status_code >= 400:
            results.bad("submit", f"HTTP {response.status_code}: {response.text[:300]}")
            return
        payload = response.json()
        expected = {"symbol", "orderId", "clientOrderId", "status", "origQty", "executedQty"}
        missing = expected - set(payload)
        if missing:
            results.bad("submit response shape", f"missing {sorted(missing)}")
        else:
            results.facts["order_status_observed"] = payload["status"]
            results.ok("submit", f"status={payload['status']} orderId={payload['orderId']}")
    except (httpx.HTTPError, ValueError) as exc:
        results.bad("submit", f"{exc}")
        return

    # The property that matters most: the same client order id must be refused.
    try:
        signed = signer.sign(params)
        duplicate = await client.post(
            f"/api/v3/order?{signed.query_string}", headers=signed.headers
        )
        if duplicate.status_code >= 400:
            results.facts["duplicate_order_rejected"] = True
            results.ok(
                "duplicate rejected",
                "the venue refuses a repeated newClientOrderId — retries are safe",
            )
        else:
            results.facts["duplicate_order_rejected"] = False
            results.bad(
                "duplicate rejected",
                "the venue ACCEPTED a second order with the same newClientOrderId. "
                "Venue-side idempotency cannot be relied on; a retry after a timeout could "
                "open a second position. Do not go live until this is understood.",
            )
    except httpx.HTTPError as exc:
        results.bad("duplicate rejected", f"{exc}")

    try:
        signed = signer.sign({"symbol": symbol, "origClientOrderId": client_order_id})
        cancelled = await client.delete(
            f"/api/v3/order?{signed.query_string}", headers=signed.headers
        )
        if cancelled.status_code >= 400:
            results.bad(
                "cancel",
                f"HTTP {cancelled.status_code}: {cancelled.text[:200]} — an order was left "
                "resting on the testnet; cancel it manually.",
            )
        else:
            results.ok("cancel", f"status={cancelled.json().get('status')}")
    except (httpx.HTTPError, ValueError) as exc:
        results.bad("cancel", f"{exc}")


# --------------------------------------------------------------------------- main


async def run(args: argparse.Namespace) -> Results:
    base_url = TESTNET if args.testnet else MAINNET
    symbol = args.symbol.upper()

    print(f"Validating {base_url} for {symbol}")
    print(f"{DIM}Everything below is an assumption in this repository until it says PASS.{RESET}")

    results = Results()
    async with httpx.AsyncClient(base_url=base_url, timeout=20.0) as client:
        await validate_public(client, results, symbol)

        if args.account or args.order:
            api_key = os.environ.get("TIA_BINANCE_API_KEY", "")
            api_secret = os.environ.get("TIA_BINANCE_API_SECRET", "")
            if not api_key or not api_secret:
                results.skip(
                    "account checks",
                    "set TIA_BINANCE_API_KEY and TIA_BINANCE_API_SECRET in the environment",
                )
            else:
                signer = BinanceSigner(
                    BinanceCredentials.from_values(api_key=api_key, secret=api_secret),
                    SystemClock(),
                    recv_window_ms=args.recv_window,
                )
                print(f"{DIM}Using {signer.key_fingerprint}{RESET}")
                # A one-way, 4-byte identifier of the key that was validated — never the
                # key itself. Binds the record to a specific credential, so a validation
                # run with one key cannot vouch for an account armed with another.
                results.facts["api_key_fingerprint"] = signer.key_fingerprint
                await validate_account(client, signer, results)
                if args.order:
                    await validate_order(client, signer, results, symbol)

    return results


def report(results: Results, args: argparse.Namespace) -> int:
    """Print the summary and write the confirmed facts. Synchronous, so the file write
    is not doing blocking I/O inside the event loop."""
    section("Summary")
    print(
        f"  {len(results.passed)} passed, {len(results.failed)} failed, "
        f"{len(results.skipped)} skipped"
    )

    if results.facts:
        print(f"\n{DIM}Facts confirmed against the venue:{RESET}")
        print(json.dumps(results.facts, indent=2))
        if args.json_out:
            # The envelope the activation gate demands: version, provenance, and a
            # fingerprint over the facts, so a hand-edited record fails instead of
            # passing. Written only when every attempted check passed — a record of a
            # failed validation must never be able to satisfy the gate.
            if results.failed:
                print(
                    f"\n{YELLOW}Not writing {args.json_out}: validation had failures, "
                    f"and a failed validation is not evidence.{RESET}"
                )
            else:
                import hashlib
                import shutil
                import subprocess

                canonical = json.dumps(results.facts, sort_keys=True, default=str)
                try:
                    git = shutil.which("git") or "git"
                    commit = subprocess.run(  # noqa: S603 - fixed args, local metadata
                        [git, "rev-parse", "HEAD"], capture_output=True, text=True,
                        timeout=5, check=False,
                    ).stdout.strip()
                except Exception:
                    commit = ""
                envelope = {
                    "validator_version": VALIDATOR_VERSION,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "environment": "testnet" if args.testnet else "mainnet",
                    "symbol": args.symbol.upper(),
                    "git_commit": commit,
                    "fingerprint": hashlib.blake2s(
                        canonical.encode("utf-8"), digest_size=16
                    ).hexdigest(),
                    "facts": results.facts,
                }
                Path(args.json_out).write_text(
                    json.dumps(envelope, indent=2), encoding="utf-8"
                )
                print(f"\nWritten to {args.json_out}")

    if results.failed:
        print(
            f"\n{RED}Do not arm live trading.{RESET} Each failure above is an assumption in "
            "this repository that turned out to be wrong or unverifiable. Fix the adapter, "
            "or fix the account, then run this again."
        )
        return 1

    print(
        f"\n{GREEN}Every attempted check passed.{RESET} That makes the adapter's assumptions "
        "verified — it says nothing about whether any strategy is profitable."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate this repository's Binance assumptions against the real venue."
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="venue symbol (default BTCUSDT)")
    parser.add_argument("--testnet", action="store_true", help="use testnet.binance.vision")
    parser.add_argument(
        "--account", action="store_true", help="also check signing, fees and key permissions"
    )
    parser.add_argument(
        "--order",
        action="store_true",
        help="also place, duplicate and cancel one resting order (requires --testnet)",
    )
    parser.add_argument("--recv-window", type=int, default=5_000)
    parser.add_argument("--json-out", default="", help="write confirmed facts to this path")
    args = parser.parse_args()

    if args.order and not args.testnet:
        parser.error(
            "--order requires --testnet. This script does not place orders against an "
            "account with real money in it, and the restriction is not overridable."
        )

    return report(asyncio.run(run(args)), args)


if __name__ == "__main__":
    raise SystemExit(main())
