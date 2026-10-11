"""F10 (Phase 1.3): the frequency-state rebuild reads back far enough for the cooldown.

Two days was a fixed assumption in the application's restore; it is now the floor, and a
configured cooldown longer than a day widens the read to twice its span, so a cooldown
armed before the restart is still seen after it whatever its length.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.integration.test_live_api import _FakePublicFeed, _settings
from tia.api.state import AppState
from tia.persistence import RiskStateRepository
from tia.risk.restore import RiskRestore


@pytest.fixture(autouse=True)
def _feed(monkeypatch: pytest.MonkeyPatch) -> None:
    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)


async def _lookback_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, cooldown_seconds: int) -> timedelta:
    settings = _settings(tmp_path)
    settings = settings.model_copy(
        update={"risk": settings.risk.propose_change(trade_cooldown_seconds=cooldown_seconds)}
    )
    state = AppState(settings)
    await state.database.ensure_schema()
    seen: dict[str, Any] = {}

    async def recording(self: Any, *, now: Any, lookback: timedelta = timedelta(days=2), modes: Any = None) -> Any:
        seen["lookback"] = lookback
        return RiskRestore.empty(day=now.date().isoformat())

    monkeypatch.setattr(RiskStateRepository, "rebuild", recording)
    restore = await state._load_risk_restore()
    assert restore.complete
    return seen["lookback"]


async def test_the_default_cooldown_reads_two_days_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _lookback_used(tmp_path, monkeypatch, cooldown_seconds=300) == timedelta(days=2)


async def test_a_long_cooldown_widens_the_read_to_twice_its_span(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    four_days = 4 * 86_400
    assert await _lookback_used(tmp_path, monkeypatch, cooldown_seconds=four_days) == timedelta(seconds=2 * four_days)


async def test_a_cooldown_shorter_than_a_day_never_narrows_the_floor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _lookback_used(tmp_path, monkeypatch, cooldown_seconds=0) == timedelta(days=2)
