"""The Advisor: grounded, read-only, and safe to expose.

Three properties matter. It answers from the system's own state, not the model's
imagination — so an answer must contain the facts it was given. It cannot act — there is no
path from a question to a trade, and the model, when used, is handed only a briefing. And it
never raises into a request: a model outage degrades to the deterministic briefing, it does
not 500.
"""

from __future__ import annotations

import pytest

from tia.core.clock import SystemClock
from tia.core.config import LLMConfig
from tia.core.errors import LLMUnavailableError
from tia.llm.advisor import AdvisorService, build_briefing
from tia.llm.governance import LLMGovernor
from tia.llm.provider import LLMProvider, LLMResult, LLMUsage, MockLLMProvider

CONTEXT = {
    "state": {
        "mode": "paper-live",
        "state": "running",
        "simulated": True,
        "capital": {"equity": 10_000.0, "total_pnl": -50.0, "return_pct": -0.5, "max_drawdown_pct": 2.0},
        "risk": {"mode": "normal", "new_trades_allowed": True, "trades_today": 3},
    },
    "positions": [
        {"symbol": "BTC-USD", "direction": "long", "quantity": 0.1,
         "average_price": 64000, "last_price": 64200, "unrealized_pnl": 20.0}
    ],
    "decisions": [
        {"decision_id": "d1", "symbol": "BTC-USD", "direction": "long", "verdict": "approve",
         "confidence": 0.72, "regime": "trending_up",
         "thesis": "Momentum with EMA cross and rising ADX.",
         "why_enter": ["EMA fast above slow", "ADX rising"], "why_not_enter": []}
    ],
    "learning": {"available": True, "reviews": 40, "win_rate": 0.45,
                 "mean_calibration_error_bps": -6.0, "active_guardrails": [],
                 "applies_guardrails": True, "guardrail_rejected": 2, "recent_lessons": []},
    "antipatterns": {"checks": [
        {"key": "cost_drag", "title": "Cost drag", "severity": "watch",
         "detail": "fees averaged 30% of the gross move", "principle": "costs decide outcomes"}
    ]},
}


def _governor(*, enabled: bool = False) -> LLMGovernor:
    return LLMGovernor(LLMConfig(enabled=enabled, provider="anthropic"), SystemClock())


class _Narrator(LLMProvider):
    """A provider that can converse — captures the prompt it was handed."""

    name = "fake-narrator"

    def __init__(self) -> None:
        self.seen_system = ""
        self.seen_user = ""

    @property
    def supports_narration(self) -> bool:
        return True

    async def assess(self, prompt: str, *, call_id: str) -> LLMResult:  # pragma: no cover
        raise NotImplementedError

    async def narrate(self, *, system: str, user: str, max_tokens: int = 1200):
        self.seen_system = system
        self.seen_user = user
        return "The system is long BTC on momentum.", LLMUsage(
            input_tokens=100, output_tokens=20, model="fake"
        )


class _BrokenNarrator(_Narrator):
    async def narrate(self, *, system: str, user: str, max_tokens: int = 1200):
        raise LLMUnavailableError("simulated outage")


# --------------------------------------------------------------------- briefing


def test_the_briefing_carries_the_decisions_stated_reasoning() -> None:
    briefing, grounded = build_briefing(CONTEXT)
    assert "Momentum with EMA cross" in briefing  # the thesis — "why it bought"
    assert "recent decisions" in grounded
    assert "BTC-USD long" in briefing
    assert "learning report" in grounded


def test_an_empty_session_briefing_says_so() -> None:
    briefing, grounded = build_briefing({})
    assert "No session is running" in briefing
    assert grounded == []


# --------------------------------------------------------------------- deterministic path


async def test_without_a_model_the_answer_is_the_grounded_briefing() -> None:
    advisor = AdvisorService(MockLLMProvider(), _governor(), LLMConfig())
    answer = await advisor.answer("what are you doing?", CONTEXT)
    assert answer.used_llm is False
    assert "Momentum with EMA cross" in answer.answer  # grounded, not invented
    assert "not configured" in answer.note
    assert "recent decisions" in answer.grounded_on


async def test_an_empty_question_is_handled_not_sent() -> None:
    advisor = AdvisorService(MockLLMProvider(), _governor(), LLMConfig())
    answer = await advisor.answer("   ", CONTEXT)
    assert answer.used_llm is False
    assert "Ask a question" in answer.answer


# --------------------------------------------------------------------- model path


async def test_with_a_model_it_answers_in_prose_grounded_only_in_the_briefing() -> None:
    narrator = _Narrator()
    advisor = AdvisorService(narrator, _governor(enabled=True), LLMConfig(enabled=True))
    answer = await advisor.answer("why are you long?", CONTEXT)

    assert answer.used_llm is True
    assert answer.answer == "The system is long BTC on momentum."
    # The model was handed the briefing and a system prompt that forbids it from acting.
    assert "Momentum with EMA cross" in narrator.seen_user
    assert "no ability to trade" in narrator.seen_system
    assert "why are you long?" in narrator.seen_user


async def test_a_model_outage_degrades_to_the_briefing_and_never_raises() -> None:
    advisor = AdvisorService(_BrokenNarrator(), _governor(enabled=True), LLMConfig(enabled=True))
    answer = await advisor.answer("what are you doing?", CONTEXT)
    assert answer.used_llm is False
    assert "Momentum with EMA cross" in answer.answer  # fell back to the grounded briefing


async def test_the_briefing_never_carries_a_secret_shaped_field() -> None:
    """The context is assembled from state dicts that hold no credentials; assert the
    Advisor's own output cannot surface one even if a key-like string sneaks into state."""
    poisoned = dict(CONTEXT)
    poisoned["state"] = {**CONTEXT["state"], "api_key": "SECRET-SHOULD-NEVER-APPEAR"}
    briefing, _ = build_briefing(poisoned)
    # build_briefing only reads known fields, so an unexpected 'api_key' is never emitted.
    assert "SECRET-SHOULD-NEVER-APPEAR" not in briefing


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
