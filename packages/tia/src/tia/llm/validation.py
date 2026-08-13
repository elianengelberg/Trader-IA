"""Business-rule validation of a model response.

Schema validation proves the response is *shaped* correctly. It does not prove the
response is *usable*. A well-formed object can still cite a source it was never shown,
describe a symbol nobody asked about, or arrive so late that the market it describes no
longer exists.

Each rule below exists because of a specific way a language model's output can be wrong
while being perfectly valid JSON. Rules are applied after schema validation and before the
response becomes a `ContextAssessment`.

**A failed rule never becomes a trade and never becomes an exception the caller must
handle.** It degrades to a neutral assessment: no influence, no veto, reason recorded. The
deterministic pipeline continues untouched. That is the §64 preference applied to the slow
loop — no context beats bad context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from tia.core.clock import ensure_utc
from tia.core.logging import get_logger
from tia.llm.schema import ContextResponse

_log = get_logger("llm.validation")

#: An assessment older than this at the moment of use is discarded outright, regardless of
#: its own TTL. Guards against a cached or replayed response outliving its market.
MAX_ASSESSMENT_AGE = timedelta(minutes=30)


class ValidationFailure(StrEnum):
    """Why a response was rejected. Counted, so a misbehaving model is visible."""

    UNATTRIBUTED_EVIDENCE = "unattributed_evidence"
    UNKNOWN_SYMBOL = "unknown_symbol"
    STALE_INPUT = "stale_input"
    CONTRADICTORY = "contradictory"
    EMPTY_THESIS = "empty_thesis"
    OVERLONG_EVIDENCE = "overlong_evidence"
    SUSPECTED_INJECTION = "suspected_injection"


@dataclass
class ValidationResult:
    """The outcome. ``ok`` is the only field a caller needs; the rest is for the record."""

    ok: bool
    failures: tuple[ValidationFailure, ...] = ()
    details: tuple[str, ...] = ()
    #: Rules that fired but only warrant a note — the response is still usable.
    warnings: tuple[str, ...] = field(default=())

    @property
    def reason(self) -> str:
        if self.ok:
            return ""
        return "; ".join(self.details) or ", ".join(f.value for f in self.failures)


#: Phrases that would only appear if something were trying to talk the system out of its
#: own rules. Their presence in a *model response* means the input contained an injection
#: attempt that the model echoed, so the response is discarded and the event recorded.
_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore the previous instructions",
    "disregard your instructions",
    "you are now",
    "override the risk",
    "bypass the risk engine",
    "execute this order",
    "place an order",
    "system prompt",
)


def validate_response(
    response: ContextResponse,
    *,
    symbol: str,
    known_symbols: frozenset[str],
    allowed_source_refs: frozenset[str],
    now: datetime,
    input_timestamps: tuple[datetime, ...] = (),
    max_input_age: timedelta = MAX_ASSESSMENT_AGE,
) -> ValidationResult:
    """Apply every business rule. Returns rather than raises.

    ``allowed_source_refs`` is the set of references the prompt actually contained. Any
    citation outside it is unattributable, which is the shape a hallucinated fact takes:
    confident, specific, and traceable to nothing.
    """
    failures: list[ValidationFailure] = []
    details: list[str] = []
    warnings: list[str] = []
    moment = ensure_utc(now)

    if symbol not in known_symbols:
        failures.append(ValidationFailure.UNKNOWN_SYMBOL)
        details.append(f"assessment concerns {symbol!r}, which is not in the universe")

    if not response.thesis.strip():
        failures.append(ValidationFailure.EMPTY_THESIS)
        details.append("an assessment with no stated reasoning cannot be audited")

    # Attribution. An empty allowed set means the prompt carried no citable references,
    # in which case citing anything at all is unattributable.
    cited = [
        item
        for item in (*response.supporting, *response.contradicting)
        if item.source_ref
    ]
    unknown_refs = sorted({i.source_ref for i in cited} - allowed_source_refs)
    if unknown_refs:
        failures.append(ValidationFailure.UNATTRIBUTED_EVIDENCE)
        details.append(
            f"cited {len(unknown_refs)} reference(s) not present in the input: "
            + ", ".join(unknown_refs[:4])
        )

    # Staleness of the *inputs*, not of the response. A perfectly fresh assessment built
    # from half-hour-old bars describes a market that has moved on.
    for stamp in input_timestamps:
        age = moment - ensure_utc(stamp)
        if age > max_input_age:
            failures.append(ValidationFailure.STALE_INPUT)
            details.append(
                f"input data was {age.total_seconds() / 60:.1f} minutes old, beyond the "
                f"{max_input_age.total_seconds() / 60:.0f}-minute limit"
            )
            break

    # Internal contradiction. A veto is a statement that trading is inadvisable; pairing
    # it with zero caution means the two fields disagree about the same judgement, and
    # there is no principled way to pick the one the model "meant".
    if response.veto and response.caution < 0.5:
        failures.append(ValidationFailure.CONTRADICTORY)
        details.append(
            f"veto set while caution is {response.caution:.2f}; the response contradicts "
            "itself about its own conclusion"
        )

    if response.confidence > 0.9 and not response.supporting and not response.contradicting:
        warnings.append(
            f"confidence {response.confidence:.2f} with no cited evidence; recorded but "
            "treated as unsupported"
        )

    haystack = " ".join(
        [response.thesis, *(i.claim for i in response.supporting),
         *(i.claim for i in response.contradicting)]
    ).lower()
    found = [marker for marker in _INJECTION_MARKERS if marker in haystack]
    if found:
        failures.append(ValidationFailure.SUSPECTED_INJECTION)
        details.append(
            "the response echoes instruction-override language, which means the input "
            f"contained an injection attempt: {found[0]!r}"
        )

    if failures:
        _log.warning(
            "llm_response_rejected",
            symbol=symbol,
            failures=[f.value for f in failures],
            detail="; ".join(details)[:500],
        )

    return ValidationResult(
        ok=not failures,
        failures=tuple(failures),
        details=tuple(details),
        warnings=tuple(warnings),
    )


__all__ = [
    "MAX_ASSESSMENT_AGE",
    "ValidationFailure",
    "ValidationResult",
    "validate_response",
]
