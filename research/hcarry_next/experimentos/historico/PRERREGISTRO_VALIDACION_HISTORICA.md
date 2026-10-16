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
