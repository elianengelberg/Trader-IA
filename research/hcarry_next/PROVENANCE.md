# Procedencia de H-CARRY Next

**Ningún archivo de `src/` es código original de H-CARRY rev. 5.** El código original se perdió cuando se recicló el contenedor; no se encontró ninguna copia (búsqueda documentada el 2026-10-16 en el disco, el historial de la sesión, GitHub, artefactos, otras sesiones y Google Drive; Gmail no estaba autorizado). Lo que hay aquí se divide en tres clases.

## 1. Recuperado (bytes originales, solo lectura) — `recuperado/`

Nueve archivos extraídos literalmente del historial de la sesión, más el ZIP de la recuperación (`5783517c…`). Hashes en `recuperado/SHA256SUMS`; los comprueba `tests/test_recuperado.py`.

| Archivo | Estado | Uso en H-CARRY Next |
|---|---|---|
| `h_carry/prechequeo_exchangeinfo.py` | **Verificado** (SHA-256 = referencia `17a336c1…`) | Ninguno: depende de módulos perdidos y consulta exchangeInfo (no autorizado) |
| `tests/test_hc_decisiones.py` | Recuperado, sin hash de referencia | Especificación: sus casos a1, a1b, a2, c1, d1 y d1b se **portaron** (reescritos) a las pruebas nuevas |
| `h_carry/ADENDA_DECISIONES_HCARRY_REV5.md` | Recuperado, sin hash de referencia | Especificación de funding, filtros, liquidación y amenazas |
| `h_carry/archivo_rev5/protocolo_rev5_decisiones.py.txt` | Recuperado, sin hash de referencia | Especificación: estructura y textos del borrador rev. 5 |
| `h_carry/archivo_rev5/README.md` | Recuperado, sin hash de referencia | Historia del borrador |
| `VERSIONES_INTERMEDIAS_NO_FINALES/*` (2) | Versiones intermedias, **no finales** | Contexto |
| `LEEME_RECUPERACION.md`, `PROCEDENCIA.json` | Notas de la recuperación | Procedencia |

## 2. Reconstruido (reimplementado a partir de la especificación conocida)

Fuentes de la especificación: los archivos recuperados, el resumen de la sesión anterior (conservado en el historial de la conversación) y las salidas documentadas de rev. 5 (ejemplo sintético de su plantilla de informe).

| Componente | Módulo | Qué reproduce de rev. 5 | Evidencia de equivalencia |
|---|---|---|---|
| Cuentas spot/futuros, equity ejecutable, ρ, precio de liquidación, transferible | `model/cartera.py` | Fórmulas del expediente rev. 5 | `test_apertura_reproduce_rev5_a_mano`: W = 10 000 − q·P − q·150, distancia a la liquidación 0,985675 |
| Costes por pata sobre el nocional a precio de apertura (S12) | `model/costes.py` | 10+5 bps spot, 5+5 bps perp | Costes 24,90 del ejemplo de la plantilla |
| Funding antes de operar (no se cobra en la hora de entrada; sí en la de salida) | `model/motor.py` | Convención rev. 5 | 8 de 9 liquidaciones cobradas, funding 39,84 |
| Reequilibrio por banda (0,5; 1,5) a ρ = 1, salida en la apertura de la última hora | `model/motor.py`, `estrategias.Siempre` | Regla de rev. 5 | Equity final 10 014,94 exacto |
| Regla R0 (ampliación inviable → detener) | `ParamsMotor(al_inviable="detener")` | R0/E1 | `test_regla_r0_detiene…` |
| D1 con días fijos (n − 1)/24; D2; D3 P95 rango más cercano; D4 con el final | `metricas.py` | Criterios congelados | CAGR 0,2022473335 y caída 0,001245 exactos; d1, d1b |
| Validación del calendario de funding (A2, A2b, A4, A7, A8, P2) | `data/validacion.py` | Catálogo de rev. 5 (subconjunto) | Pruebas a1, a1b, a2 portadas (±22,41 USDT) |
| Período reservado bloqueado por código | `conventions.py` | Restricción del proyecto | `test_periodo_reservado…` |

Diferencias deliberadas con rev. 5 (documentadas en `DECISIONS.md`): aritmética en coma flotante con cantidades en lotes enteros (rev. 5 usaba `Fraction`); sin ledger encadenado ni autorizaciones en dos fases (sustituidos por el registro de experimentos con huellas y la guarda del test); la descarga usa los archivos mensuales oficiales de data.binance.vision con checksum en lugar de la API REST.

## 3. Nuevo o mejorado en H-CARRY Next

- **Motor generalizado:** ρ objetivo y banda configurables (variantes apalancadas), escala de despliegue, tolerancia de tamaño, liquidación por salto de apertura y fondo de seguros, venta del spot descubierto y enfriamiento, estrés de retraso y de pata adversa, impacto de mercado ∝ √(nocional/volumen), filtros con división por máximos, horas rellenadas sin decisiones.
- **Conciliación independiente** del equity en cada cierre y descomposición precio/funding/costes (`model/conciliacion.py`).
- **Políticas alternativas:** `UmbralFunding` (histéresis), `UmbralPrima` (predicción del funding con la fórmula de Binance a partir de la prima observada), `RhoPorVolatilidad`, `EscalaPorVolatilidad`.
- **Vista sin look-ahead** y su prueba de perturbación del futuro.
- **Métricas** de capital comprometido, utilización, rotación, duración, base adversa, por año y comparador.
- **Laboratorio:** registro JSONL con huellas, divisiones fijas, test prerregistrado y de uso único, bootstrap pareado por bloques, protocolo desarrollo → validación → test con estrés y regla de decisión fija, **mundos nulos** para medir falsos descubrimientos.
- **Datos:** cargador de data.binance.vision (checksums, ms/µs, con y sin cabecera, huecos, índice de prima opcional) y generador sintético con la fórmula de funding de Binance y una variante «bajista suave» para análisis de sensibilidad.
- **Análisis** de la estructura de capital (`analisis.py`).
