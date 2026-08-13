"""The AI layer — advisory, expiring, and structurally incapable of creating risk.

Everything here feeds one field: ``ContextAssessment.context_modifier``, clamped to
``[-1, 0]``. There is no path from any object in this package to an order.
"""

from tia.llm.context import ContextOutcome, ContextRequest, ContextService, build_prompt
from tia.llm.governance import BreakerState, BudgetSnapshot, LLMGovernor, RefusalReason
from tia.llm.provider import (
    AnthropicProvider,
    LLMProvider,
    LLMResult,
    LLMUsage,
    MockLLMProvider,
    ScriptedLLMProvider,
    build_provider,
)
from tia.llm.schema import PROMPT_VERSION, ContextResponse, response_json_schema
from tia.llm.validation import ValidationFailure, ValidationResult, validate_response

__all__ = [
    "PROMPT_VERSION",
    "AnthropicProvider",
    "BreakerState",
    "BudgetSnapshot",
    "ContextOutcome",
    "ContextRequest",
    "ContextResponse",
    "ContextService",
    "LLMGovernor",
    "LLMProvider",
    "LLMResult",
    "LLMUsage",
    "MockLLMProvider",
    "RefusalReason",
    "ScriptedLLMProvider",
    "ValidationFailure",
    "ValidationResult",
    "build_prompt",
    "build_provider",
    "response_json_schema",
    "validate_response",
]
