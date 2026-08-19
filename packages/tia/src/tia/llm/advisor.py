"""The Advisor — a read-only window into what the system is doing, and why.

The user wanted to *ask the AI* what it is up to: why it took a trade, on what grounds, how
it is thinking. This is that, built with one hard rule that makes it safe to expose: the
Advisor **cannot act**. It reads the system's own state and explains it. There is no code
path from a question to an order, a risk change, or a live activation — the endpoint that
serves it calls no mutating method, and the model, when one is used, is offered no tools.

It answers in two ways, and the difference is deliberate:

* **Grounded, always.** Every answer is built from a *briefing* assembled here out of the
  system's real state — positions, recent decisions and their stated theses, the learning
  report, the economics, the anti-pattern audit. The facts come from the system, never from
  the model's imagination.
* **Conversational when it can be.** If a real model is configured, it is asked to answer
  the question *using only that briefing*, and told to say "I don't have that" rather than
  invent. If no model is configured, the briefing itself is returned, plainly labelled — so
  the Advisor is useful offline and never fabricates.

No secret is reachable from here: the briefing is assembled from state dictionaries that
carry no keys, and the model, if called, is shown only the briefing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tia.core.config import LLMConfig
from tia.core.errors import LLMError
from tia.core.logging import get_logger
from tia.llm.governance import LLMGovernor
from tia.llm.provider import LLMProvider

_log = get_logger("llm.advisor")

ADVISOR_SYSTEM = """\
You are the read-only analyst of a simulation-only quantitative trading platform. You
explain what the system is doing and why. You have no ability to trade, size a position,
change a risk setting, or turn anything on — and you must never imply that you do.

Answer ONLY from the SYSTEM BRIEFING you are given below the question. If the briefing does
not contain what is needed to answer, say so plainly — do not invent numbers, trades, or
reasons. Never state or imply a prediction of future returns, and never give the user a
buy/sell instruction. When you explain a decision, explain the system's *stated* reasoning
from the briefing; you are reporting its thinking, not substituting your own.

Be concrete and brief. Prefer the system's real figures over adjectives.
"""


@dataclass(frozen=True)
class AdvisorAnswer:
    question: str
    answer: str
    #: Which parts of the system state the briefing drew on — shown so the user can see the
    #: answer is grounded, not conjured.
    grounded_on: list[str] = field(default_factory=list)
    used_llm: bool = False
    model: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "grounded_on": self.grounded_on,
            "used_llm": self.used_llm,
            "model": self.model,
            "note": self.note,
        }


class AdvisorService:
    """Answers questions about the running system, grounded in its own state."""

    def __init__(self, provider: LLMProvider, governor: LLMGovernor, config: LLMConfig) -> None:
        self._provider = provider
        self._governor = governor
        self._config = config

    async def answer(self, question: str, context: dict[str, Any]) -> AdvisorAnswer:
        question = (question or "").strip()
        if not question:
            return AdvisorAnswer(
                question="",
                answer="Ask a question — for example, \"why are you not trading right now?\" "
                "or \"what have you learned this session?\"",
                note="empty question",
            )

        briefing, grounded_on = build_briefing(context)
        if self._provider.supports_narration:
            allowed, reason = self._governor.may_call()
            if allowed:
                user = (
                    f"QUESTION:\n{question}\n\n"
                    f"SYSTEM BRIEFING (the only facts you may use):\n{briefing}"
                )
                try:
                    text, usage = await self._provider.narrate(
                        system=ADVISOR_SYSTEM, user=user, max_tokens=1200
                    )
                    self._governor.record_success(usage)
                    return AdvisorAnswer(
                        question=question,
                        answer=text,
                        grounded_on=grounded_on,
                        used_llm=True,
                        model=usage.model,
                    )
                except LLMError as exc:
                    self._governor.record_failure(error=str(exc))
                    _log.warning("advisor_llm_failed", error=str(exc)[:200])
                    # fall through to the deterministic briefing
                except Exception as exc:  # never let the Advisor raise into the request
                    self._governor.record_failure(error=str(exc))
                    _log.exception("advisor_llm_raised")
            else:
                return self._deterministic(
                    question, briefing, grounded_on,
                    note=f"the language model is rate/budget limited right now ({reason.value}); "
                    "showing the raw system briefing instead",
                )

        return self._deterministic(
            question, briefing, grounded_on,
            note="conversational AI is not configured — this is the raw system briefing the "
            "AI would reason over. Set an Anthropic API key on the server to get answers in "
            "prose.",
        )

    def _deterministic(
        self, question: str, briefing: str, grounded_on: list[str], *, note: str
    ) -> AdvisorAnswer:
        return AdvisorAnswer(
            question=question,
            answer=briefing,
            grounded_on=grounded_on,
            used_llm=False,
            note=note,
        )


def build_briefing(context: dict[str, Any]) -> tuple[str, list[str]]:
    """Assemble the grounded facts the Advisor answers from. Deterministic; no I/O.

    Returns ``(briefing_text, grounded_on)`` where ``grounded_on`` names the sections that
    actually had data — the provenance shown to the user.
    """
    lines: list[str] = []
    used: list[str] = []

    state = context.get("state") or {}
    if state:
        used.append("session state")
        cap = state.get("capital", {})
        lines.append(
            f"SESSION: mode={state.get('mode', '?')}, state={state.get('state', '?')}, "
            f"simulated={state.get('simulated', True)}."
        )
        if cap:
            lines.append(
                f"CAPITAL (simulated): equity {cap.get('equity', 0):,.2f}, "
                f"P&L {cap.get('total_pnl', 0):+,.2f} ({cap.get('return_pct', 0):+.2f}%), "
                f"max drawdown {cap.get('max_drawdown_pct', 0):.2f}%."
            )
        risk = state.get("risk") or {}
        if risk:
            lines.append(
                f"RISK: mode={risk.get('mode', '?')}, "
                f"new trades allowed={risk.get('new_trades_allowed', '?')}, "
                f"trades today={risk.get('trades_today', 0)}"
                + (f", kill switch: {risk['kill_switch_reason']}" if risk.get("kill_switch_reason") else "")
                + "."
            )

    positions = context.get("positions") or []
    if positions:
        used.append("open positions")
        lines.append("OPEN POSITIONS:")
        for p in positions[:8]:
            lines.append(
                f"  - {p.get('symbol')} {p.get('direction')} qty {p.get('quantity')} @ "
                f"{p.get('average_price')}, last {p.get('last_price')}, "
                f"unrealised {p.get('unrealized_pnl', 0):+.2f}."
            )
    elif state:
        lines.append("OPEN POSITIONS: none.")

    economics = context.get("economics") or {}
    if economics.get("available"):
        used.append("economics / expected value")
        ev = economics.get("expected_value") or {}
        lines.append(
            "WHY IT IS (OR IS NOT) TRADING: the system only trades a "
            "(regime, direction, confidence) bucket once it has enough closed trades to "
            "prove a positive edge after costs. "
            f"Evaluations so far: {ev.get('evaluations', 0)}, "
            f"accepted {ev.get('acceptance_rate', 0):.0%}, "
            f"refused for lack of evidence {ev.get('no_evidence', 0)}. "
            f"Minimum trades per bucket before it will act: {ev.get('min_samples', '?')}."
        )
        latest = ev.get("latest")
        if latest and latest.get("expected_value"):
            lines.append(f"  Latest pricing verdict: {latest['expected_value'].get('explanation', '')}")

    decisions = context.get("decisions") or []
    if decisions:
        used.append("recent decisions")
        lines.append("RECENT DECISIONS (its own stated reasoning):")
        for d in decisions[:6]:
            verdict = d.get("verdict", "?")
            thesis = d.get("thesis") or "(no thesis recorded)"
            why = "; ".join(d.get("why_enter", [])[:3]) or "—"
            why_not = "; ".join(d.get("why_not_enter", [])[:3])
            line = (
                f"  - {d.get('symbol')} {d.get('direction')} [{verdict}] "
                f"conf {d.get('confidence', 0):.2f}, regime {d.get('regime', '?')}: {thesis}"
            )
            if why != "—":
                line += f" Reasons for: {why}."
            if why_not:
                line += f" Reasons against: {why_not}."
            lines.append(line)

    learning = context.get("learning") or {}
    if learning.get("available") and learning.get("reviews"):
        used.append("learning report")
        error_bps = float(learning.get("mean_calibration_error_bps", 0) or 0.0)
        notional = float(learning.get("typical_notional_usd") or 0.0)
        # Spoken in dollars at the typical trade size when one is known — bps mean nothing
        # to the person asking. The engine itself still learns in bps.
        if notional > 0:
            error_usd = error_bps * notional / 10_000
            error_text = (
                f"{'+' if error_usd >= 0 else '-'}${abs(error_usd):,.2f} per trade "
                f"(typical trade ≈${notional:,.0f}, simulated)"
            )
        else:
            error_text = f"{error_bps:+.1f} bps"
        lines.append(
            f"WHAT IT HAS LEARNED: {learning.get('reviews', 0)} trades reviewed, "
            f"win rate {learning.get('win_rate', 0):.0%}, "
            f"mean calibration error {error_text}. "
            f"Guardrails now active on {len(learning.get('active_guardrails', []))} pattern(s)"
            + (
                f"; they have refused {learning.get('guardrail_rejected', 0)} trade(s)."
                if learning.get("applies_guardrails")
                else " (observe-only in the demo)."
            )
        )
        for lesson in (learning.get("recent_lessons") or [])[:4]:
            lines.append(f"  Lesson: {lesson.get('headline', '')}")

    antipatterns = context.get("antipatterns") or {}
    if antipatterns.get("checks"):
        used.append("behaviour audit")
        flagged = [c for c in antipatterns["checks"] if c.get("severity") in {"watch", "alert"}]
        if flagged:
            lines.append("BEHAVIOUR AUDIT — flags on its own recent trading:")
            for c in flagged:
                lines.append(f"  [{c['severity'].upper()}] {c['title']}: {c['detail']}")
        else:
            lines.append("BEHAVIOUR AUDIT: no anti-patterns flagged in recent trading.")

    mentor = context.get("mentor") or {}
    if mentor.get("available") and mentor.get("proposals"):
        used.append("mentor proposals")
        lines.append(
            "MENTOR — tighten-only proposals, each validated by replaying the recorded "
            "trades under the proposed rule:"
        )
        for prop in mentor["proposals"][:4]:
            verdict = prop.get("status", "?").upper()
            lines.append(
                f"  [{verdict}] {prop.get('title', '')} — {prop.get('rationale', '')} "
                f"Replay: {prop.get('validation', {}).get('detail', '')}"
            )

    intel = context.get("intel") or {}
    if intel.get("available") and intel.get("items"):
        used.append("market intel")
        lines.append(
            "MARKET INTEL — curated headlines (central banks + premier crypto press, "
            "relevance-filtered; informational only, the pipeline does not trade on them):"
        )
        for item in intel["items"][:6]:
            lines.append(
                f"  - [{item.get('kind', '?')}/{item.get('source', '?')}, relevance "
                f"{item.get('relevance', 0):.2f}] {item.get('headline', '')}"
            )

    focus = context.get("focus_decision")
    if focus:
        used.append("focused decision")
        checks = focus.get("risk_checks", [])
        passed = sum(1 for c in checks if c.get("passed"))
        lines.append(
            f"FOCUS — decision {focus.get('decision_id', '')}: {focus.get('symbol')} "
            f"{focus.get('direction')} [{focus.get('verdict')}], confidence "
            f"{focus.get('confidence', 0):.2f}, regime {focus.get('regime', '?')}.\n"
            f"  Thesis: {focus.get('thesis', '(none)')}\n"
            f"  Risk checks passed: {passed}/{len(checks)}.\n"
            f"  Reasons for: {'; '.join(focus.get('why_enter', [])) or '—'}\n"
            f"  Reasons against: {'; '.join(focus.get('why_not_enter', [])) or '—'}\n"
            f"  AI context effect: {focus.get('context_reason', 'none')}."
        )

    if not lines:
        return ("No session is running, so there is nothing to report yet. Start the 24/7 "
                "paper session or a demo run and ask again.", [])
    return ("\n".join(lines), used)


__all__ = ["ADVISOR_SYSTEM", "AdvisorAnswer", "AdvisorService", "build_briefing"]
