"""Authentication and request hardening.

Demo mode uses a local username/password with a JWT session cookie. That is deliberately
modest, and the reason is worth stating: this platform holds **no money and no financial
credential**, so the thing authentication protects here is the control surface — who may
start, stop or halt a simulation — not an account balance.

What is nonetheless done properly, because getting it wrong is a habit:

* Passwords are hashed with PBKDF2-HMAC-SHA256 and a per-password salt. No plaintext
  comparison, no reversible encoding, and a constant-time digest comparison.
* The session token is a signed JWT in an `HttpOnly`, `SameSite=Strict` cookie, so a
  cross-site request cannot ride the session and page JavaScript cannot read the token.
* The signing secret is generated per process if none is configured, which means a
  restart invalidates sessions. That is the correct default: a hard-coded fallback secret
  is how a demo's "temporary" key ends up in production.
* Every mutating endpoint requires the session; read endpoints do too, so an unauthenticated
  scrape cannot enumerate the system's state.

**No financial credential is ever accepted, stored or transmitted by this module.** There
is no card field, no bank field, no broker key. The "capital" in this application is a
number in a simulation.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status

from tia.core.logging import get_logger

_log = get_logger("api.security")

SESSION_COOKIE = "tia_session"
ALGORITHM = "HS256"
SESSION_HOURS = 12
_PBKDF2_ROUNDS = 240_000


@dataclass(frozen=True)
class User:
    username: str
    role: str = "operator"

    @property
    def can_control_runtime(self) -> bool:
        return self.role in {"operator", "admin"}

    @property
    def can_change_settings(self) -> bool:
        return self.role in {"operator", "admin"}


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """PBKDF2-HMAC-SHA256. Returns ``salt$digest``, both hex."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison. A malformed stored value fails closed."""
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return hmac.compare_digest(candidate.hex(), digest_hex)


class AuthService:
    """Issues and validates session tokens for a small, fixed set of users."""

    def __init__(
        self,
        *,
        secret: str | None = None,
        users: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        # A per-process random secret when none is configured. Sessions do not survive a
        # restart, which is the right trade: a shared default secret would let anyone who
        # read the source mint a valid session.
        self._secret = secret or secrets.token_urlsafe(48)
        self._ephemeral_secret = secret is None
        self._users: dict[str, tuple[str, str]] = users or {}

    @property
    def uses_ephemeral_secret(self) -> bool:
        return self._ephemeral_secret

    def add_user(self, username: str, password: str, role: str = "operator") -> None:
        self._users[username] = (hash_password(password), role)

    def authenticate(self, username: str, password: str) -> User | None:
        record = self._users.get(username)
        if record is None:
            # Hash anyway, so a missing user and a wrong password take the same time and
            # the endpoint does not become a username oracle.
            verify_password(password, hash_password("dummy"))
            return None
        stored, role = record
        if not verify_password(password, stored):
            return None
        return User(username=username, role=role)

    def issue_token(self, user: User, *, now: datetime | None = None) -> str:
        moment = now or datetime.now(UTC)
        payload = {
            "sub": user.username,
            "role": user.role,
            "iat": int(moment.timestamp()),
            "exp": int((moment + timedelta(hours=SESSION_HOURS)).timestamp()),
            "jti": secrets.token_urlsafe(12),
        }
        return jwt.encode(payload, self._secret, algorithm=ALGORITHM)

    def read_token(self, token: str) -> User | None:
        try:
            payload: dict[str, Any] = jwt.decode(token, self._secret, algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            # Covers a wrong signature, a tampered payload, and the `alg: none` attack —
            # `algorithms=[ALGORITHM]` is what makes the last one impossible.
            return None
        username = payload.get("sub")
        if not isinstance(username, str):
            return None
        return User(username=username, role=str(payload.get("role", "viewer")))


def default_credentials() -> tuple[str, str, bool]:
    """The demo login.

    Read from the environment when set. When it is not, a password is **generated** and
    printed to the server log once, rather than defaulting to something guessable — a
    demo whose password is `admin/admin` is a demo that will be deployed with
    `admin/admin`.
    """
    username = os.environ.get("TIA_DEMO_USER", "operator")
    password = os.environ.get("TIA_DEMO_PASSWORD", "")
    generated = not password
    if generated:
        password = secrets.token_urlsafe(12)
    return (username, password, generated)


async def current_user(request: Request) -> User:
    """FastAPI dependency. Rejects anything without a valid session."""
    auth: AuthService | None = getattr(request.app.state, "auth", None)
    if auth is None:  # pragma: no cover - app always sets it
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "auth not configured")

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:]
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")

    user = auth.read_token(token)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired or invalid")
    return user


async def require_operator(user: User = Depends(current_user)) -> User:
    """For anything that changes system state."""
    if not user.can_control_runtime:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operator role required")
    return user


class RateLimiter:
    """A fixed-window limiter, per client, per route group.

    Deliberately in-process: this is one process serving one operator, and a Redis-backed
    limiter would add a dependency the demo is designed not to need. It is enough to stop
    a login endpoint being brute-forced by a script, which is what it is for.
    """

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, *, now: float) -> bool:
        cutoff = now - self._window
        hits = [t for t in self._hits.get(key, []) if t > cutoff]
        if len(hits) >= self._limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


def password_strength(password: str) -> dict[str, Any]:
    """A verdict on the operator password, computed once and never storing the value.

    Length is what matters against a rate-limited online guess; character classes are
    secondary. The thresholds are deliberately plain: under 12 characters is weak for a
    control surface reachable from the internet, whatever it contains.
    """
    length = len(password)
    classes = sum(
        1
        for test in (str.islower, str.isupper, str.isdigit)
        if any(test(ch) for ch in password)
    ) + (1 if any(not ch.isalnum() for ch in password) else 0)
    if length < 12 or password.lower() in {"password", "operator", "admin", "123456789012"}:
        verdict = "weak"
    elif length < 16 or classes < 2:
        verdict = "fair"
    else:
        verdict = "strong"
    return {"verdict": verdict, "length": length, "character_classes": classes}


SECURITY_HEADERS = {
    # No inline-script escape hatch beyond what the bundled app needs, no framing, no
    # referrer leakage. `connect-src 'self'` keeps the page from exfiltrating anything.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


__all__ = [
    "ALGORITHM",
    "SECURITY_HEADERS",
    "SESSION_COOKIE",
    "SESSION_HOURS",
    "AuthService",
    "RateLimiter",
    "User",
    "current_user",
    "default_credentials",
    "hash_password",
    "password_strength",
    "require_operator",
    "verify_password",
]
