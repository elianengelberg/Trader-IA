# Trader-IA · tendencia_btc

Línea de investigación posterior a H-CARRY (cerrado en `../hcarry_next/INFORME_CIERRE_HCARRY.md`): estrategias distintas del carry sobre BTCUSDT spot, **solo simulación histórica**.

**Estado (2026-10-17):** el cribado y las puertas de desarrollo están cerrados. Ninguna candidata pasó a validación ni a test, que siguen sin usar. Ver `INFORME_NUEVA_LINEA.md`.

| Ruta | Contenido |
|---|---|
| `FAMILIAS_ESTRATEGIA.md` | Familias consideradas, reglas de decisión fijadas antes de cada cálculo y sus resultados |
| `INFORME_NUEVA_LINEA.md` | Informe: datos, selección, implementación, resultados, sensibilidad, estrés, decisión y siguiente paso |
| `src/tendencia/` | Datos diarios oficiales, señales, backtest long/flat, métricas, estadística |
| `tests/` | 6 pruebas (sin look-ahead, costes exactos, benchmarks, formato oficial) |
| `experimentos/` | Scripts y salidas JSON (todo en desarrollo) |
| `datos/` | Velas diarias oficiales de BTCUSDT y ETHUSDT con manifiesto y `.CHECKSUM` |

Reutiliza `../hcarry_next/src` (pipeline de datos y bootstrap) sin modificarlo. Comandos en `INFORME_NUEVA_LINEA.md` §8.
