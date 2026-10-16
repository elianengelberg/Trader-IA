# H-CARRY Next

Laboratorio de investigación del carry delta-neutral en BTCUSDT: largo spot y corto en el perpetuo USDⓈ-M. Es la evolución de H-CARRY rev. 5, cuyo código original se perdió.

**Solo simulación:** ningún módulo envía órdenes, usa claves ni toca producción.

> **Estado (2026-10-16):** motor, pruebas y laboratorio funcionando. **Todos los resultados económicos son SINTÉTICOS**: la red del entorno bloquea los datos de mercado (ver `experimentos/DATOS_REALES.md`). No hay ninguna conclusión sobre la rentabilidad real.

## Uso rápido

Si recibiste el proyecto en ZIP, descomprimilo con `unzip`, que conserva el modo de solo lectura de `recuperado/`. Hay una prueba que lo verifica, y `zipfile.extractall` de Python no lo conserva.

```
cd research/hcarry_next
uv venv --python python3.11 .venv && uv pip install --python .venv/bin/python pytest hypothesis   # si no existe
.venv/bin/python -B -m pytest -q                                   # pruebas (sin red)
PYTHONPATH=src .venv/bin/python -B -m hcarry estructura            # aritmética de la estructura de capital
PYTHONPATH=src .venv/bin/python -B -m hcarry protocolo --sintetico 101 --salida /tmp/p101   # protocolo en un mundo sintético
PYTHONPATH=src .venv/bin/python -B -m hcarry calidad --directorio DATOS                 # informe y filtros de calidad
PYTHONPATH=src .venv/bin/python -B -m hcarry historico --datos DATOS                   # validación prerregistrada (ver experimentos/historico/)
.venv/bin/python -B experimentos/correr_sintetico.py 101 12        # ensayo en 12 mundos + 12 nulos
.venv/bin/python -B experimentos/estres_capacidad.py               # estrés y capacidad (sintético)
```

Las dependencias de ejecución son solo la biblioteca estándar (Python ≥ 3.11). Las pruebas usan pytest e hypothesis.

## Estructura

| Ruta | Contenido |
|---|---|
| `src/hcarry/conventions.py` | Unidades, signos, tiempos y período reservado (bloqueado en el código) |
| `src/hcarry/data/` | Esquema, cargador de data.binance.vision (checksums), validación (catálogo rev. 5) y generador sintético |
| `src/hcarry/model/` | Costes y filtros, cartera de dos cuentas, motor horario, conciliación independiente |
| `src/hcarry/estrategias.py` | Vista sin look-ahead; referencia rev. 5 (`Siempre`), `UmbralFunding`, `UmbralPrima`, `RhoPorVolatilidad`, `EscalaPorVolatilidad` |
| `src/hcarry/metricas.py` | Métricas sobre el capital total y comprometido; clasificador D1–D4 de rev. 5 |
| `src/hcarry/lab/` | Divisiones, experimentos con registro, bootstrap pareado y protocolo desarrollo → validación → test |
| `src/hcarry/analisis.py` | Aritmética de la estructura de capital |
| `tests/` | 78 pruebas: casos a mano, regresión rev. 5, propiedades, look-ahead, datos, laboratorio |
| `recuperado/` | Material original recuperado de rev. 5, en solo lectura con sus hashes |
| `experimentos/` | Scripts, registros y resúmenes de los experimentos (sintéticos) |
| `PROVENANCE.md`, `DECISIONS.md`, `CHANGELOG.md` | Recuperado frente a reconstruido frente a nuevo; decisiones; cambios |
| `INFORME_HCARRY_NEXT.md` | Informe de la fase: resultados, limitaciones y próximo experimento |
| `INFORME_VALIDACION_HISTORICA.md` | Validación histórica rev. 5 frente a UmbralFunding: estado, prerregistro, ensayo y características (sintéticas) y conclusión |

## Convenciones clave

- **Tiempo:** milisegundos UTC; barras horarias por su apertura.
- **Funding:** se liquida sobre la posición de la hora anterior, antes de operar. Con f > 0 el corto cobra q·m·f.
- **Equity ejecutable:** E = U + q·S + W + q·(Fb − F).
- **ρ:** equity de futuros / nocional del corto.
- **Liquidación:** P_liq = (W + q·Fb)/(q·(1 + mmr)).

El detalle está en `src/hcarry/conventions.py`.
