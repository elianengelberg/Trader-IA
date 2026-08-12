"""Structured logging.

JSON by default, with two properties that matter operationally:

1. **Correlation.** ``correlation_id`` is carried in a context variable and stamped onto
   every record, so one root stimulus (a closed candle) can be followed through features,
   strategy, LLM, risk, execution and P&L in a single query.
2. **Redaction.** A processor scrubs values that look like secrets before they reach a
   handler. Logs are the most common accidental exfiltration path; the guard is applied
   here rather than at each call site so it cannot be forgotten.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import structlog

_correlation_id: ContextVar[str | None] = ContextVar("tia_correlation_id", default=None)
_component: ContextVar[str | None] = ContextVar("tia_component", default=None)

# Keys whose values are replaced wholesale, regardless of content.
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "anthropic_api_key",
        "authorization",
        "jwt_secret",
        "password",
        "secret",
        "token",
        "webhook_secret",
        "x-api-key",
    }
)

# Value shapes that are secrets wherever they appear.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

REDACTED = "***REDACTED***"


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        out = value
        for pattern in _SECRET_PATTERNS:
            out = pattern.sub(REDACTED, out)
        return out
    if isinstance(value, dict):
        return {k: (REDACTED if k.lower() in _SENSITIVE_KEYS else _scrub_value(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(v) for v in value)
    return value


def redact_processor(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _scrub_value(event_dict[key])
    return event_dict


def context_processor(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    cid = _correlation_id.get()
    if cid is not None:
        event_dict.setdefault("correlation_id", cid)
    component = _component.get()
    if component is not None:
        event_dict.setdefault("component", component)
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Idempotently configure structlog and the stdlib root logger."""
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            context_processor,
            redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=level.upper(), force=True
    )


def get_logger(component: str) -> Any:
    """Return a bound logger tagged with ``component``."""
    return structlog.get_logger().bind(component=component)


def set_correlation_id(correlation_id: str | None) -> None:
    _correlation_id.set(correlation_id)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


@contextmanager
def correlation_scope(correlation_id: str) -> Iterator[str]:
    """Bind ``correlation_id`` for the duration of the block."""
    token = _correlation_id.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _correlation_id.reset(token)


@contextmanager
def component_scope(component: str) -> Iterator[str]:
    token = _component.set(component)
    try:
        yield component
    finally:
        _component.reset(token)


__all__ = [
    "REDACTED",
    "component_scope",
    "configure_logging",
    "correlation_scope",
    "get_correlation_id",
    "get_logger",
    "redact_processor",
    "set_correlation_id",
]
