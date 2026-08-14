"""Request signing for authenticated Binance endpoints.

This is the only module in the package that touches an API secret. That is not an accident
of layout — it is the point. "Which code can see the secret?" has a one-line answer, this
file is short enough to read in full, and the boundary test in
``tests/unit/test_scope_boundary.py`` fails if credential-shaped names appear anywhere
else.

Integration status: **REQUIRES VALIDATION**. The signing scheme below (HMAC over the
URL-encoded query string, with ``timestamp`` and ``recvWindow``, key passed in a header)
is Binance's documented scheme for signed endpoints. It could not be exercised in this
build environment — every Binance host is blocked by the egress proxy, including the
testnet — so no signature produced here has ever been accepted by the venue.
``scripts/validate_binance.py`` is the check; run it before trusting anything downstream.

Three rules this module enforces, each because the alternative has burned somebody:

**The secret never leaves.** :class:`BinanceCredentials` holds it in a
``SecretStr``-equivalent wrapper, its ``__repr__`` and ``__str__`` are redacted, and it is
excluded from every serialisation path. The value is read exactly once per signature, at
the point of computing the HMAC.

**The signature covers everything.** A partial signature — over some parameters but not
others — is worse than none, because it looks correct. The canonical string signed here is
the exact query string sent, byte for byte, and the two are built from the same object so
they cannot drift.

**Timestamps are ours, not the venue's.** ``timestamp`` comes from an injected
:class:`~tia.core.clock.Clock`, so a replayed session signs the same requests. A clock
skewed past ``recvWindow`` produces a rejection from the venue rather than a silent
mis-ordering, which is the failure mode to prefer.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from tia.core.clock import Clock

#: The venue rejects a signed request whose timestamp is older than this. Five seconds:
#: long enough to survive ordinary network jitter, short enough that a replayed request is
#: useless almost immediately.
DEFAULT_RECV_WINDOW_MS = 5_000

#: A ceiling on ``recvWindow``. Widening it to tolerate a broken clock trades a correct
#: rejection for an unbounded replay window, so the ceiling is here rather than in config.
MAX_RECV_WINDOW_MS = 60_000

_REDACTED = "***redacted***"


class _Secret:
    """A string that refuses to print itself.

    Not security through obscurity — the secret is in memory either way. It stops the
    ordinary accident: an exception with the request context attached, a debug log, a
    ``repr`` in a traceback frame. Those are how secrets actually leak.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """The only way to read it. Named so that every use site is greppable."""
        return self._value

    def __repr__(self) -> str:
        return f"_Secret({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __format__(self, spec: str) -> str:
        return _REDACTED


@dataclass(frozen=True)
class BinanceCredentials:
    """An API key pair, loaded from the environment and never from a request body.

    The frontend never sees these. There is no endpoint that accepts them, no field in any
    API schema that carries them, and no log line that prints them.
    """

    api_key: str
    _secret: _Secret

    @classmethod
    def from_values(cls, *, api_key: str, secret: str) -> BinanceCredentials:
        if not api_key.strip() or not secret.strip():
            raise ValueError(
                "both an API key and a secret are required. Configure them in the process "
                "environment (TIA_BINANCE_API_KEY / TIA_BINANCE_API_SECRET) or a secret "
                "manager — never in a config file that is committed, and never through the "
                "web interface."
            )
        return cls(api_key=api_key.strip(), _secret=_Secret(secret.strip()))

    @property
    def key_fingerprint(self) -> str:
        """A short, non-reversible identifier for logs and the UI.

        So that "which key is this?" is answerable without the key ever appearing anywhere.
        """
        return _fingerprint(self.api_key)

    def __repr__(self) -> str:
        return f"BinanceCredentials({self.key_fingerprint}, secret={_REDACTED})"


@dataclass(frozen=True)
class SignedRequest:
    """A request ready to send. Carries the key in a header, never in the query."""

    query_string: str
    headers: dict[str, str]

    def redacted(self) -> dict[str, Any]:
        """Safe to log: the signature and key are elided, the parameters are not."""
        without_signature = self.query_string.split("&signature=")[0]
        return {"query": without_signature, "headers": {"X-MBX-APIKEY": _REDACTED}}


class BinanceSigner:
    """Turns a parameter dict into a signed query string.

    Stateless apart from the credentials and the clock, so it is trivially testable: the
    same parameters and the same frozen clock produce the same signature every time, which
    is what lets ``scripts/validate_binance.py`` compare against a known vector.
    """

    def __init__(
        self,
        credentials: BinanceCredentials,
        clock: Clock,
        *,
        recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
    ) -> None:
        if recv_window_ms <= 0 or recv_window_ms > MAX_RECV_WINDOW_MS:
            raise ValueError(
                f"recv_window_ms must be between 1 and {MAX_RECV_WINDOW_MS}; a wider window "
                "extends how long a captured request stays replayable"
            )
        self._credentials = credentials
        self._clock = clock
        self._recv_window = recv_window_ms

    @property
    def key_fingerprint(self) -> str:
        return self._credentials.key_fingerprint

    def key_header(self) -> dict[str, str]:
        """The API-key header alone, for keyed-but-unsigned endpoints (listenKey).

        The *key* identifies; only the signature authorises. Endpoints that take the key
        without a signature can open a market-data stream and nothing else.
        """
        return {"X-MBX-APIKEY": self._credentials.api_key}

    def sign(self, params: dict[str, Any]) -> SignedRequest:
        """Sign ``params``, adding ``timestamp`` and ``recvWindow``.

        The signed string and the sent string are the same object, built once. A signature
        computed over a differently-ordered or differently-encoded rendering of the same
        parameters is the classic way this goes wrong, and it fails with an opaque venue
        error that sends people looking in the wrong place for a day.
        """
        payload = dict(params)
        payload["timestamp"] = self._clock.timestamp_ms()
        payload["recvWindow"] = self._recv_window

        canonical = urlencode(payload, doseq=True)
        digest = hmac.new(
            self._credentials._secret.reveal().encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return SignedRequest(
            query_string=f"{canonical}&signature={digest}",
            headers={"X-MBX-APIKEY": self._credentials.api_key},
        )


def _fingerprint(api_key: str) -> str:
    digest = hashlib.blake2s(api_key.encode("utf-8"), digest_size=4).hexdigest()
    return f"key:{digest}"


def signer_from_live_config(live: Any, clock: Clock) -> BinanceSigner:
    """Build a signer from the live configuration block.

    This function exists so that no module outside this file ever reads the secret — the
    boundary test flags any other file that so much as names a credential-shaped
    attribute, and it flagged the API layer the first time it tried. The credential's
    entire journey is: process environment → pydantic SecretStr → this function → HMAC.
    """
    if not live.has_credentials:
        raise ValueError(
            "no venue credentials configured; set TIA_LIVE__BINANCE_API_KEY and "
            "TIA_LIVE__BINANCE_API_SECRET in the process environment"
        )
    return BinanceSigner(
        BinanceCredentials.from_values(
            api_key=live.binance_api_key.get_secret_value(),
            secret=live.binance_api_secret.get_secret_value(),
        ),
        clock,
    )


def key_fingerprint_from_live_config(live: Any) -> str:
    """The configured key's one-way fingerprint, or "" when none is configured.

    Lives here for the same reason as :func:`signer_from_live_config`: the key never
    leaves this module, only its 4-byte blake2s identifier does. The activation gate
    uses it to check that the validation record was produced with the *same* key the
    deployment would trade with — a record made with one key must not vouch for another.
    """
    if not live.has_credentials:
        return ""
    return _fingerprint(live.binance_api_key.get_secret_value())


__all__ = [
    "DEFAULT_RECV_WINDOW_MS",
    "MAX_RECV_WINDOW_MS",
    "BinanceCredentials",
    "BinanceSigner",
    "SignedRequest",
    "key_fingerprint_from_live_config",
    "signer_from_live_config",
]
