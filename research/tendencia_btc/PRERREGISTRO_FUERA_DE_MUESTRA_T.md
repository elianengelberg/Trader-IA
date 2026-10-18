# Prerregistro: la regla T, sin cambios, fuera de muestra (2026-10-17, antes de calcular)

**Categoría del resultado:** histórico verificado, **fuera de muestra para T**. No es prospectivo ni sustituye al experimento en papel.

## Qué se evalúa (todo congelado de antemano)
- **Regla T exactamente como está congelada:** `src/tendencia/*.py`, huella `73b22f3e3a8f21513d5533fb11a7553becae30b87c8736fb6880bccc36c11d2b`.
  - Señal `tsmom`: ventanas {30, 90, 180} días; exposición 0, ⅓, ⅔ o 1.
  - Decisión con el cierre de d y ejecución en la apertura de d + 1.
  - Costes de 10 + 5 bps por lado (comisión taker estándar de Binance spot y slippage); efectivo al 0 %; sin apalancamiento.
  - **Nada se ajusta.**
- **Métrica:** la misma del experimento en papel, `tendencia.papel._exceso`: exceso diario de T frente a la estática con su misma exposición media.
  - Primaria: **media de BTC y ETH** (exceso conjunto), anualizada × 365.
- **Inferencia:** `bootstrap_media` por bloques de 20 días, 2 000 remuestreos, semilla 20261017, como en el papel.
- **Datos:** `datos/BTCUSDT` y `datos/ETHUSDT`.
  - Velas diarias oficiales de data.binance.vision, 106 + 106 archivos mensuales verificados contra su `.CHECKSUM`; manifiestos `5a0805a7…` y `3998305b…`.
  - Ya están en disco: **no se descarga nada.**
- **Ventana fuera de muestra:** [2022-01-01, 2026-06-01), es decir 1 612 días, 4,42 años.
  - Nunca se usó para la línea de tendencia (`INFORME_NUEVA_LINEA.md`).
  - Termina antes del período reservado de H-CARRY (2026-06-01 → 2026-10-13), que no se lee.
  - Los cierres de desarrollo anteriores a 2022 solo sirven como historia de la señal.

## Decisión (una sola ejecución; mismos umbrales que el papel a 24 meses)
| Resultado | Condición |
|---|---|
| **RESPALDADA FUERA DE MUESTRA** | P(exceso conjunto > 0) ≥ 0,95, P(BTC > 0) ≥ 0,90 y exceso conjunto con costes ×2 > 0 |
| **NO RESPALDADA** | P(exceso conjunto > 0) < 0,10 |
| **EVIDENCIA INSUFICIENTE** | Cualquier otro caso |

**Consecuencias declaradas de antemano.** Son para la recomendación sobre qué investigar; **no cambian el experimento en papel**, cuyas reglas, código, hashes, fechas y criterios siguen intactos:
- **Respaldada:** T es la única candidata que merece seguir investigándose, sin cambiar la regla. El papel sigue igual.
- **No respaldada:** T se descarta como candidata para nuevo desarrollo. El papel sigue según su propio prerregistro; solo vos decidís si detenerlo.
- **Insuficiente:** no se hace más trabajo histórico con T. Solo el papel puede agregar evidencia.

**Potencia esperada.** Calculada solo con cifras de desarrollo (`papel/potencia.json`), con una aproximación normal y un error de 14,8 %/año con 4,42 años:
- con un efecto igual al de desarrollo (+19,4 %/año conjunto), P(alcanzar 0,95) ≈ **37 %**;
- con la mitad, ≈ **16 %**;
- con un efecto nulo, 5 %.
- La probabilidad de «no respaldada» es del 0,5 % con el efecto de desarrollo y del 10 % con un efecto nulo.
- **Lo más probable es «insuficiente», incluso si T funciona.** Un resultado así no refuta T.

## Análisis secundarios (descriptivos; no cambian la decisión)
- **Por activo:** BTC y ETH por separado.
- **Por subventana:** 2022–2023 y 2024-01 → 2026-05.
- **Estrés:** costes ×2 y ×3; retraso de ejecución de 1 día.
- **Métricas:** CAGR, volatilidad, Sharpe, caída máxima, exposición, operaciones y costes de T, de la estática, de buy and hold y del efectivo.
- **Nulo de BTC por desplazamiento circular**, como en desarrollo: 1 000 desplazamientos, semilla 20261017.
- **Replicación:** cociente entre la estimación fuera de muestra y la de desarrollo, y si la de desarrollo cae dentro del IC90 fuera de muestra.
- **Desarrollo + fuera de muestra** (2018-02-14 → 2026-05-31): solo descriptivo; no es una prueba independiente.

## Advertencias
- El diseñador conoce a grandes rasgos 2022–2026 (bajista en 2022, alcista en 2023–2024). La regla se fijó antes, con datos hasta 2021, y no se cambia.
- **El congelado es local:** no está autorizado hacer commit. El SHA-256 de este archivo queda registrado en el resultado, y el script se niega a correr si el resultado ya existe (una sola ejecución). La fecha no es verificable externamente hasta que se publique.
- Es un solo mercado (cripto spot) y una sola familia (tendencia): no se deduce nada sobre otras estrategias.
