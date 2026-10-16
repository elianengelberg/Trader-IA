# Cómo ejecutar la validación histórica con datos reales

Estado al 2026-10-16 (19:54 UTC): **no ejecutada**. Especificación exacta de los archivos y lista de URLs en `experimentos/historico/REQUISITOS_DATOS_HISTORICOS.md`. La red del entorno deniega `data.binance.vision` (403). Todos los comandos se ejecutan desde `research/hcarry_next` con `PYTHONPATH=src`.

## Vía 1 (recomendada): habilitar el dominio

En el entorno: menú del entorno → *Edit* → *Network access* → añadir `data.binance.vision` a *Allowed domains*.

> Si el cambio reinicia el contenedor, se pierde todo lo no versionado. Guardá antes el último ZIP del proyecto.

```
.venv/bin/python -B -m hcarry descargar --destino datos/binance_vision --desde 2019-10 --hasta 2026-06
```

Baja cada zip con su `.CHECKSUM` oficial y los verifica. Es reanudable, y los meses no publicados quedan anotados.

## Vía 2: copia descargada en otra máquina

En una máquina con acceso a Binance, con el ZIP de H-CARRY Next descomprimido (solo necesita Python ≥ 3.11):

```
PYTHONPATH=src python3 -m hcarry descargar --destino binance_vision --desde 2019-10 --hasta 2026-06
```

Subí la carpeta `binance_vision` a una rama nueva del repositorio (por ejemplo `datos/binance-vision-btcusdt`). Por Drive no es fiable: la herramienta devuelve el contenido en base64 dentro de la conversación. Aquí:

```
.venv/bin/python -B -m hcarry importar --origen COPIA_DESCOMPRIMIDA --destino datos/binance_vision
```

`importar` vuelve a verificar cada archivo contra su `.CHECKSUM` oficial. Una copia manipulada a la vez en datos y checksums no se detectaría: si querés más garantía, comprobá en tu máquina algunos hashes al azar contra data.binance.vision.

## Después: calidad y evaluación prerregistrada (una sola vez)

```
.venv/bin/python -B -m hcarry calidad   --directorio datos/binance_vision --salida experimentos/historico/calidad.md
.venv/bin/python -B -m hcarry historico --datos datos/binance_vision
```

- Si la calidad no es apta, el evaluador se detiene sin simular. La conclusión es EVIDENCIA INSUFICIENTE.
- Si es apta:
  1. calcula el diagnóstico de persistencia, solo en desarrollo;
  2. corre desarrollo y validación;
  3. prerregistra el test con los datos concretos;
  4. lo ejecuta una vez, con las 8 sensibilidades;
  5. aplica los criterios de `experimentos/historico/PRERREGISTRO_VALIDACION_HISTORICA.md`.
- Los resultados van a `experimentos/historico/resultados/historico/`.
- **El test no se repite.**
