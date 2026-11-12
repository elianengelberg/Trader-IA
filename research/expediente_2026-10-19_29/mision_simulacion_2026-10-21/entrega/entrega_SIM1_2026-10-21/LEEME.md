# Entrega SIM-1 (2026-10-21): motor corregido y simulación histórica real de Trader-IA

**Leer primero:** `INFORME_SIM1.md`. La decisión está en §0 y lo que te toca decidir, en §9.

| Ruta | Contenido |
|---|---|
| `INFORME_SIM1.md` | Informe final: defectos, datos, diseño, desarrollo, OOS, causas, mejoras y decisiones |
| `CRITERIO_SUFICIENCIA_TECNICA.md` | Criterio C1–C8 fijado antes de simular, con su evidencia |
| `prerregistro/PRERREGISTRO_SIM1.md`, `HUELLAS.txt` | Prerregistro. Huellas a las 20:41:41Z (antes de leer retornos) y Adenda 1 a las 21:59:47Z (antes de OOS) |
| `parche/` | `parche_motor_D1_D3.diff` contra `72ffae5` y la prueba de regresión `test_backtest_order_hygiene.py` |
| `codigo/` | `sim1.py` (DEV, y OOS una vez con candado), `sim1_comun.py`, `calidad_datos.py`, `verificacion_motor.py`, `paridad_e1.py`, `tablas_sim1.py`, `descargar_vision.sh`, `fijar_huellas.sh`, `correr_suite.sh`, `sonda_d3.py` y el ensayo sintético |
| `E1/` | `e1.py`, `e1_comun.py` y `requisitos_con_hash.txt` de E1, sin cambios: se reutilizan su configuración y su estadística |
| `evidencia/` | Línea base y suite corregida; regresión antes y después; ruff y mypy; paridad con E1; verificación sintética |
| `resultados/` | `calidad_datos.json`; `dev/`: resultados, operaciones, validez, M1, tablas y diagnóstico previo a OOS; `final/`: OOS-ETH |
| `registro/` | Descarga (URL, HTTP, bytes, hora), checksums, horas de inicio y fin, candado de OOS, incidente 01, entorno, logs |
| `reproduccion/` | `REPRODUCIR.sh`, `descargar_todo.sh` y `SHA256_zips_usados.txt` (228 ZIP) |
| `ensayo_sintetico/` | Ensayo funcional con datos **sintéticos**; no es evidencia económica |

- Sin datos crudos de terceros: se descargan de data.binance.vision y se verifican byte a byte.
- Sin commits, push ni despliegues. Sin dinero real. `validada_para_operar` sin tocar.
