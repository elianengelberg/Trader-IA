# La regla T, sin cambios, fuera de muestra (2022-01 → 2026-05): resultado

> **Corrección (2026-10-17, revisión crítica):** los resultados, el prerregistro, el script y la decisión **no cambian**. Se corrigen afirmaciones derivadas sobre la caída respecto de desarrollo, la robustez, la comparación con buy and hold, el resto de las candidatas y la potencia del papel. Detalle y cálculos en `REVISION_CRITICA_FUERA_DE_MUESTRA_T.md` y `experimentos/revision_fuera_de_muestra_T.py`.

**Categoría:** histórico verificado (data.binance.vision, checksums), **fuera de muestra para T**. **No es prospectivo.** No modifica el experimento en papel: sus reglas, código, hashes, fechas y criterios siguen intactos.

**Procedencia.**
- Prerregistro `PRERREGISTRO_FUERA_DE_MUESTRA_T.md` (`94a16556…`), escrito antes de calcular.
- Script `experimentos/fuera_de_muestra_T.py` (`941b6e11…`), de una sola ejecución.
- Resultado `experimentos/fuera_de_muestra_T.json`.
- Código congelado `73b22f3e…`; datos `5a0805a7…` y `3998305b…`, ya en disco, sin descargas nuevas.
- Antes de la ejecución, el script se ensayó sobre la ventana de **desarrollo** y reprodujo exactamente las cifras publicadas (BTC +14,2 %/año, P = 0,842).
- Se ejecutó una sola vez, el 2026-10-17 a las 19:27 UTC; el congelado es local, sin commit.

## Decisión prerregistrada: **EVIDENCIA INSUFICIENTE**
| Exceso de timing frente a la estática con la misma exposición | Exceso anual | IC90 | P(> 0) |
|---|---|---|---|
| **Conjunto (BTC + ETH), primario** | **+7,0 %** | −8,8 % / +22,9 % | **0,755** |
| BTC | +9,1 % | −6,7 % / +24,9 % | 0,836 |
| ETH | +5,0 % | −13,4 % / +23,7 % | 0,649 |

- Para «respaldada» hacían falta P ≥ 0,95 en el conjunto y P ≥ 0,90 en BTC; para «no respaldada», P < 0,10.
- El nulo por desplazamiento circular en BTC queda en el percentil 0,869.
- **Consecuencia declarada de antemano:** no se hace más trabajo histórico con T sobre estos datos.

## Lo que muestra (descriptivo)
- **Signo consistente pero efecto menor:** el exceso es positivo en ambos activos y en ambas subventanas (2022–2023: conjunto +7,0 %; 2024 → 2026-05: +5,9 %).
- **Bajo estrés, la estimación puntual sigue positiva** (costes ×2, +4,4 %; costes ×3, +1,7 %; un día de retraso, +7,7 %), pero **ninguna variante es significativa**: P = 0,66 con costes ×2 y 0,79 con retraso. Eso no prueba robustez; solo que el signo no depende de esos supuestos.
- **La estimación es menor que en desarrollo, pero la diferencia no es significativa:** el conjunto cae de +19,4 % a +7,0 % (diferencia 12,3 pp, error 18,5 pp, z = 0,67). En ETH, de +24,6 % a +5,0 % (z = 0,82). Que la cifra de desarrollo de ETH quede fuera del IC90 fuera de muestra no compara bien dos estimaciones con error. Una inflación por selección es **posible**, pero estos datos no la distinguen del azar.

**Frente a buy and hold** (netos de costes, 2022-01 → 2026-05):

| | CAGR | Sharpe | Caída máx. | Exposición | Operaciones (costes/año) |
|---|---|---|---|---|---|
| BTC T | **18,8 %** | 0,71 | **31 %** | 0,54 | 227 (3,9 pp) |
| BTC estática, misma exposición | 9,4 % | 0,46 | 43 % | 0,54 | — |
| BTC buy and hold | 11,1 % | 0,46 | 67 % | 1,00 | 1 |
| ETH T | 3,0 % | 0,26 | 41 % | 0,48 | 230 (2,7 pp) |
| ETH buy and hold | −12,9 % | 0,15 | 74 % | 1,00 | 1 |
| Efectivo (USDT al 0 %) | 0 % | — | 0 % | 0 | 0 |

- **En 2022**, la menor exposición media explica la mayor parte de la diferencia frente a buy and hold. En BTC, buy and hold −64 %, estática −40 %, T −30 %; en ETH, −68 %, −36 % y −29 %.
- **En todo el período**, en cambio, la ventaja de CAGR de BTC sobre buy and hold (+7,7 pp) viene del **timing**: la estática −1,7 pp y el timing +9,4 pp. En ETH viene sobre todo de la exposición media: +12,3 pp de la estática y +3,5 pp del timing.
- La reducción de la caída máxima de BTC (67 → 31 %) viene en parte de la exposición (→ 43 %) y en parte del timing.
- El timing (frente a la estática) es justamente la parte que no alcanza significación.
- **Desarrollo + fuera de muestra** (2018-02 → 2026-05; solo descriptivo, no es una prueba independiente): conjunto +14,2 %/año, P = 0,938. Ni con 8,3 años se llega a 0,95.

## Qué implica para la decisión
- **H-CARRY** quedó cerrada (evidencia insuficiente; su carry rindió +3,76 % en test, por debajo de su comparador del 5 %) y **V** se descartó. **T es la única candidata cuya estimación fuera de muestra supera a su benchmark**, pero su ventaja **no está demostrada**. La mejor estimación es +7 %/año, con un IC90 de −8,8 % a +22,9 %; cualquier cifra más precisa sería una suposición.
- **Si el efecto verdadero fuera de ≈ +7 %/año**, el experimento en papel difícilmente lo confirmaría en un plazo razonable. Para que P ≥ 0,95 fuera lo esperable harían falta de 16 a 52 años (y de 37 a 120 para un 80 % de potencia), según cómo se estime la variabilidad.
  - A los 24 meses, la probabilidad de «ventaja respaldada» sería de ≈ 8 a 14 %, y la de «detener» a los 12 meses, de ≈ 5 a 8 %.
  - **No es una cota:** si el efecto fuera el de desarrollo, esa probabilidad sería de ≈ 22 a 48 %. La cifra anterior («como mucho ≈ 9 %») suponía un efecto exacto de +7 % y la variabilidad de desarrollo.
  - Sigue siendo útil como control prospectivo y de operación, **sin cambios**. Lo más probable es que termine en «insuficiente».
- **La restricción es la potencia, no la regla.** Con un solo mercado cripto, más años de datos no alcanzan. La única manera de ganar potencia sin minería de datos es **aplicar T sin cambios a muchos mercados independientes** (índices, bonos, materias primas, divisas), como en la literatura de momentum de series temporales. Eso exige una fuente de datos nueva y un prerregistro propio: es una decisión tuya.
