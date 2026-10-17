# Registro de experimentos: validación histórica (2026-10-16)

## Referencias comunes
- **Código:** huella `8a7cb0424b28…` (`hcarry.lab.experimento.huella_codigo`), salvo que se indique otra.
- **Prerregistro:** `90642cd1…`, con tres adendas, en `PRERREGISTRO_VALIDACION_HISTORICA.md`.
- **Datos BTCUSDT:** manifiesto `8bdabde706bffadc…` (412 archivos oficiales).
- **Ejecuciones con registro del laboratorio** (configuración, hash y métricas de cada corrida):
  - `desarrollo/registro.jsonl`: 19 ejecuciones;
  - `resultados/historico/datos_8bdabde706bf/registro.jsonl`: 23 ejecuciones, de las cuales 19 son de test.
- **Semilla del bootstrap:** 20261016 en todos los casos.

| ID | Fecha (UTC) | Hipótesis o pregunta | Categoría | Script y salida | Parámetros | Resultado | Decisión |
|---|---|---|---|---|---|---|---|
| HX-01 | 20:32 | ¿Funciona el acceso oficial y están completos los datos? | Datos | `hcarry descargar`; `datos/descarga.log` | BTCUSDT, 5 series, 2019-10 → 2026-05 | 388 archivos verificados; 12 no publicados (futuros 2019-Q4) | Inicio común en 2020-01 |
| HX-02 | 20:35–20:44 | ¿Pasa la muestra C1–C6? | Datos | `hcarry calidad`; `datos_oficiales/calidad.md` | Umbrales prerregistrados | Primero aborta (velas irregulares, formato µs); tras las correcciones, D1 por volumen; finalmente apta | Adenda 2; muestra aceptada |
| HX-03 | 20:45 | Diagnóstico del mercado y de las políticas | Histórico, solo desarrollo | `diagnostico_desarrollo.py`; `desarrollo/diagnostico.json` | Prerregistrados; 8 sensibilidades | Funding del 17,3 % APR; persistencia de 0,72; umbral −1,4 pp/año frente a rev. 5 (P = 0,001) | Seguir con E1 y E3 |
| HX-04 | 20:46 | E1: ¿de dónde sale la diferencia? E3: ¿cuál es el techo de las reglas de salida? | Histórico, solo desarrollo | `investigacion_desarrollo.py`; `desarrollo/investigacion.json` | Coste de ida y vuelta de 50 bps (×0,5, ×1 y ×2) | E1: −516 funding perdido, +234 evitado, −241 costes. E3: techo de 0,17 pp/año | No sumar candidatos al test (adenda 3); predicción P1 = no respaldada |
| **HX-05** | **20:47** | **P1 y P2 prerregistradas (test de uso único)** | **Histórico verificado** | `hcarry historico`; `resultados/historico/datos_8bdabde706bf/` | Prerregistro sin cambios; 19 configuraciones | **P1: NO RESPALDADA** (−264; P = 0). **P2: INSUFICIENTE** (3,76 % < 5 %) | Test consumido (`TEST_CONSUMIDO.json`) |
| HX-06 | 20:48 | ¿Cómo evolucionó el funding y cuál es el techo de las salidas en validación y test? | Exploratorio post-test | `post_test_exploratorio.py`; `post_test/exploratorio.json` | — | Compresión 2022–2026; techo de 0,00 pp en validación y test; funding necesario ≥ 9,2 % | Línea de salidas descartada |
| HX-07 | 20:50 | ¿Cambia P1 si el efectivo rinde el T-bill? | Exploratorio post-test (supuesto externo) | `post_test_efectivo_remunerado.py`; `post_test/efectivo_remunerado.json` | DTB3, recorte de 0 y 1 pp; con o sin margen | umbral > rev. 5 en validación y test, ≈ efectivo; techo de alternancia de 0,4–1,0 pp | Documentado; no altera P1 |
| HX-08 | 20:52 | ¿Es la compresión específica de BTC? | Exploratorio post-test | Descarga del funding de ETH y SOL; `post_test/funding_otros_simbolos.json` | Manifiestos ETH `7ca2ccb2…`, SOL `8aeedb35…` | ETH y SOL se comprimen igual; SOL −38 % en 2022 | El cambio de activo no rescata el carry |
| HX-09 | 20:53 | Métricas de riesgo complementarias | Exploratorio post-test | `post_test/metricas_completas.json` | — | Caídas de 0,25–2,15 %; ninguna liquidación; concentración del 41–73 % | Riesgo de cola no capturado; documentado |

**Candidatos probados en total:** 2 políticas prerregistradas (rev. 5 y umbral), más el efectivo como control.
- No se buscaron parámetros con datos reales.
- La selección múltiple es **nula** para P1 y P2.
- Los análisis HX-06 a HX-09 son posteriores al test y no pueden usarse como evidencia independiente.
