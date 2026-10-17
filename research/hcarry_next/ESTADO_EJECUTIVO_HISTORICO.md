# H-CARRY: estado ejecutivo y recomendación (2026-10-16, 21:00 UTC)

## Recomendación: **4. Detener la línea de investigación**, con un criterio explícito de reapertura

La evidencia no justifica seguir desarrollando H-CARRY tal como está definido: carry BTCUSDT spot/perpetuo en Binance, ρ = 1, y reglas de entrada y salida por funding.
- **No hay nada que optimizar en las reglas.** Ni con conocimiento perfecto del futuro, una regla de salida supera al carry permanente en más de 0–0,17 pp/año. Alternar entre carry y efectivo agrega como mucho 0,4–1,0 pp/año.
- **El carry ya no supera al efectivo.** Rindió un 3,76 % en el test (2024-02 → 2026-05), frente a un 4,3 % de la letra del Tesoro, y prácticamente 0 % en 2026.
- **La causa es estructural y de todo el mercado.** El funding de BTC, ETH y SOL se comprimió desde 2022, no por un detalle de diseño.

**Criterio de reapertura** (seguimiento prospectivo, sin desarrollo):
- **Condición:** que el funding medio de 90 días de BTCUSDT supere el **12 % anual** sobre el nocional. Es el nivel aproximado para batir al efectivo por ≥ 2 pp con ρ = 1 y el T-bill en torno al 4 %.
- **Entonces:**
  1. prerregistrar una prueba prospectiva en papel de rev. 5 frente a efectivo remunerado;
  2. no reutilizar ninguna ventana histórica ya consumida.

**Qué haría cambiar esta recomendación:** un régimen sostenido de funding alto, como en 2021 o en 2024-T1 (22 %). O una fuente de rendimiento no estudiada aquí: estructura con colateral spot o carry entre exchanges. Cada una necesitaría su propia hipótesis, datos y prueba independiente.

## Qué se completó hoy
1. **Acceso oficial verificado** (DNS, TLS, HTTP 200, checksum).
2. **Descarga reanudable y verificada:** 412 archivos oficiales. Datos **aptos** según C1–C6, tras corregir 4 defectos reales del pipeline antes de simular (`REGISTRO_DEFECTOS.md`).
3. **Diagnóstico económico solo en desarrollo:** persistencia de 0,72; techo de las reglas de salida de 0,17 pp/año.
4. **Test prerregistrado ejecutado UNA vez** (20:47 UTC; cerrojo global):
   - **P1, UmbralFunding frente a rev. 5: HIPÓTESIS NO RESPALDADA.** −264 USDT; P(> 0) = 0; pierde en los 8 escenarios y también en validación y desarrollo.
   - **P2, carry de rev. 5: EVIDENCIA INSUFICIENTE.** CAGR del 3,76 %, por debajo del 5 % prerregistrado; 3,55 % con costes ×2.
5. **Análisis posterior al test, exploratorio:** compresión del funding en todo el mercado; el marco con efectivo a 0 % sesga P1; techo de la alternancia carry ↔ efectivo.

## Qué es histórico y qué no

| Resultado | Categoría |
|---|---|
| P1 y P2, tablas de desarrollo, validación y test, y sensibilidades | **Histórico verificado** (protocolo prerregistrado) |
| Diagnóstico y techo de salidas en desarrollo (antes del test) | Histórico verificado, análisis complementario |
| Funding por año, ETH y SOL, efectivo remunerado y techo de alternancia | **Exploratorio posterior al test**, no independiente |
| Ensayos y características de la fase anterior | **Sintéticos** |
| Prospectivo y real | **Ninguno** |

## Estado de las hipótesis
- **Descartadas:**
  - UmbralFunding como mejora de rev. 5;
  - toda la familia de reglas de salida por funding, UmbralPrima incluida;
  - cambiar a ETH o SOL (también comprimidos).
- **Vivas, pero sin respaldo:** el carry permanente de rev. 5 como inversión. Rentabilidad positiva, pero sin exceso sobre el efectivo desde 2022 y con un riesgo de cola de contraparte no modelado.
- **No evaluadas, porque el motor no lo permite con fiabilidad:**
  - apalancamiento o colateral spot: escala la rentabilidad y el riesgo de funding en la misma proporción, sin crear ventaja;
  - riesgo de liquidación dentro de la hora.

## Qué impide una conclusión más fuerte
- Una sola ventana de test (28 meses), ya consumida.
- El período reservado (2026-06 → 2026-10-13) dura solo unos 4,4 meses y requiere autorización.
- El rendimiento realizable del efectivo en el exchange no tiene serie verificable.

## Preservación
- **Registro del test:** enviado como `hcarry_test_historico_2026-10-16.zip` (SHA-256 `729fe86b…`).
- **Proyecto completo:** en `research/hcarry_next/`, **sin commit**. La instrucción vigente exige autorización explícita para commit y push.
- **Datos:** reproducibles con `REPRODUCIR.md`. Los hashes de cada archivo están en el manifiesto.

## Siguiente paso
Ninguno de desarrollo. Si autorizás el commit y el push, los hago para preservar todo en la rama. El seguimiento del criterio de reapertura puede hacerse a mano con los mismos comandos de descarga.
