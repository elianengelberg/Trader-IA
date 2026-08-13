"""LLM providers.

Two implementations behind one interface:

* :class:`MockLLMProvider` — deterministic, offline, seeded. The **default**, and the one
  the demo uses. It needs no credential, makes no network call, and returns the same
  assessment for the same market state on every machine.
* :class:`AnthropicProvider` — the real Claude client, activated only when an API key is
  configured. Written against the Messages API with a forced tool call, which is how a
  structured response is obtained without parsing prose.

The mock is not a stub that returns a constant. It derives its caution from the same
market features Claude would be shown, so the pipeline downstream of it is exercised
with varying, plausible input — a mock that always returns ``caution=0`` would let a
broken fusion layer pass every test.

**No credential ever reaches a prompt.** The prompt builder receives market features and
nothing else; there is no code path from `Settings.anthropic_api_key` to prompt text, and
`tests/unit/test_llm_governance.py` asserts it.
"""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from tia.core.config import LLMConfig
from tia.core.errors import LLMSchemaError, LLMUnavailableError
from tia.core.ids import deterministic_id
from tia.core.logging import get_logger
from tia.core.rng import derive_seed
from tia.llm.schema import PROMPT_VERSION, ContextResponse, response_json_schema

_log = get_logger("llm.provider")

#: The tool the model is required to call. Forcing a tool call is what makes the response
#: structured; asking for "JSON only" in a prompt and parsing the reply is the approach
#: that fails on the first response wrapped in a code fence.
TOOL_NAME = "submit_context_assessment"


@dataclass
class LLMUsage:
    """What one call cost, for governance and the experiment record."""

    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    model: str = ""
    call_id: str = ""
    cached: bool = False

    def cost_usd(self, config: LLMConfig) -> float:
        return (
            self.input_tokens / 1_000_000 * config.input_cost_per_mtok_usd
            + self.output_tokens / 1_000_000 * config.output_cost_per_mtok_usd
        )


@dataclass
class LLMResult:
    """A validated response plus what it cost."""

    response: ContextResponse
    usage: LLMUsage
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Produce a validated :class:`ContextResponse` for a market state."""

    name: str = "abstract"

    @abstractmethod
    async def assess(self, prompt: str, *, call_id: str) -> LLMResult:
        """Return a validated response, or raise.

        Implementations must never return an unvalidated object: a caller that receives
        an :class:`LLMResult` is entitled to assume the schema held.
        """

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None

    @staticmethod
    def _validate(payload: Any, *, call_id: str) -> ContextResponse:
        """Schema-validate a raw payload.

        Every failure mode gets the same treatment — raise :class:`LLMSchemaError` with
        the offending payload attached — because "the model returned something odd" is a
        metric worth counting, not a log line worth skimming.
        """
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise LLMSchemaError(
                    "model response was not valid JSON",
                    call_id=call_id,
                    error=str(exc),
                    excerpt=payload[:400],
                ) from exc
        if not isinstance(payload, dict):
            raise LLMSchemaError(
                "model response was not a JSON object",
                call_id=call_id,
                received=type(payload).__name__,
            )
        try:
            return ContextResponse.model_validate(payload)
        except ValidationError as exc:
            raise LLMSchemaError(
                "model response violated the context schema",
                call_id=call_id,
                errors=[
                    {"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]}
                    for e in exc.errors()[:8]
                ],
            ) from exc


class MockLLMProvider(LLMProvider):
    """Offline, deterministic, and derived from the prompt's own content.

    Caution is computed from features the prompt carries, so the same market state always
    produces the same assessment — on any machine, in any process, without a network. That
    reproducibility is what lets the demo, the tests and a replay all agree.

    It is explicitly **not** a model of Claude's judgement. It is a stand-in that exercises
    the pipeline, and every assessment it produces says so in its thesis.
    """

    name = "mock"

    def __init__(self, *, seed: int = 20260812, fail_rate: float = 0.0) -> None:
        self._seed = seed
        self._fail_rate = fail_rate
        self.calls = 0

    async def assess(self, prompt: str, *, call_id: str) -> LLMResult:
        self.calls += 1

        # A deterministic pseudo-failure channel so the runtime's degradation path can be
        # exercised without waiting for a real outage.
        if self._fail_rate > 0:
            draw = (derive_seed(self._seed, f"fail:{call_id}") % 10_000) / 10_000
            if draw < self._fail_rate:
                raise LLMUnavailableError(
                    "mock provider simulated an outage", call_id=call_id
                )

        signals = _extract_numbers(prompt)
        caution = _derive_caution(signals)
        veto = caution >= 0.85
        leaning = _derive_leaning(signals)

        response = ContextResponse(
            caution=round(caution, 4),
            veto=veto,
            leaning=leaning,
            confidence=round(min(1.0, 0.35 + caution * 0.5), 4),
            regime_view=signals.get("regime_view", "unknown"),  # type: ignore[arg-type]
            thesis=(
                "Deterministic mock assessment — not a language model. Caution derived "
                f"from volatility percentile {signals.get('vol_percentile', 0.0):.2f}, "
                f"data quality {signals.get('data_quality', 1.0):.2f} and drawdown "
                f"{signals.get('drawdown_pct', 0.0):.2f}%. This text exists to exercise "
                "the pipeline and must never be read as market analysis."
            ),
            supporting=[],
            contradicting=[],
            invalidation_conditions=["mock assessment; superseded by any real provider"],
            relevant_events=[],
        )
        return LLMResult(
            response=response,
            usage=LLMUsage(
                input_tokens=len(prompt) // 4,
                output_tokens=120,
                latency_ms=0.0,
                model="mock",
                call_id=call_id,
            ),
            raw=response.model_dump(),
        )


class ScriptedLLMProvider(LLMProvider):
    """Returns pre-supplied payloads in order. For adversarial and failure tests.

    Each item is either a payload to validate (which may be deliberately malformed) or an
    exception to raise. This is how the schema validator, the business-rule validator and
    the circuit breaker are tested against inputs no real model would conveniently produce
    on demand.
    """

    name = "scripted"

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls = 0

    async def assess(self, prompt: str, *, call_id: str) -> LLMResult:
        del prompt
        if not self._script:
            raise LLMUnavailableError("scripted provider exhausted", call_id=call_id)
        item = self._script.pop(0)
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        response = self._validate(item, call_id=call_id)
        return LLMResult(
            response=response,
            usage=LLMUsage(input_tokens=10, output_tokens=10, model="scripted", call_id=call_id),
            raw=item if isinstance(item, dict) else {},
        )


class AnthropicProvider(LLMProvider):
    """The real Claude client.

    Uses a **forced tool call** rather than asking for JSON in the prompt: the tool's
    input schema is generated from :class:`ContextResponse`, so the schema the model is
    shown and the schema its reply is validated against cannot drift apart.

    Constructed only when an API key is present. The key is read from settings and handed
    to the SDK; it is never interpolated into a prompt, logged, or returned in a response.
    """

    name = "anthropic"

    def __init__(self, config: LLMConfig, api_key: str) -> None:
        if not api_key:
            raise LLMUnavailableError(
                "the Anthropic provider requires an API key; set TIA_ANTHROPIC_API_KEY "
                "or leave llm.provider='stub' to use the deterministic mock"
            )
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise LLMUnavailableError(
                "the 'anthropic' package is not installed; install tia[llm]"
            ) from exc

        self._config = config
        self._client = AsyncAnthropic(
            api_key=api_key,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    async def assess(self, prompt: str, *, call_id: str) -> LLMResult:
        import time

        from anthropic import APIError, APITimeoutError

        tool = {
            "name": TOOL_NAME,
            "description": (
                "Record a market-context assessment. This tool cannot place, size or "
                "modify an order; its only effect is to reduce or veto risk-taking."
            ),
            "input_schema": response_json_schema(),
        }

        started = time.perf_counter()
        try:
            message = await self._client.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                tools=[tool],
                tool_choice={"type": "tool", "name": TOOL_NAME},
            )
        except APITimeoutError as exc:
            raise LLMUnavailableError(
                "Claude request timed out", call_id=call_id, error=str(exc)
            ) from exc
        except APIError as exc:
            raise LLMUnavailableError(
                "Claude request failed", call_id=call_id, error=str(exc)
            ) from exc

        latency_ms = (time.perf_counter() - started) * 1000.0
        payload = _extract_tool_input(message, call_id=call_id)
        response = self._validate(payload, call_id=call_id)

        usage = getattr(message, "usage", None)
        return LLMResult(
            response=response,
            usage=LLMUsage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                latency_ms=latency_ms,
                model=self._config.model,
                call_id=call_id,
            ),
            raw=payload,
        )

    async def close(self) -> None:
        await self._client.close()


def _extract_tool_input(message: Any, *, call_id: str) -> dict[str, Any]:
    """Pull the tool input out of a Messages API response.

    A reply that contains only text — because the model declined the tool, or answered in
    prose — is a contract violation, not something to salvage by parsing the text. Parsing
    it is exactly the path by which free-form output would reach the decision pipeline.
    """
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", "") == TOOL_NAME:
            return dict(getattr(block, "input", {}) or {})
    raise LLMSchemaError(
        "the model returned no tool call; free-form text is never parsed as a decision",
        call_id=call_id,
        stop_reason=getattr(message, "stop_reason", None),
    )


SYSTEM_PROMPT = f"""\
You are the context layer of a simulation-only quantitative trading research platform.

Your role is strictly advisory and strictly one-directional. Deterministic strategies and
a deterministic risk engine make every decision about whether and how much to trade. Your
assessment can only ever *reduce* the size of a position or stop it entirely. There is no
field in your response that can create a trade, enlarge one, or override a risk limit, and
your reply is discarded entirely if it does not match the required schema.

Given that, the useful thing you can do is notice reasons for caution that a mechanical
rule would miss: a regime that looks unstable, evidence that contradicts the apparent
setup, data that looks wrong, an event whose consequences are not yet priced.

Rules:
- Call the `{TOOL_NAME}` tool. Do not answer in prose.
- `caution` is 0 when you see no reason for concern and 1 when trading looks inadvisable.
- Set `veto` only when you would decline to trade regardless of what the strategies say.
- Every claim in `supporting` or `contradicting` must cite a `source_ref` that appears in
  the input you were given. Do not cite anything you were not shown.
- If the input is insufficient to form a view, say so in `thesis` and return `caution: 0`.
  Low information is a reason to have no influence, not a reason to be alarmed.
- Never state or imply a prediction of returns.

Prompt contract version: {PROMPT_VERSION}
"""


# --------------------------------------------------------------------------- mock logic


def _extract_numbers(prompt: str) -> dict[str, Any]:
    """Read the machine-readable block the prompt builder embeds.

    The mock parses the same structured block the real model is shown, so both providers
    are driven by identical input and a difference in behaviour is a difference in
    judgement rather than in what they saw.
    """
    marker = "```json"
    if marker not in prompt:
        return {}
    try:
        body = prompt.split(marker, 1)[1].split("```", 1)[0]
        parsed = json.loads(body)
    except (IndexError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _derive_caution(signals: dict[str, Any]) -> float:
    """Map market state to a caution level.

    Monotone in each input and bounded in [0, 1]. Chosen so that the pipeline downstream
    sees a realistic spread of values rather than a constant, not because these weights
    represent any view about markets.
    """

    def number(key: str, default: float = 0.0) -> float:
        try:
            value = float(signals.get(key, default))
        except (TypeError, ValueError):
            return default
        return default if math.isnan(value) else value

    vol_percentile = min(1.0, max(0.0, number("vol_percentile")))
    data_quality = min(1.0, max(0.0, number("data_quality", 1.0)))
    drawdown = min(1.0, max(0.0, number("drawdown_pct") / 20.0))
    spread = min(1.0, max(0.0, number("spread_bps") / 50.0))
    regime_risk = 1.0 if signals.get("regime_view") in {"crisis", "high_volatility"} else 0.0

    caution = (
        0.35 * vol_percentile
        + 0.30 * (1.0 - data_quality)
        + 0.20 * drawdown
        + 0.10 * spread
        + 0.25 * regime_risk
    )
    return min(1.0, max(0.0, caution))


def _derive_leaning(signals: dict[str, Any]) -> str:
    try:
        trend = float(signals.get("trend_score", 0.0))
    except (TypeError, ValueError):
        return "neutral"
    if math.isnan(trend):
        return "neutral"
    if trend > 0.25:
        return "long"
    if trend < -0.25:
        return "short"
    return "neutral"


def build_provider(config: LLMConfig, *, api_key: str | None = None, seed: int = 20260812) -> LLMProvider:
    """Select a provider from configuration.

    Defaults to the mock. The real provider is only constructed when explicitly requested
    *and* a key is present — a missing key downgrades to the mock with a warning rather
    than crashing the runtime, because an unavailable context layer must never stop the
    deterministic pipeline.
    """
    if config.provider == "anthropic" and config.enabled:
        if not api_key:
            _log.warning(
                "llm_downgraded_to_mock",
                reason="anthropic provider requested but no API key is configured",
            )
            return MockLLMProvider(seed=seed)
        return AnthropicProvider(config, api_key)
    return MockLLMProvider(seed=seed)


def call_id_for(symbol: str, moment: Any) -> str:
    return deterministic_id("llm", symbol, moment)


__all__ = [
    "SYSTEM_PROMPT",
    "TOOL_NAME",
    "AnthropicProvider",
    "LLMProvider",
    "LLMResult",
    "LLMUsage",
    "MockLLMProvider",
    "ScriptedLLMProvider",
    "build_provider",
    "call_id_for",
]
