"""Instruments and timeframes."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tia.domain.enums import AssetClass

_TIMEFRAME_RE = re.compile(r"^(\d+)(s|m|h|d|w)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


class Timeframe(BaseModel):
    """A bar interval such as ``1m`` or ``4h``."""

    model_config = ConfigDict(frozen=True)

    value: str

    @field_validator("value")
    @classmethod
    def _valid(cls, v: str) -> str:
        if not _TIMEFRAME_RE.match(v):
            raise ValueError(f"invalid timeframe {v!r}; expected e.g. '1m', '15m', '4h', '1d'")
        return v

    @classmethod
    def parse(cls, value: str | Timeframe) -> Timeframe:
        return value if isinstance(value, Timeframe) else cls(value=value)

    @property
    def seconds(self) -> int:
        match = _TIMEFRAME_RE.match(self.value)
        if match is None:  # pragma: no cover - the validator makes this unreachable
            raise ValueError(f"invalid timeframe {self.value!r}")
        return int(match.group(1)) * _UNIT_SECONDS[match.group(2)]

    @property
    def delta(self) -> timedelta:
        return timedelta(seconds=self.seconds)

    def bars_per_year(self) -> float:
        """Bars in a 365-day year — the annualization factor for metrics."""
        return 365 * 24 * 3600 / self.seconds

    def floor(self, moment: datetime) -> datetime:
        """Round ``moment`` down to the start of its bar."""
        epoch_seconds = int(moment.timestamp())
        return datetime.fromtimestamp(
            epoch_seconds - (epoch_seconds % self.seconds), tz=moment.tzinfo
        )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class Instrument(BaseModel):
    """A tradable (in simulation) instrument.

    ``listed_on`` / ``delisted_on`` exist so the backtester can build a point-in-time
    universe. Without them, every historical study silently inherits survivorship bias.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=32)
    asset_class: AssetClass
    base_currency: str = "USD"
    quote_currency: str = "USD"
    tick_size: float = Field(0.01, gt=0)
    lot_size: float = Field(1e-8, gt=0)
    min_notional: float = Field(0.0, ge=0)
    max_leverage: float = Field(1.0, gt=0, le=100)
    shortable: bool = True
    correlation_cluster: str = "default"
    listed_on: date | None = None
    delisted_on: date | None = None
    venue: str = "simulated"

    def is_listed_at(self, moment: datetime) -> bool:
        day = moment.date()
        if self.listed_on is not None and day < self.listed_on:
            return False
        return not (self.delisted_on is not None and day >= self.delisted_on)

    def round_price(self, price: float) -> float:
        return round(round(price / self.tick_size) * self.tick_size, 10)

    def round_quantity(self, quantity: float) -> float:
        """Round *down* to a valid lot. Rounding up could exceed a risk-approved size."""
        lots = int(abs(quantity) / self.lot_size)
        rounded = lots * self.lot_size
        return round(rounded if quantity >= 0 else -rounded, 12)


class InstrumentUniverse(BaseModel):
    """Point-in-time instrument set."""

    model_config = ConfigDict(frozen=True)

    instruments: tuple[Instrument, ...]

    def get(self, symbol: str) -> Instrument | None:
        return next((i for i in self.instruments if i.symbol == symbol), None)

    def require(self, symbol: str) -> Instrument:
        found = self.get(symbol)
        if found is None:
            from tia.core.errors import UnknownInstrumentError

            raise UnknownInstrumentError(f"unknown instrument {symbol!r}", symbol=symbol)
        return found

    def as_of(self, moment: datetime) -> InstrumentUniverse:
        return InstrumentUniverse(
            instruments=tuple(i for i in self.instruments if i.is_listed_at(moment))
        )

    def clusters(self) -> dict[str, tuple[str, ...]]:
        out: dict[str, list[str]] = {}
        for inst in self.instruments:
            out.setdefault(inst.correlation_cluster, []).append(inst.symbol)
        return {k: tuple(v) for k, v in out.items()}

    def __len__(self) -> int:
        return len(self.instruments)


DEFAULT_UNIVERSE = InstrumentUniverse(
    instruments=(
        Instrument(
            symbol="BTC-USD",
            asset_class=AssetClass.CRYPTO,
            tick_size=0.01,
            lot_size=1e-6,
            min_notional=10.0,
            correlation_cluster="crypto",
        ),
        Instrument(
            symbol="ETH-USD",
            asset_class=AssetClass.CRYPTO,
            tick_size=0.01,
            lot_size=1e-5,
            min_notional=10.0,
            correlation_cluster="crypto",
        ),
        Instrument(
            symbol="SPX-IDX",
            asset_class=AssetClass.INDEX,
            tick_size=0.25,
            lot_size=0.01,
            min_notional=25.0,
            shortable=True,
            correlation_cluster="equity_beta",
        ),
    )
)

__all__ = ["DEFAULT_UNIVERSE", "Instrument", "InstrumentUniverse", "Timeframe"]
