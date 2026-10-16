"""Generador SINTÉTICO de mercado BTC spot/perpetuo para probar la maquinaria. NO es evidencia económica.

Modelo (todo con ``random.Random(semilla)``, reproducible):
  - Régimen de Markov horario (alcista / tranquilo / bajista) con duración media en días.
  - Spot: 12 subpasos de 5 minutos por hora con deriva y volatilidad del régimen, más saltos raros.
  - Prima del perpetuo p (fracción, F = S·(1 + p)): proceso de Ornstein-Uhlenbeck horario hacia la media del régimen.
  - Mark: S·(1 + p_ema), con p_ema una media exponencial de la prima.
  - Funding cada ``intervalo_h`` horas con la fórmula de Binance: f = P̄ + clamp(I − P̄, −0,05 %, +0,05 %), con P̄ la prima
    media del intervalo e I = 0,01 % por 8 h (escalado al intervalo), acotado a ±``tope``. Por eso la tasa modal es
    exactamente el interés en los períodos tranquilos, como en los datos reales.
  - Volumen en USDT lognormal (spot y perp).

Los parámetros por defecto son plausibles, no calibrados contra datos reales: sirven para ejercitar estrategias y
estrés, no para estimar rentabilidades."""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field, replace

from hcarry.conventions import HORA_MS, comprobar_fuera_de_reservado
from hcarry.data.schema import Barra, EventoFunding, Panel


@dataclass(frozen=True)
class Regimen:
    nombre: str
    deriva_anual: float
    vol_anual: float
    prima_media: float        # fracción (0.0005 = 5 bps)
    prima_vol_h: float        # desviación de la innovación horaria de la prima
    duracion_media_dias: float


# Con la fórmula de Binance, una prima media en [−0,04 %, +0,06 %] da exactamente el interés (+0,01 %/8 h): el régimen
# tranquilo cobra eso casi siempre; el alcista, más; el bajista paga a menudo (prima media −0,08 %).
REGIMENES = (
    Regimen("alcista", 0.9, 0.65, 0.0008, 0.00030, 80.0),
    Regimen("tranquilo", 0.05, 0.40, 0.0, 0.00015, 120.0),
    Regimen("bajista", -0.7, 0.80, -0.0008, 0.00030, 60.0),
)


@dataclass(frozen=True)
class ParamsSintetico:
    semilla: int = 1
    desde: str = "2019-10-01"
    hasta: str = "2026-06-01"
    precio_inicial: float = 8_000.0
    intervalo_h: int = 8
    reversion_prima_h: float = 0.08
    ema_mark_h: float = 0.3
    prob_salto_h: float = 0.0015
    salto_sd: float = 0.04
    interes_8h: float = 0.0001
    tope: float = 0.003
    volumen_spot_usdt: float = 3e8
    volumen_perp_usdt: float = 9e8
    regimenes: tuple[Regimen, ...] = field(default=REGIMENES)
    variante: str = "base"  # "bajista_suave": régimen bajista con prima −0,03 % (funding ≈ interés, rara vez negativo)

    def descripcion(self) -> dict:
        d = asdict(self)
        d["regimenes"] = [asdict(r) for r in self.regimenes]
        return d


def generar(p: ParamsSintetico | None = None) -> Panel:
    p = p or ParamsSintetico()
    from hcarry.conventions import ms
    ini, fin = ms(p.desde), ms(p.hasta)
    comprobar_fuera_de_reservado(ini, fin)
    regimenes = p.regimenes
    if p.variante == "bajista_suave":
        regimenes = tuple(replace(r, prima_media=-0.0003) if r.nombre == "bajista" else r for r in regimenes)
    elif p.variante != "base":
        raise ValueError(f"variante desconocida: {p.variante}")
    rng = random.Random(p.semilla)
    sub = 12
    dt_sub = 1 / (365 * 24 * sub)
    reg = 1
    S = p.precio_inicial
    prima = regimenes[reg].prima_media
    prima_ema = prima
    barras: list[Barra] = []
    eventos: list[EventoFunding] = []
    primas_intervalo: list[float] = []
    interes = p.interes_8h * p.intervalo_h / 8
    tope = p.tope * p.intervalo_h / 8
    for t in range(ini, fin, HORA_MS):
        r = regimenes[reg]
        if rng.random() < 1 / (r.duracion_media_dias * 24):
            reg = rng.choice([k for k in range(len(regimenes)) if k != reg])
            r = regimenes[reg]
        # funding en la apertura t, con la prima media del intervalo anterior
        if (t // HORA_MS) % p.intervalo_h == 0:
            pm = sum(primas_intervalo) / len(primas_intervalo) if primas_intervalo else prima
            f = pm + min(0.0005, max(-0.0005, interes - pm))
            f = min(tope, max(-tope, f))
            eventos.append(EventoFunding(t, round(f, 8), round(S * (1 + prima_ema), 2)))
            primas_intervalo = []
        prima_ini, S_ini = prima, S
        prima = prima + p.reversion_prima_h * (r.prima_media - prima) + r.prima_vol_h * rng.gauss(0, 1)
        sigma = r.vol_anual * math.sqrt(dt_sub)
        mu = (r.deriva_anual - 0.5 * r.vol_anual ** 2) * dt_sub
        salto_en = rng.randrange(sub) if rng.random() < p.prob_salto_h else -1
        sh = sl = S
        fh = fl = S * (1 + prima_ini)
        mh = ml = S * (1 + prima_ema)
        for k in range(sub):
            x = mu + sigma * rng.gauss(0, 1)
            if k == salto_en:
                x += p.salto_sd * rng.gauss(0, 1)
            S *= math.exp(x)
            pk = prima_ini + (prima - prima_ini) * (k + 1) / sub
            Fk = S * (1 + pk)
            prima_ema_k = prima_ema + p.ema_mark_h * (pk - prima_ema) * (k + 1) / sub
            Mk = S * (1 + prima_ema_k)
            sh, sl = max(sh, S), min(sl, S)
            fh, fl = max(fh, Fk), min(fl, Fk)
            mh, ml = max(mh, Mk), min(ml, Mk)
        prima_ema += p.ema_mark_h * (prima - prima_ema)
        primas_intervalo.append(prima)
        Fo, Fc = S_ini * (1 + prima_ini), S * (1 + prima)
        Mo = barras[-1].M_c if barras else S_ini * (1 + prima_ini)
        Mc = S * (1 + prima_ema)
        mult = r.vol_anual / 0.5
        barras.append(Barra(t, S_ini, sh, sl, S, Fo, max(fh, Fo, Fc), min(fl, Fo, Fc), Fc, Mo, max(mh, Mo, Mc),
                            min(ml, Mo, Mc), Mc,
                            p.volumen_spot_usdt * mult * math.exp(0.5 * rng.gauss(0, 1) - 0.125),
                            p.volumen_perp_usdt * mult * math.exp(0.5 * rng.gauss(0, 1) - 0.125), prima=prima))
    return Panel(barras, eventos, f"sintetico:semilla={p.semilla}:{p.variante}",
                 [f"SINTÉTICO: generado con hcarry.data.sintetico (semilla {p.semilla}); no son datos de mercado"])
