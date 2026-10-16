"""Cartera de dos cuentas (spot y futuros USDⓈ-M) con contabilidad explícita y registro de cada movimiento.

Estado: spot (U USDT, ``lotes_spot``) y futuros (W USDT, ``lotes_perp`` en corto con precio medio Fb). Las patas
tienen la misma cantidad salvo tras una liquidación del corto (spot descubierto hasta la siguiente apertura).

Todas las operaciones dejan un asiento en ``self.asientos``; ``hcarry.model.conciliacion`` reconstruye el equity
SOLO a partir de esos asientos, como comprobación independiente de esta contabilidad."""

from __future__ import annotations

from dataclasses import dataclass, field

from hcarry.model.costes import Costes, Filtros


class OperacionInviable(Exception):
    """La operación no se puede ejecutar con los saldos o filtros actuales."""


@dataclass
class Cartera:
    filtros: Filtros
    costes: Costes
    apalancamiento_max: float = 2.0  # margen inicial = nocional / L (para el transferible de futuros)
    U: float = 0.0
    W: float = 0.0
    lotes_spot: int = 0
    lotes_perp: int = 0
    Fb: float = 0.0
    asientos: list[dict] = field(default_factory=list)
    costes_acumulados: float = 0.0
    funding_acumulado: float = 0.0

    # ------------------------------------------------------------------ lecturas
    @property
    def q_spot(self) -> float:
        return self.filtros.cantidad(self.lotes_spot)

    @property
    def q_perp(self) -> float:
        return self.filtros.cantidad(self.lotes_perp)

    def no_realizado(self, F: float) -> float:
        return self.q_perp * (self.Fb - F)

    def equity_futuros(self, F: float) -> float:
        return self.W + self.no_realizado(F)

    def equity(self, S: float, F: float) -> float:
        return self.U + self.q_spot * S + self.equity_futuros(F)

    def rho(self, F: float) -> float | None:
        """Equity de futuros / nocional del corto. None sin posición."""
        if self.lotes_perp == 0:
            return None
        return self.equity_futuros(F) / (self.q_perp * F)

    def precio_liquidacion(self, mmr: float) -> float | None:
        """Mark al que el equity de futuros iguala el margen de mantenimiento: (W + q·Fb) / (q·(1 + mmr))."""
        if self.lotes_perp == 0:
            return None
        return (self.W + self.q_perp * self.Fb) / (self.q_perp * (1 + mmr))

    def transferible_futuros(self, M: float) -> float:
        """Máximo transferible de futuros a spot: W + min(0, no realizado) − margen inicial (q·M/L)."""
        return max(0.0, self.W + min(0.0, self.no_realizado(M)) - self.q_perp * M / self.apalancamiento_max)

    # ------------------------------------------------------------------ movimientos primitivos
    def _asiento(self, **kw) -> None:
        self.asientos.append(kw)

    def depositar(self, t: int, importe: float) -> None:
        self.U += importe
        self._asiento(t=t, tipo="deposito", importe=importe)

    def transferir(self, t: int, importe: float, M: float) -> None:
        """importe > 0: spot → futuros; importe < 0: futuros → spot."""
        if importe > 0:
            if importe > self.U + 1e-9:
                raise OperacionInviable(f"transferencia {importe:.6f} > efectivo spot {self.U:.6f}")
            self.U -= importe
            self.W += importe
        elif importe < 0:
            if -importe > self.transferible_futuros(M) + 1e-9:
                raise OperacionInviable(f"transferencia {-importe:.6f} > transferible de futuros "
                                        f"{self.transferible_futuros(M):.6f}")
            self.W += importe
            self.U -= importe
        else:
            return
        self._asiento(t=t, tipo="transferencia", importe=importe)

    def operar_spot(self, t: int, delta_lotes: int, S: float, volumen: float | None) -> float:
        """Compra (delta > 0) o vende spot al precio S; el coste se paga desde U. Devuelve el coste."""
        q = self.filtros.cantidad(abs(delta_lotes))
        coste = self.costes.coste("spot", q * S, volumen)
        if delta_lotes > 0:
            if q * S + coste > self.U + 1e-9:
                raise OperacionInviable(f"efectivo spot {self.U:.6f} < compra {q * S + coste:.6f}")
            self.U -= q * S + coste
        else:
            if abs(delta_lotes) > self.lotes_spot:
                raise OperacionInviable("venta spot mayor que la posición")
            self.U += q * S - coste
        self.lotes_spot += delta_lotes
        self.costes_acumulados += coste
        self._asiento(t=t, tipo="spot", lotes=delta_lotes, cantidad=q, precio=S, coste=coste)
        return coste

    def operar_perp(self, t: int, delta_lotes_corto: int, F: float, volumen: float | None) -> float:
        """Amplía (delta > 0, vende) o reduce (delta < 0, recompra) el corto al precio F. Coste desde W."""
        q = self.filtros.cantidad(abs(delta_lotes_corto))
        coste = self.costes.coste("perp", q * F, volumen)
        realizado = 0.0
        if delta_lotes_corto > 0:
            nuevo = self.lotes_perp + delta_lotes_corto
            self.Fb = (self.q_perp * self.Fb + q * F) / self.filtros.cantidad(nuevo)
            self.lotes_perp = nuevo
        else:
            if abs(delta_lotes_corto) > self.lotes_perp:
                raise OperacionInviable("recompra mayor que el corto")
            realizado = q * (self.Fb - F)
            self.lotes_perp += delta_lotes_corto
            self.W += realizado
            if self.lotes_perp == 0:
                self.Fb = 0.0
        self.W -= coste
        self.costes_acumulados += coste
        self._asiento(t=t, tipo="perp", lotes=delta_lotes_corto, cantidad=q, precio=F, coste=coste,
                      realizado=realizado)
        return coste

    def liquidar_funding(self, t: int, tasa: float, mark: float) -> float:
        """El corto cobra q·m·f (f > 0) o paga (f < 0). Devuelve el importe abonado a W."""
        if self.lotes_perp == 0:
            return 0.0
        importe = self.q_perp * mark * tasa
        self.W += importe
        self.funding_acumulado += importe
        self._asiento(t=t, tipo="funding", tasa=tasa, mark=mark, cantidad=self.q_perp, importe=importe)
        return importe

    def liquidacion(self, t: int, precio: float, comision: float) -> float:
        """Cierre forzoso del corto al precio de liquidación; comisión en fracción del nocional. Devuelve la pérdida
        de la pata corta (realizado negativo + comisión)."""
        q = self.q_perp
        realizado = q * (self.Fb - precio)
        fee = comision * q * precio
        self.W += realizado - fee
        if self.W < 0:  # saldo negativo: lo cubre el fondo de seguros; se registra el exceso
            self._asiento(t=t, tipo="nota", texto=f"saldo de futuros negativo {self.W:.6f} → 0 (fondo de seguros)",
                          ajuste=-self.W)
            self.W = 0.0
        self.costes_acumulados += fee
        self._asiento(t=t, tipo="liquidacion", lotes=-self.lotes_perp, cantidad=q, precio=precio, coste=fee,
                      realizado=realizado)
        self.lotes_perp = 0
        self.Fb = 0.0
        return realizado - fee
