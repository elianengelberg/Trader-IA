"""Datos SINTÉTICOS deterministas para las pruebas y para la calibración del MEC §5. Nunca son datos de mercado.

- ``velas``: OHLCV continuas (apertura = cierre anterior), con semilla.
- ``inyectar``: defectos conocidos para probar el validador (hueco, duplicado, conflicto, OHLC incoherente, etc.).
- ``proceso``: las seis series de exceso del MEC §5 (C1–C6), con media POBLACIONAL 0 bajo H₀ y desvío diario ``sd``."""
from __future__ import annotations

import math
import random


def velas(n: int, intervalo_ms: int = 3_600_000, inicio_ms: int = 1_798_761_600_000, precio0: float = 100.0,
          vol: float = 0.01, deriva: float = 0.0, semilla: int = 7) -> list[dict]:
    rng = random.Random(semilla)
    filas, c = [], precio0
    for i in range(n):
        o = c
        c = o * math.exp(deriva + vol * rng.gauss(0.0, 1.0))
        hi = max(o, c) * (1 + abs(rng.gauss(0.0, vol / 2)))
        lo = min(o, c) * (1 - abs(rng.gauss(0.0, vol / 2)))
        filas.append({"t": inicio_ms + i * intervalo_ms, "open": o, "high": hi, "low": lo, "close": c,
                      "volume": abs(rng.gauss(1000.0, 100.0))})
    return filas


def inyectar(filas: list[dict], defecto: str, i: int = 10) -> list[dict]:
    f = [dict(x) for x in filas]
    if defecto == "hueco":
        del f[i]
    elif defecto == "duplicado":
        f.insert(i + 1, dict(f[i]))
    elif defecto == "conflicto":
        f.insert(i + 1, {**f[i], "close": f[i]["close"] * 1.01, "high": f[i]["high"] * 1.02})
    elif defecto == "desorden":
        f[i], f[i + 1] = f[i + 1], f[i]
    elif defecto == "fuera_de_grilla":
        f[i]["t"] += 1
    elif defecto == "ohlc_incoherente":
        f[i]["low"] = f[i]["high"] * 1.01
    elif defecto == "volumen_negativo":
        f[i]["volume"] = -1.0
    elif defecto == "no_finito":
        f[i]["close"] = float("nan")
    elif defecto == "campo_faltante":
        del f[i]["volume"]
    elif defecto == "precio_cero":
        f[i]["low"] = 0.0
    else:
        raise ValueError(defecto)
    return f


def _t(rng: random.Random, nu: int) -> float:
    """t de Student con ν grados de libertad, reescalada a varianza 1."""
    z = rng.gauss(0.0, 1.0)
    chi2 = sum(rng.gauss(0.0, 1.0) ** 2 for _ in range(nu))
    return z / math.sqrt(chi2 / nu) * math.sqrt((nu - 2) / nu)


def proceso(nombre: str, n: int, semilla: int, sd: float = 0.01) -> list[float]:
    """Series de exceso del MEC v0.2 §5, centradas exactamente (media muestral 0) y con desvío ``sd``."""
    rng = random.Random(f"{nombre}-{n}-{semilla}")
    if nombre == "C1":  # t₃ i.i.d.
        x = [_t(rng, 3) for _ in range(n)]
    elif nombre == "C2":  # GARCH(1,1) α = 0,10, β = 0,85, innovaciones t₄
        a, b = 0.10, 0.85
        w = 1 - a - b
        h, e, x = 1.0, 0.0, []
        for _ in range(n + 500):
            h = w + a * e * e + b * h
            e = math.sqrt(h) * _t(rng, 4)
            x.append(e)
        x = x[500:]
    elif nombre == "C3":  # AR(1) φ = 0,2 con t₃
        x, v = [], 0.0
        for _ in range(n + 200):
            v = 0.2 * v + _t(rng, 3)
            x.append(v)
        x = x[200:]
    elif nombre == "C4":  # exposición de Markov dispersa × rendimiento GARCH-t₄ independiente
        r = proceso("C2", n, semilla + 1, 1.0)
        w, on = [], 0
        for _ in range(n):
            on = (1 if rng.random() < 0.005 else 0) if on == 0 else (0 if rng.random() < 1 / 6 else 1)
            w.append(on)
        wb = sum(w) / n
        x = [(wi - wb) * ri for wi, ri in zip(w, r, strict=True)]
        if all(v == 0 for v in x):  # sin eventos: la serie es nula; se informa como degenerada aguas arriba
            return x
    elif nombre == "C5":  # intradía agregado: K ~ Poisson(0,6) excesos t₄ (desvío 1,5 %) por día
        x = []
        for _ in range(n):
            k, p, lim = 0, 1.0, math.exp(-0.6)
            while True:
                p *= rng.random()
                if p <= lim:
                    break
                k += 1
            x.append(sum(0.015 * _t(rng, 4) for _ in range(k)))
    elif nombre == "C6":  # cambio de régimen: varianza ×3 en un tercio contiguo
        x = [rng.gauss(0.0, 1.0) for _ in range(n)]
        ini = rng.randrange(0, n - n // 3)
        for i in range(ini, ini + n // 3):
            x[i] *= math.sqrt(3.0)
    else:
        raise ValueError(nombre)
    # Media POBLACIONAL 0 bajo H₀; la muestral NO se centra (si se centrara, T = 0 siempre y la calibración no mediría
    # nada). Solo se reescala: T es invariante a la escala, así que esto no altera el tamaño de la prueba.
    m = sum(x) / n
    s = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
    return [v / s * sd for v in x] if s > 0 else x
