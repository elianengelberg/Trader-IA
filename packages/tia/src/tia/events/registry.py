"""Event type registry, serialization and schema evolution.

One place maps ``event_type`` → payload model, per ``schema_version``. Two consequences:

* An unknown or unparseable event is **quarantined**, never silently dropped. A dropped
  event is an invisible data-loss bug; a quarantined one shows up in a queue with a
  reason attached.
* Schema evolution is explicit. A breaking payload change requires a new version *and* a
  registered upcaster, so old persisted events stay readable forever.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from tia.core.errors import SchemaValidationError, UnknownEventTypeError
from tia.events import payloads as pl
from tia.events.envelope import EventEnvelope
from tia.events.payloads import EventType

Upcaster = Callable[[dict[str, Any]], dict[str, Any]]

_REGISTRY: dict[str, dict[int, type[BaseModel]]] = {}
_UPCASTERS: dict[tuple[str, int], Upcaster] = {}


def register(event_type: str, payload_cls: type[BaseModel], version: int = 1) -> None:
    _REGISTRY.setdefault(event_type, {})[version] = payload_cls


def register_upcaster(event_type: str, from_version: int, fn: Upcaster) -> None:
    """Register a transform from ``from_version`` to ``from_version + 1``."""
    _UPCASTERS[(event_type, from_version)] = fn


def payload_class(event_type: str, version: int = 1) -> type[BaseModel]:
    versions = _REGISTRY.get(event_type)
    if not versions:
        raise UnknownEventTypeError(f"unregistered event type {event_type!r}", event_type=event_type)
    cls = versions.get(version)
    if cls is None:
        raise UnknownEventTypeError(
            f"event type {event_type!r} has no schema version {version}",
            event_type=event_type,
            version=version,
            known_versions=sorted(versions),
        )
    return cls


def latest_version(event_type: str) -> int:
    versions = _REGISTRY.get(event_type)
    if not versions:
        raise UnknownEventTypeError(f"unregistered event type {event_type!r}", event_type=event_type)
    return max(versions)


def known_event_types() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def encode(envelope: EventEnvelope[Any]) -> dict[str, Any]:
    """Serialize to a JSON-compatible dict."""
    return envelope.model_dump(mode="json")


def decode(raw: dict[str, Any]) -> EventEnvelope[Any]:
    """Deserialize, applying upcasters until the payload is at the latest version.

    Raises :class:`SchemaValidationError` rather than returning ``None``: the caller is
    expected to quarantine, and a silent ``None`` invites an unchecked dereference.
    """
    event_type = raw.get("event_type")
    if not isinstance(event_type, str):
        raise SchemaValidationError("event is missing 'event_type'", raw_keys=sorted(raw))

    version = int(raw.get("schema_version", 1))
    target = latest_version(event_type)
    payload_data = dict(raw.get("payload") or {})

    while version < target:
        upcaster = _UPCASTERS.get((event_type, version))
        if upcaster is None:
            raise SchemaValidationError(
                f"no upcaster from v{version} to v{version + 1} for {event_type!r}",
                event_type=event_type,
                from_version=version,
            )
        payload_data = upcaster(payload_data)
        version += 1

    cls = payload_class(event_type, version)
    try:
        payload = cls.model_validate(payload_data)
        return EventEnvelope[Any].model_validate({**raw, "schema_version": version, "payload": payload})
    except ValidationError as exc:
        raise SchemaValidationError(
            f"payload failed validation for {event_type!r}",
            event_type=event_type,
            errors=exc.errors(include_url=False)[:5],
        ) from exc


def _register_defaults() -> None:
    mapping: dict[str, type[BaseModel]] = {
        EventType.TICK_RECEIVED: pl.TickReceived,
        EventType.QUOTE_RECEIVED: pl.QuoteReceived,
        EventType.CANDLE_CLOSED: pl.CandleClosed,
        EventType.REGIME_CHANGED: pl.RegimeChanged,
        EventType.VOLATILITY_CHANGED: pl.VolatilityChanged,
        EventType.DATA_QUALITY_EVALUATED: pl.DataQualityEvaluated,
        EventType.DATA_QUALITY_FAILURE: pl.DataQualityFailure,
        EventType.PROVIDER_DISCONNECTED: pl.ProviderDisconnected,
        EventType.PROVIDER_RECONNECTED: pl.ProviderReconnected,
        EventType.NEWS_RECEIVED: pl.NewsReceived,
        EventType.MACRO_EVENT_DETECTED: pl.MacroEventDetected,
        EventType.FEATURES_COMPUTED: pl.FeaturesComputed,
        EventType.CONTEXT_ASSESSED: pl.ContextAssessed,
        EventType.CONTEXT_UNAVAILABLE: pl.ContextUnavailable,
        EventType.SIGNAL_CANDIDATE_CREATED: pl.SignalCandidateCreated,
        EventType.SIGNAL_EXPIRED: pl.SignalExpired,
        EventType.RISK_DECISION_CREATED: pl.RiskDecisionCreated,
        EventType.ORDER_INTENT_CREATED: pl.OrderIntentCreated,
        EventType.ORDER_STATE_CHANGED: pl.OrderStateChanged,
        EventType.FILL_SIMULATED: pl.FillSimulated,
        EventType.POSITION_CHANGED: pl.PositionChanged,
        EventType.PORTFOLIO_UPDATED: pl.PortfolioUpdated,
        EventType.RECONCILIATION_COMPLETED: pl.ReconciliationCompleted,
        EventType.SAFE_MODE_ENTERED: pl.SafeModeEntered,
        EventType.SAFE_MODE_EXITED: pl.SafeModeExited,
        EventType.SYSTEM_FAILURE: pl.SystemFailure,
        EventType.HEARTBEAT: pl.Heartbeat,
    }
    for event_type, cls in mapping.items():
        register(event_type, cls, version=1)


_register_defaults()


__all__ = [
    "decode",
    "encode",
    "known_event_types",
    "latest_version",
    "payload_class",
    "register",
    "register_upcaster",
]
