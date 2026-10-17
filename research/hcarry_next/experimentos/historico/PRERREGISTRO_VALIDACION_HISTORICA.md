# Prerregistro: validación histórica de rev. 5 frente a UmbralFunding

- **Fecha:** 2026-10-16, antes de disponer de ningún dato histórico real.
- **SHA-256 del prerregistro:** `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd`. Es el hash de `PRERREGISTRO.json`, idéntico a `hcarry.lab.historico.PRERREGISTRO`.
- **Huella del código al prerregistrar:** `2e35b68ff663b93698a3b38f78c17321e85bfe4af9885bfd5c5403c006220b00`.

Cambiar cualquier punto después de ver datos convierte el análisis en una hipótesis nueva, que exige datos nuevos: el período reservado, solo con autorización, o una prueba prospectiva.

## Preguntas

- **P1.** ¿UmbralFunding mejora de forma neta y robusta al carry permanente de rev. 5, con los mismos datos, costes y restricciones?
- **P2.** ¿El carry permanente de rev. 5 tiene una ventaja económica neta?

## Datos y filtros de calidad (`hcarry.data.calidad`)

- **Fuente:** solo data.binance.vision o una copia suya verificable. Procedencia `historico_oficial`: cada zip con su `.CHECKSUM` oficial y sin la marca de archivo sintético.
- **Instrumento y series:** BTCUSDT; spot, perpetuo, mark y funding en 1 h; el índice de prima es opcional.
- **Ventana:** desde el primer mes común de las series requeridas (nunca antes de 2019-10) hasta 2026-06-01. El período reservado es inaccesible por código.
- **Filtros. Si falla alguno, no se simula nada y la conclusión es EVIDENCIA INSUFICIENTE:**
  - C1: checksums oficiales presentes y coincidentes.
  - C2: ningún mes requerido ausente.
  - C3: horas rellenadas ≤ 0,5 % y ninguna racha > 24 h.
  - C4: funding sin A2, A2b, A4, A7 ni A8 (política estricta de rev. 5).
  - C5: sin A6 ni P2; mediana de |F/S − 1| ≤ 0,2 %; p99 de |M/F − 1| ≤ 1 %.
  - C6: fuera del período reservado.

## Diseño

| Elemento | Valor fijado |
|---|---|
| Divisiones | Desarrollo 2019-10 → 2022-12 · Validación 2023-01 → 2024-01 · Test 2024-02 → 2026-05 (la ventana prerregistrada de rev. 5) |
| rev. 5 | `Siempre`: ρ = 1, banda (0,5; 1,5). Regla «omitir»; la variante R0 «detener» solo informa D1–D4 |
| UmbralFunding | Ventana de 21 eventos, entrada 10 % anual, salida 3 %, permanencia de 72 h, ρ = 1, misma banda. **Fijado a priori, sin optimizar con datos reales** |
| Capital y margen | 10 000 USDT; margen de mantenimiento del 1 %; apalancamiento máximo 2 para el transferible |
| Costes base | Spot 10 + 5 bps; perpetuo 5 + 5 bps, sobre el nocional (comisión de tomador minorista + slippage, como en rev. 5) |
| Sensibilidad (en test) | Costes ×0,5, ×2 y ×3; retraso de 1 h y de 3 h; pata del perpetuo adversa; funding × 0,75; nocional mínimo del perpetuo de 5 USDT |
| Diagnóstico previo (solo en desarrollo) | Correlación entre medias de funding de 7 días consecutivos y fracción de eventos negativos. **Predicción:** si la correlación es < 0,2, UmbralFunding no aportará |
| Estadística | Bootstrap circular por bloques de 30 días, 2 000 remuestreos, semilla 20261016, sobre las diferencias diarias (umbral − rev. 5) |

## Criterios de conclusión

**P1 — VENTAJA RESPALDADA.** Hace falta que se cumpla todo esto:
- datos históricos con calidad apta;
- en test:
  - PnL neto de umbral mayor que el de rev. 5;
  - P(diferencia diaria media > 0) ≥ 0,95;
  - caída de umbral ≤ caída de rev. 5 + 5 pp, sin liquidaciones;
  - umbral sigue por encima de rev. 5 con costes ×2, con pata adversa y con retraso de 3 h;
- en validación, umbral ≥ rev. 5.

**P1 — HIPÓTESIS NO RESPALDADA.** Datos aptos y, en test, PnL de umbral ≤ rev. 5 o P < 0,5.

**P1 — EVIDENCIA INSUFICIENTE.** En cualquier otro caso:
- datos no aptos o no históricos;
- 0,5 ≤ P < 0,95;
- falla solo algún estrés o la validación.

**P2 — carry de rev. 5:**
- **VENTAJA RESPALDADA** si en test el CAGR neto es > 5 % (el comparador) y sigue > 0 con costes ×2;
- **NO RESPALDADA** si el CAGR neto es ≤ 0;
- **EVIDENCIA INSUFICIENTE** si no.

## Separación de categorías

El evaluador decide la categoría a partir del manifiesto de los datos, y no es configurable:
- `resultados/historico/` solo con procedencia `historico_oficial`;
- `resultados/sintetico/` para cualquier ensayo con datos fabricados. Sus informes llevan el aviso «SINTÉTICO: no es evidencia económica» y su conclusión es siempre EVIDENCIA INSUFICIENTE.

**Evidencia prospectiva:** no existe. Ningún informe la representa.

## Adenda (2026-10-16, antes de disponer de datos históricos): cambios de código posteriores al prerregistro

`PRERREGISTRO.json` no cambió; su hash sigue siendo `90642cd1…`. El código sí cambió después de `2e35b68f…`, solo en esto:

1. `importar` escribía siempre `via: "copia aportada por el usuario"`, también para archivos fabricados. Ahora describe la importación sin atribuirla a nadie. Huella intermedia: `4e31b921…`.
2. Lint: paréntesis en concatenaciones implícitas, `itertools.pairwise` y valores por defecto `None` en `amortizacion` y `generar`. Huella actual: `68ddc304…`.

**Verificación:** con el código actual, el ensayo sintético (semilla 101) reproduce exactamente el original de `2e35b68f…` en el diagnóstico previo, el desarrollo, la validación, el test, la sensibilidad y el bootstrap. Ningún cambio toca un cálculo ni un criterio. La evaluación histórica registrará la huella que tenga el código cuando se ejecute. Cualquier diferencia con `68ddc304…` debe quedar justificada en otra adenda **antes** de ver los datos.

## Adenda 2 (2026-10-16, ~21:00 UTC): datos descargados, antes de cualquier simulación con ellos

`PRERREGISTRO.json` no cambió (hash canónico `90642cd1…`). Ningún parámetro, coste, sensibilidad ni criterio cambió. Hasta ahora no corrió ninguna simulación con datos reales y no leí ninguna estadística económica del período de test. Del informe de calidad solo leí veredictos e incidencias; las cifras agregadas de funding quedaron guardadas sin leer.

### Hechos observados en los datos oficiales (calidad, no economía)
- **Archivos no publicados (404):** perpetuo, mark, funding y prima de 2019-10 a 2019-12. El inicio común pasa a ser **2020-01**, por la regla prerregistrada del primer mes común.
- **Spot:**
  - 8 velas irregulares por paradas del exchange: duraciones de 35,5, 21,8, −12,7 (cierre anterior a la apertura), 40,9, 1,0, 60,0−, 59,9 y 39,7 min;
  - 35 h sin vela, en huecos de 1 a 5 h.
- **Mark:** a los archivos mensuales les faltan 192 h (incluidas 96 seguidas del 2021-07-24 al 27). Los archivos **diarios oficiales** del mismo emisor las contienen, cada uno con su `.CHECKSUM`.
- **Formato:** en el spot desde 2025, el cierre de vela es apertura + 1 h − **1 µs**. El lector esperaba −1 ms y abortaba.

### Decisiones (código nuevo con pruebas; huella `8a7cb042…`)
1. **Cerrojo global del test** (`TEST_CONSUMIDO.json`), independiente del manifiesto. Una descarga nueva ya no puede repetir el test.
2. **Lector de microsegundos** corregido. El fabricante sintético emula ahora el formato real.
3. **Velas irregulares:** se excluyen y su hora queda sin datos. Es decir, son horas rellenadas planas en las que el motor no decide, y cuentan para C3. Es el trato más conservador: no se inventa nada y no se usa una vela parcial.
4. **Archivos diarios oficiales:** completan **solo** horas ausentes de los mensuales de la misma serie. Si una hora está en ambos archivos y sus precios difieren, la discrepancia bloquea (D1). Fuente y series no cambian, porque el prerregistro dice «solo data.binance.vision», no «solo archivos mensuales».
5. **D1 limitado a precios** (decisión tomada **después** de observar la única discrepancia):
   - la discrepancia: spot del 2021-12-24 a las 03:00 UTC, OHLC idénticos y volumen en USDT +1,85 % en el diario;
   - el panel usa el valor mensual en esa hora, así que la decisión no altera ningún dato simulado;
   - D1 lo introduje en esta misma adenda: no es un filtro del prerregistro.

**Lectura estricta, para que conste:**
- solo con archivos mensuales, la muestra **no** habría sido apta (C3: racha de 96 h > 24 h);
- con los diarios y D1 sobre todos los campos, tampoco (una diferencia de volumen).

Con estas decisiones, **C1–C6 pasan:**
- manifiesto `8bdabde706bffadc…`;
- 412 archivos (388 mensuales y 24 diarios);
- ventana 2020-01-01 → 2026-06-01, con 56 232 h, 39 rellenadas y una racha máxima de 6 h;
- 7 029 eventos de funding, todos cada 8 h.

**Verificación:** el ensayo sintético (semilla 101) se reproduce bit a bit con el código actual. Las decisiones afectan a dev y validación (huecos del mark, velas irregulares de 2020–2023), no a la ventana de test, salvo por el cerrojo.

### Discrepancia entre la misión del 2026-10-16 y el prerregistro
La misión describe 2019-10 → 2026-05 como «desarrollo» y 2026-06 en adelante como «test independiente». El prerregistro, en cambio, fija:
- **test de uso único: 2024-02 → 2026-05**;
- el período 2026-06-01 → 2026-10-13 como **reservado**, inaccesible salvo autorización.

**Resolución, sin cambiar el protocolo:**
- se aplica el prerregistro;
- el diagnóstico y el desarrollo de candidatos nuevos usan **solo desarrollo** (2020-01 → 2022-12), y la validación (2023-01 → 2024-01) sirve para confirmarlos;
- la ventana de test sigue a ciegas hasta su ejecución única;
- el período reservado no se descarga ni se mira.

Este orden conserva las dos lecturas: tras consumir el test, 2024-02 → 2026-05 pasa a ser desarrollo, y el período reservado (≈ 4,4 meses) sigue intacto para una hipótesis nueva, con autorización.

## Adenda 3 (2026-10-16, antes de ejecutar el test): resultados de desarrollo y decisión de no sumar candidatos

Todo lo de esta adenda se calculó **solo con desarrollo** (2020-01 → 2022-12): `experimentos/historico/diagnostico_desarrollo.py` e `investigacion_desarrollo.py`. Huella `8a7cb042…`, manifiesto `8bdabde7…`. Ni la validación ni el test se miraron fuera del evaluador.

### Diagnóstico previo prerregistrado
Correlación de medias de 7 días consecutivos: **0,72**, con un 14,6 % de eventos negativos. Según la predicción escrita, UmbralFunding *podría* aportar.

### Desarrollo con parámetros prerregistrados (análisis complementario)

| | rev. 5 | UmbralFunding |
|---|---|---|
| CAGR | 9,48 % | 7,95 % |
| Diferencia (bootstrap) | | −1,4 pp/año, IC90 [−2,1; −0,7], P(> 0) = 0,001 |
| Sensibilidades | | umbral pierde en las 8 |

### E1 · Atribución (umbral − rev. 5 = −544 USDT)
| Concepto | USDT |
|---|---|
| Funding positivo perdido estando fuera | −516 |
| Funding negativo evitado | +234 |
| Costes extra | −241 |

### E3 · Techo de cualquier regla de salida
Un oráculo con conocimiento perfecto del funding futuro, pagando 50 bps del nocional por ida y vuelta, gana **0,17 pp/año** sobre el equity: 0,27 con costes ×0,5 y 0,09 con costes ×2. Los episodios negativos son cortos: mediana de 8 h, solo 3 de más de 3 días.

### Decisión
**No se prerregistran candidatos nuevos** para la ventana de test:
- las reglas de salida, como UmbralFunding, sus variantes o UmbralPrima, tienen un techo despreciable en desarrollo;
- variar el tamaño según el funding esperado es apalancamiento, y su riesgo principal (liquidación dentro de la hora en subidas bruscas, tramos de margen) no lo modela el motor con fiabilidad.

La ventana de test se usa una sola vez, para el protocolo original.

**Predicción escrita antes del test:** P1 = HIPÓTESIS NO RESPALDADA (UmbralFunding ≤ rev. 5 en test). Sobre P2 no hago predicción.
