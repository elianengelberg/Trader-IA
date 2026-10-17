# Reproducir la validación histórica sin una sesión de Claude

Requisitos: Python ≥ 3.11 y acceso a `data.binance.vision`. El paquete no tiene dependencias de ejecución; las pruebas usan `pytest`, `hypothesis` y `ruff`.

```
git clone -b claude/algo-trading-simulation-platform-ngf7xo https://github.com/elianengelberg/Trader-IA.git
cd Trader-IA/research/hcarry_next
python3 -m venv .venv && .venv/bin/pip install pytest hypothesis ruff
.venv/bin/python -B -m pytest -q                                  # 81 pruebas
export PYTHONPATH=src
```

## 1. Datos oficiales (unos 10 MB, unos 3 min)
```
.venv/bin/python -B -m hcarry descargar --destino datos/binance_vision --desde 2019-10 --hasta 2026-06
.venv/bin/python -B -m hcarry completar-diarios --directorio datos/binance_vision
.venv/bin/python -B -m hcarry calidad --directorio datos/binance_vision --salida /tmp/calidad.md
```
- Deben quedar 412 archivos verificados, 12 no publicados (futuros 2019-Q4) y la calidad **apta**.
- Una descarga nueva tiene otra fecha en `MANIFIESTO.json`, y por tanto **otro hash de manifiesto**. Para verificar que los datos son los mismos, compará los `sha256` de cada archivo con los del manifiesto evaluado (`8bdabde7…`), que se conserva en el ZIP del registro del test (`datos/binance_vision/MANIFIESTO.json`).

## 2. Diagnóstico de desarrollo (antes del test, solo 2020–2022)
```
.venv/bin/python -B experimentos/historico/diagnostico_desarrollo.py
.venv/bin/python -B experimentos/historico/investigacion_desarrollo.py
```

## 3. Test prerregistrado
**El test ya está consumido.** `experimentos/historico/resultados/historico/TEST_CONSUMIDO.json` impide repetirlo en la carpeta canónica.

Para **replicar** el resultado (comprobar el determinismo, no evaluar de nuevo), usá otra carpeta de resultados:
```
.venv/bin/python -B -m hcarry historico --datos datos/binance_vision --resultados /tmp/replica
```
Con los mismos datos, el resultado coincide exactamente con `datos_8bdabde706bf/resultado.json`; se comprobó el 2026-10-16 con el código `9d11ecbe…`. Una replicación **no** es evidencia nueva y no debe usarse para elegir nada.

## 4. Análisis posteriores al test (exploratorios)
```
.venv/bin/python -B experimentos/historico/post_test_exploratorio.py
.venv/bin/python -B experimentos/historico/post_test_efectivo_remunerado.py   # usa post_test/externos/DTB3.csv (FRED)
```
- El funding de ETH y SOL se baja con `hcarry.data.binance_vision.descargar(destino, "2020-01", "2026-06", simbolo="ETHUSDT", tipos=("funding",))`.
- Los análisis exigen que exista el cerrojo del test: solo tienen sentido después de él.

## Referencias
- Prerregistro: `experimentos/historico/PRERREGISTRO_VALIDACION_HISTORICA.md`, con las adendas 1–3.
- Datos: `experimentos/historico/INFORME_DATOS.md`.
- Economía: `INFORME_ECONOMICO_HISTORICO.md`.
- Experimentos: `experimentos/historico/REGISTRO_EXPERIMENTOS.md`.
- Defectos: `REGISTRO_DEFECTOS.md`.
- Estado y recomendación: `ESTADO_EJECUTIVO_HISTORICO.md`.
