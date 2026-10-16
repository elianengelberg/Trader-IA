"""Motor horario de H-CARRY Next.

Orden de los sucesos en cada barra i (apertura t):
  1. Funding: se liquidan los eventos con marca t sobre la posición mantenida durante la hora anterior.
  2. Liquidación por salto: si el mark de apertura ya supera el precio de liquidación, se liquida a ese mark.
  3. Spot descubierto (tras una liquidación): se vende el excedente de spot a la apertura (regla de riesgo).
  4. Última barra: se cierra todo a la apertura y termina (salida de rev. 5).
  5. Ejecución de la orden pendiente programada para esta barra (estrés de retraso) y, si no hay ninguna, decisión de
     la política con la ``Vista`` de t y ejecución inmediata (retraso 0) o programada (retraso k).
  6. Liquidación dentro de la barra: si el mark MÁXIMO de la hora alcanza el precio de liquidación.
  7. Valoración al cierre: E = U + q_spot·S_c + W + q_perp·(Fb − F_c).

La equity ejecutable usa el último precio del perpetuo; el margen y la liquidación usan el mark."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from hcarry.conventions import BP, HORA_MS, iso
from hcarry.data.schema import Barra, Panel
from hcarry.estrategias import EstadoVisible, Objetivo, Politica, Vista
from hcarry.model.cartera import Cartera, OperacionInviable
from hcarry.model.costes import Costes, Filtros


@dataclass(frozen=True)
class ParamsMotor:
    capital: float = 10_000.0
    mmr: float = 0.01                  # margen de mantenimiento fijo (rev. 5)
    apalancamiento_max: float = 2.0    # margen inicial = nocional / L (transferible de futuros; rev. 5: 2)
    comision_liquidacion: float = 0.0  # fracción del nocional al liquidar (rev. 5: no modelada)
    retraso_barras: int = 0            # estrés: la decisión de t se ejecuta k barras después
    al_inviable: str = "omitir"        # "detener" = regla R0 de rev. 5; "omitir" = ejecutar lo viable o nada
    enfriamiento_h: int = 24           # horas sin reentrar tras una liquidación
    pata_perp_adversa: bool = False    # estrés: el perpetuo se ejecuta en el extremo adverso de la barra


class Detencion(Exception):
    """Ampliación inviable con la regla R0: la simulación se detiene (E1 de rev. 5)."""


@dataclass
class Resultado:
    estado: str                         # completada | detenida_E1
    origen: str
    politica: str
    parametros_politica: dict
    params: dict
    costes: dict
    filtros: dict
    inicio: int
    n_barras: int
    capital: float
    final: float
    serie: list[tuple]                  # (t_cierre, E, U, W, lotes_spot, lotes_perp, Fb, comprometido)
    operaciones: list[dict] = field(default_factory=list)
    funding: list[dict] = field(default_factory=list)
    rechazos: list[dict] = field(default_factory=list)
    liquidaciones: list[dict] = field(default_factory=list)
    asientos: list[dict] = field(default_factory=list)
    costes_total: float = 0.0
    funding_total: float = 0.0
    distancia_min_liquidacion: tuple[float, int] | None = None   # (distancia relativa, hora)
    notas: list[str] = field(default_factory=list)

    @property
    def dias(self) -> float:
        """Días FIJOS de la ventana: (n − 1)/24, de la apertura de la primera hora a la de la última (D1 rev. 5)."""
        return (self.n_barras - 1) / 24


@dataclass
class _Orden:
    lotes_objetivo: int
    rho: float
    escala: float
    motivo: str
    decidida_en: int


class Motor:
    def __init__(self, panel: Panel, politica: Politica, costes: Costes | None = None, filtros: Filtros | None = None,
                 params: ParamsMotor | None = None) -> None:
        self.panel, self.politica = panel, politica
        self.costes, self.filtros, self.p = costes or Costes(), filtros or Filtros(), params or ParamsMotor()
        if self.p.al_inviable not in ("omitir", "detener"):
            raise ValueError("al_inviable debe ser 'omitir' o 'detener'")
        self.c = Cartera(self.filtros, self.costes, self.p.apalancamiento_max)
        self.ops: list[dict] = []
        self.rechazos: list[dict] = []
        self.liqs: list[dict] = []
        self.notas: list[str] = []
        self.horas_en_posicion = 0
        self.ultima_salida: int | None = None
        self.enfriamiento_hasta = -1
        self.dist_min: tuple[float, int] | None = None
        self.pendientes: dict[int, _Orden] = {}

    # ------------------------------------------------------------------ dimensionamiento
    def lotes_objetivo(self, rho: float, escala: float, S: float, F: float) -> int:
        """Lotes que dejan la cartera con equity desplegado = escala·E y ratio de futuros = rho, descontando los costes
        de la propia operación (dos iteraciones de punto fijo) y redondeando hacia abajo."""
        c = self.c
        E = c.equity(S, F)
        k = (S * self.costes.bps("spot") + F * self.costes.bps("perp")) * BP * self.costes.multiplicador
        q0 = c.q_perp
        q = escala * E / (S + rho * F)
        for _ in range(3):
            q = escala * (E - abs(q - q0) * k) / (S + rho * F)
        return self.filtros.lotes(max(0.0, q))

    # ------------------------------------------------------------------ ejecución
    def _registrar(self, b: Barra, tipo: str, delta: int, S: float, F: float, coste_s: float, coste_p: float,
                   motivo: str, ordenes: int) -> None:
        base_adversa = (S - F) / S if delta > 0 else (F - S) / S
        self.ops.append({"t": b.t, "tipo": tipo, "lotes": delta, "cantidad": self.filtros.cantidad(abs(delta)),
                         "S": S, "F": F, "coste_spot": coste_s, "coste_perp": coste_p, "base_adversa": base_adversa,
                         "ordenes": ordenes, "motivo": motivo, "lotes_despues": self.c.lotes_perp})

    def _precio_perp(self, b: Barra, delta: int) -> float:
        if not self.p.pata_perp_adversa:
            return b.F_o
        return b.F_l if delta > 0 else b.F_h  # vender el perp al mínimo, recomprarlo al máximo

    def _ejecutar(self, b: Barra, n_obj: int, rho: float, escala: float, motivo: str) -> None:
        c, f = self.c, self.filtros
        n = c.lotes_perp
        delta = n_obj - n
        if delta == 0:
            return
        S, F, M = b.S_o, self._precio_perp(b, delta), b.M_o
        cierre_total = n_obj == 0
        rechazo = f.motivo_rechazo(delta, S, F, cierre_total)
        if rechazo:
            self.rechazos.append({"t": b.t, "lotes": delta, "motivo": rechazo})
            return
        tipo = "apertura" if n == 0 else "cierre" if cierre_total else "aumento" if delta > 0 else "reduccion"
        try:
            if delta < 0:
                coste_s = c.operar_spot(b.t, delta, S, b.qv_spot)
                if not cierre_total:
                    destino = c.U if escala >= 1 else max(0.0, min(c.U, rho * f.cantidad(n_obj) * F - c.equity_futuros(F)))
                    c.transferir(b.t, destino, M)
                coste_p = c.operar_perp(b.t, delta, F, b.qv_perp)
                if cierre_total:
                    c.transferir(b.t, -c.W, M)
            else:
                delta = self._delta_viable(b, delta, S, F, M)
                if delta <= 0:
                    return
                n_obj = n + delta
                q = f.cantidad(delta)
                coste_s_est = self.costes.coste("spot", q * S, b.qv_spot)
                falta = q * S + coste_s_est - c.U
                if falta > 0:
                    c.transferir(b.t, -falta, M)
                coste_s = c.operar_spot(b.t, delta, S, b.qv_spot)
                coste_p_est = self.costes.coste("perp", q * F, b.qv_perp)
                if escala >= 1:
                    destino = c.U
                else:
                    destino = max(0.0, min(c.U, rho * f.cantidad(n_obj) * F + coste_p_est - c.equity_futuros(F)))
                c.transferir(b.t, destino, M)
                coste_p = c.operar_perp(b.t, delta, F, b.qv_perp)
        except OperacionInviable as exc:  # no debería ocurrir tras _delta_viable; se registra si ocurre
            raise RuntimeError(f"{iso(b.t)}: operación inconsistente: {exc}") from exc
        self._registrar(b, tipo, delta, S, F, coste_s, coste_p, motivo, f.ordenes(delta))
        if n == 0:
            self.horas_en_posicion = 0
        if cierre_total:
            self.ultima_salida = b.t

    def _delta_viable(self, b: Barra, delta: int, S: float, F: float, M: float) -> int:
        """Mayor ampliación ≤ delta financiable sin violar el margen inicial: el efectivo de spot más lo transferible
        de futuros (dejando margen para el corto ampliado) debe cubrir la compra de spot y la comisión del perp."""
        c, f = self.c, self.filtros
        ks = self.costes.bps("spot") * BP * self.costes.multiplicador
        kp = self.costes.bps("perp") * BP * self.costes.multiplicador
        L = self.p.apalancamiento_max
        disponible = c.U + c.W + min(0.0, c.no_realizado(M)) - c.q_perp * M / L
        por_lote = f.paso * (S * (1 + ks) + M / L + F * kp)
        maximo = int(disponible / por_lote) if disponible > 0 else 0
        while maximo > 0 and self._necesidad(b, maximo, S, F, M) > disponible + 1e-9:
            maximo -= 1  # el impacto no lineal puede encarecer la estimación lineal
        if maximo >= delta:
            return delta
        if self.p.al_inviable == "detener":
            raise Detencion(f"{iso(b.t)}: ampliación de {delta} lotes inviable (máximo {maximo})")
        self.rechazos.append({"t": b.t, "lotes": delta, "motivo": f"ampliación limitada a {maximo} lotes"})
        if maximo <= 0 or f.motivo_rechazo(maximo, S, F, False):
            return 0
        return maximo

    def _necesidad(self, b: Barra, lotes: int, S: float, F: float, M: float) -> float:
        q = self.filtros.cantidad(lotes)
        return (q * S + self.costes.coste("spot", q * S, b.qv_spot) + q * M / self.p.apalancamiento_max
                + self.costes.coste("perp", q * F, b.qv_perp))

    def _orden(self, obj: Objetivo, b: Barra, i: int) -> _Orden | None:
        c = self.c
        if not obj.en_mercado:
            return _Orden(0, obj.rho, obj.escala, "salida", i) if c.lotes_perp else None
        if b.t < self.enfriamiento_hasta:
            return None
        n_obj = self.lotes_objetivo(obj.rho, obj.escala, b.S_o, b.F_o)
        if c.lotes_perp == 0:
            return _Orden(n_obj, obj.rho, obj.escala, "entrada", i) if n_obj else None
        rho = c.rho(b.F_o)
        lo, hi = obj.banda
        if rho < lo or rho > hi:
            return _Orden(n_obj, obj.rho, obj.escala, f"reequilibrio rho={rho:.3f}", i)
        if obj.tolerancia is not None and abs(n_obj - c.lotes_perp) > obj.tolerancia * c.lotes_perp:
            return _Orden(n_obj, obj.rho, obj.escala, f"ajuste de tamaño {c.lotes_perp}→{n_obj}", i)
        return None

    # ------------------------------------------------------------------ liquidación
    def _comprobar_liquidacion(self, b: Barra, precio_extremo: float, en_apertura: bool) -> None:
        c = self.c
        p_liq = c.precio_liquidacion(self.p.mmr)
        if p_liq is None:
            return
        d = p_liq / b.M_o - 1
        if self.dist_min is None or d < self.dist_min[0]:
            self.dist_min = (d, b.t)
        if precio_extremo >= p_liq:
            precio = precio_extremo if en_apertura else p_liq  # en un salto de apertura no se llega a P_liq
            perdida = c.liquidacion(b.t, precio, self.p.comision_liquidacion)
            self.liqs.append({"t": b.t, "precio": precio, "precio_liquidacion": p_liq, "en_apertura": en_apertura,
                              "resultado_pata_corta": perdida})
            self.enfriamiento_hasta = b.t + self.p.enfriamiento_h * HORA_MS
            self.pendientes.clear()  # una orden decidida antes de la liquidación ya no es válida

    # ------------------------------------------------------------------ bucle
    def correr(self) -> Resultado:
        panel, c = self.panel, self.c
        barras = panel.barras
        fpor_t = {e.t: e for e in panel.funding}
        marcas = [e.t for e in panel.funding]
        c.depositar(barras[0].t, self.p.capital)
        serie: list[tuple] = []
        pendientes = self.pendientes
        estado = "completada"
        n = len(barras)
        for i, b in enumerate(barras):
            ev = fpor_t.get(b.t)
            if ev is not None:
                c.liquidar_funding(b.t, ev.tasa, ev.mark if ev.mark is not None else b.M_o)
            if c.lotes_perp:
                self._comprobar_liquidacion(b, b.M_o, en_apertura=True)
            if c.lotes_spot > c.lotes_perp:  # spot descubierto tras liquidación: se vende a la apertura
                exceso = c.lotes_spot - c.lotes_perp
                coste = c.operar_spot(b.t, -exceso, b.S_o, b.qv_spot)
                self.ops.append({"t": b.t, "tipo": "venta_spot_descubierto", "lotes": -exceso,
                                 "cantidad": self.filtros.cantidad(exceso), "S": b.S_o, "F": b.F_o,
                                 "coste_spot": coste, "coste_perp": 0.0, "base_adversa": None, "ordenes": 1,
                                 "motivo": "tras liquidación", "lotes_despues": c.lotes_perp})
                if c.lotes_perp == 0 and c.W > 0:
                    c.transferir(b.t, -c.W, b.M_o)
                    self.ultima_salida = b.t
            if i == n - 1:
                if c.lotes_perp:
                    self._ejecutar(b, 0, 1.0, 1.0, "fin de la ventana")
                break
            try:
                orden = pendientes.pop(i, None)
                if orden is not None and b.relleno:
                    pendientes[i + 1] = orden  # no se ejecuta en una hora sin datos
                elif orden is not None:
                    self._ejecutar(b, orden.lotes_objetivo, orden.rho, orden.escala, orden.motivo + " (retrasada)")
                elif not b.relleno and not any(k > i for k in pendientes):
                    vista = Vista(barras, panel.funding, marcas, i, self._estado_visible(b))
                    orden = self._orden(self.politica.decidir(vista), b, i)
                    if orden is not None:
                        if self.p.retraso_barras == 0:
                            self._ejecutar(b, orden.lotes_objetivo, orden.rho, orden.escala, orden.motivo)
                        else:
                            pendientes[i + self.p.retraso_barras] = orden
            except Detencion as exc:
                estado = "detenida_E1"
                self.notas.append(str(exc))
                if c.lotes_perp:
                    self._ejecutar(b, 0, 1.0, 1.0, "detención E1")
                break
            if c.lotes_perp:
                self._comprobar_liquidacion(b, b.M_h, en_apertura=False)
                self.horas_en_posicion += 1
            E = c.equity(b.S_c, b.F_c)
            comprometido = (c.q_spot * b.S_c + c.equity_futuros(b.F_c)) if (c.lotes_perp or c.lotes_spot) else 0.0
            serie.append((b.t + HORA_MS, E, c.U, c.W, c.lotes_spot, c.lotes_perp, c.Fb, comprometido))
        final = c.equity(barras[-1].S_o, barras[-1].F_o) if estado == "completada" else c.U + c.W
        if c.lotes_perp or c.lotes_spot:
            raise RuntimeError("quedó posición abierta al final")
        return Resultado(
            estado=estado, origen=panel.origen, politica=self.politica.nombre,
            parametros_politica=self.politica.parametros(), params=asdict(self.p), costes=asdict(self.costes),
            filtros=asdict(self.filtros), inicio=barras[0].t, n_barras=n if estado == "completada" else len(serie) + 1,
            capital=self.p.capital, final=final, serie=serie, operaciones=self.ops,
            funding=[a for a in c.asientos if a["tipo"] == "funding"], rechazos=self.rechazos,
            liquidaciones=self.liqs, asientos=c.asientos, costes_total=c.costes_acumulados,
            funding_total=c.funding_acumulado, distancia_min_liquidacion=self.dist_min,
            notas=list(panel.notas) + self.notas)

    def _estado_visible(self, b: Barra) -> EstadoVisible:
        c = self.c
        en = c.lotes_perp > 0
        desde = None if self.ultima_salida is None else (b.t - self.ultima_salida) // HORA_MS
        return EstadoVisible(en, c.rho(b.F_o), c.equity(b.S_o, b.F_o), self.horas_en_posicion if en else 0, desde)


def simular(panel: Panel, politica: Politica, costes: Costes | None = None, filtros: Filtros | None = None,
            params: ParamsMotor | None = None) -> Resultado:
    return Motor(panel, politica, costes, filtros, params).correr()


__all__ = ["Detencion", "Motor", "ParamsMotor", "Resultado", "simular"]
