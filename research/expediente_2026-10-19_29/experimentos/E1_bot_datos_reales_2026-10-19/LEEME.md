# E1: las estrategias del bot con datos reales de BTCUSDT a 1 h

Es un experimento aislado: no modifica el repositorio, no hace commits y no opera.

| Ruta | Contenido |
|---|---|
| `prerregistro/PRERREGISTRO_E1.md` | Hipótesis, datos, configuraciones, costos, métricas, inferencia y criterios, escritos antes de evaluar datos reales |
| `prerregistro/HUELLAS_ANTES_DE_EJECUTAR.txt` | SHA-256 del prerregistro, el código y el entorno, con su hora, fijados antes de la ejecución |
| `entorno/` | venv aislado (Python 3.11.17); `requisitos_con_hash.txt`; ruedas verificadas contra PyPI (`logs/01_*`) |
| `codigo/e1_comun.py` | Datos verificados contra `.CHECKSUM`, `MotorE1` (correcciones D1 y D2 copiadas de la sesión en vivo), escenarios y round trips |
| `codigo/e1_verificacion.py` | Verificación del backtester con datos **sintéticos**: look-ahead, réplica independiente, D1/D2 y solo largos |
| `codigo/e1.py` | Ejecución y análisis prerregistrados |
| `codigo/diag_motor.py` | Diagnóstico inicial de D1/D2 con datos sintéticos |
| `datos/` y `resultados/real/manifiesto_datos.json` | SHA-256 de cada archivo de datos y de la lista completa |
| `resultados/verificacion_backtester_sintetico*.json` | Resultado de la verificación: la corrida 1 con los criterios iniciales y la corrida 2 con los corregidos |
| `resultados/ensayo_sintetico/` | Ensayo funcional del flujo con datos sintéticos; no es evidencia |
| `resultados/real/` | La ejecución única con datos reales: `validez.json`, `resultado_e1.json` y `operaciones_por_configuracion.json` |
| `informe/INFORME_E1.md` | Informe final |
| `logs/` | Salida de cada paso, en orden |

Para reproducir:

```
cd codigo
PYTHONPATH=/home/user/Trader-IA/packages/tia/src:. ../entorno/venv/bin/python -B e1_verificacion.py <salida.json>
PYTHONPATH=/home/user/Trader-IA/packages/tia/src:. ../entorno/venv/bin/python -B e1.py --salida <dir nuevo>
```
