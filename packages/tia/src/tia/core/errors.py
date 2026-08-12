"""Error taxonomy for Trader-IA.

Every error carries a stable ``code`` so that failures can be counted, alerted on and
correlated without string matching. Errors are grouped by whether the system can keep
operating (``recoverable``) — the runtime uses that flag to decide between degrading a
component and entering safe mode.
"""

from __future__ import annotations

from typing import Any


class TiaError(Exception):
    """Base class for every error raised by this package."""

    code: str = "TIA_ERROR"
    recoverable: bool = False

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = context

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "context": self.context,
        }

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.context:
            return f"[{self.code}] {self.message} | {self.context}"
        return f"[{self.code}] {self.message}"


# --------------------------------------------------------------------------- config
class ConfigurationError(TiaError):
    code = "CONFIGURATION_ERROR"


class UnsupportedEnvironmentError(ConfigurationError):
    code = "UNSUPPORTED_ENVIRONMENT"


# --------------------------------------------------------------------------- contracts
class ContractError(TiaError):
    code = "CONTRACT_ERROR"


class SchemaValidationError(ContractError):
    code = "SCHEMA_VALIDATION_ERROR"
    recoverable = True


class UnknownEventTypeError(ContractError):
    code = "UNKNOWN_EVENT_TYPE"
    recoverable = True


class NaiveDatetimeError(ContractError):
    """A datetime crossed a boundary without timezone information.

    Treated as a hard error: silent local-time interpretation is the classic source of
    off-by-hours bugs in trading systems.
    """

    code = "NAIVE_DATETIME"


# --------------------------------------------------------------------------- data
class DataError(TiaError):
    code = "DATA_ERROR"
    recoverable = True


class DataQualityError(DataError):
    code = "DATA_QUALITY_ERROR"


class ProviderError(DataError):
    code = "PROVIDER_ERROR"


class ProviderUnavailableError(ProviderError):
    code = "PROVIDER_UNAVAILABLE"


class StaleDataError(DataError):
    code = "STALE_DATA"


# --------------------------------------------------------------------------- domain
class DomainError(TiaError):
    code = "DOMAIN_ERROR"


class InvalidStateTransitionError(DomainError):
    code = "INVALID_STATE_TRANSITION"


class InsufficientCapitalError(DomainError):
    code = "INSUFFICIENT_CAPITAL"
    recoverable = True


class UnknownInstrumentError(DomainError):
    code = "UNKNOWN_INSTRUMENT"
    recoverable = True


# --------------------------------------------------------------------------- risk
class RiskError(TiaError):
    code = "RISK_ERROR"


class RiskLimitImmutableError(RiskError):
    """Raised when anything attempts to mutate a risk limit at runtime.

    Risk limits are configuration. They change through a reviewed, versioned config
    change — never from inside the running process, and never from a model output.
    """

    code = "RISK_LIMIT_IMMUTABLE"


class KillSwitchEngagedError(RiskError):
    code = "KILL_SWITCH_ENGAGED"
    recoverable = True


# --------------------------------------------------------------------------- execution
class ExecutionError(TiaError):
    code = "EXECUTION_ERROR"
    recoverable = True


class OrderRejectedError(ExecutionError):
    code = "ORDER_REJECTED"


class DuplicateOrderError(ExecutionError):
    code = "DUPLICATE_ORDER"


class ReconciliationError(TiaError):
    code = "RECONCILIATION_ERROR"


class SafeModeError(TiaError):
    code = "SAFE_MODE"
    recoverable = True


# --------------------------------------------------------------------------- llm
class LLMError(TiaError):
    code = "LLM_ERROR"
    recoverable = True


class LLMUnavailableError(LLMError):
    code = "LLM_UNAVAILABLE"


class LLMSchemaError(LLMError):
    code = "LLM_SCHEMA_ERROR"


class LLMBudgetExceededError(LLMError):
    code = "LLM_BUDGET_EXCEEDED"


class SecretLeakDetectedError(TiaError):
    """A payload about to leave the process matched a secret pattern.

    Never recoverable: the call is aborted rather than redacted-and-sent, because a
    partial redaction that misses one pattern is worse than a failed request.
    """

    code = "SECRET_LEAK_DETECTED"


# --------------------------------------------------------------------------- backtest
class BacktestError(TiaError):
    code = "BACKTEST_ERROR"


class LookAheadBiasError(BacktestError):
    code = "LOOK_AHEAD_BIAS"


__all__ = [
    "BacktestError",
    "ConfigurationError",
    "ContractError",
    "DataError",
    "DataQualityError",
    "DomainError",
    "DuplicateOrderError",
    "ExecutionError",
    "InsufficientCapitalError",
    "InvalidStateTransitionError",
    "KillSwitchEngagedError",
    "LLMBudgetExceededError",
    "LLMError",
    "LLMSchemaError",
    "LLMUnavailableError",
    "LookAheadBiasError",
    "NaiveDatetimeError",
    "OrderRejectedError",
    "ProviderError",
    "ProviderUnavailableError",
    "ReconciliationError",
    "RiskError",
    "RiskLimitImmutableError",
    "SafeModeError",
    "SchemaValidationError",
    "SecretLeakDetectedError",
    "StaleDataError",
    "TiaError",
    "UnknownEventTypeError",
    "UnknownInstrumentError",
    "UnsupportedEnvironmentError",
]
