# Prerregistro: evaluación EN PAPEL con reglas congeladas (2026-10-17)

- **Naturaleza:** prospectiva y en papel. **Sin órdenes, sin claves y sin dinero real.**
- **SHA-256 de las reglas** (`prerregistro_papel.json` = `tendencia.papel.PRERREGISTRO_PAPEL`): `d2e4e1fb43b8219b80e19736ba7a9abed22d6e858f0b8955171496fa06e74939`.
- **Huella del código** (`src/tendencia/*.py`): `73b22f3e3a8f21513d5533fb11a7553becae30b87c8736fb6880bccc36c11d2b`.
- **Fecha de congelado:** la del commit en GitHub que introduce este archivo. Es anterior a cualquier dato evaluado.

**Nada de esto se modifica después.** Un cambio de reglas es una hipótesis nueva, con su propio prerregistro y su propio período prospectivo.

## Qué se evalúa
- **T_BTC y T_ETH:** tendencia long/flat, exactamente como en `INFORME_NUEVA_LINEA.md`:
  - ventanas {30, 90, 180} días;
  - exposición 0, ⅓, ⅔ o 1;
  - decisión con el cierre UTC y ejecución en la apertura oficial siguiente;
  - solo opera cuando cambia el objetivo;
  - costes de 10 + 5 bps; efectivo al 0 %; sin apalancamiento ni cortos.
- **Benchmarks:** buy and hold, estática con la misma exposición media (rebalanceo diario sin costes) y efectivo.
- **Métrica principal:** exceso de timing = media diaria de (estrategia − estática), promediado entre BTC y ETH.
- **Monitor del carry (H-CARRY):** funding medio de 90 días de BTCUSDT, anualizado. **Si supera el 12 % anual**, se propone reabrir H-CARRY con un prerregistro prospectivo nuevo.
- **Datos:** `data.binance.vision`, velas 1d **diarias** con `.CHECKSUM` y fundingRate mensual. Se descargan y verifican en cada evaluación.

## Decisiones prerregistradas (en cada corte; bootstrap por bloques de 20 días, 2 000 remuestreos, semilla 20261017)

| Corte | Decisión |
|---|---|
| < 12 meses | **Solo informativo**: ninguna decisión |
| ≥ 12 meses y P(exceso BTC+ETH > 0) < 0,10 | **HIPÓTESIS NO RESPALDADA: detener** |
| ≥ 24 meses, P(BTC+ETH) ≥ 0,95, P(BTC) ≥ 0,90 y exceso con costes ×2 > 0 | **VENTAJA RESPALDADA** |
| Cualquier otro caso | **EVIDENCIA INSUFICIENTE: continuar** |

**Potencia** (`papel/potencia.py`; solo desarrollo):
- con el efecto estimado en desarrollo hacen falta **≈ 7 años** para P ≥ 0,95 (BTC solo, ≈ 10); con la mitad del efecto, ≈ 28 años;
- un resultado de 1–2 años **solo puede descartar un fracaso grueso** o detectar problemas operativos; **no puede confirmar** una ventaja;
- la estimación de desarrollo probablemente está inflada, porque se eligió tras verla.

## Período reservado de H-CARRY (2026-06-01 → 2026-10-13): **pendiente de tu decisión**
La señal necesita 180 días de cierres. Hay dos ramas, ambas fijadas aquí:
- **Rama A** (si autorizás usar los **precios** del período reservado **solo como historia de la señal**, nunca para evaluar): la primera ejecución es el **2026-10-18**.
- **Rama B** (si no lo autorizás): la señal solo usa días ≥ 2026-10-14, y la primera ejecución es el **2027-04-13**. El monitor del carry reporta desde que hay 90 días completos sin el período reservado, alrededor de febrero de 2027.

Hasta que decidas, el código funciona en la **rama B** y no descarga ni lee nada del período reservado. Las guardas tienen pruebas en `tests/test_papel.py`.

## Cómo se evalúa (en cualquier fecha; determinista)
```
cd research/tendencia_btc; export PYTHONPATH=src:../hcarry_next/src; PY=../hcarry_next/.venv/bin/python
$PY -B -c "from pathlib import Path; from tendencia import papel as P
for s in ('BTCUSDT','ETHUSDT'): P.descargar(Path(f'datos_papel/{s}'), s, '2026-10-14', 'AAAA-MM-DD')   # rama B
print(P.evaluar({'T_BTC': Path('datos_papel/BTCUSDT'), 'T_ETH': Path('datos_papel/ETHUSDT')}, 'AAAA-MM-DD', rama='B'))"
```
La salida incluye la huella del código y el hash de las reglas. Si alguno no coincide con los de arriba, el resultado **no vale** como evaluación de este prerregistro.

## Qué no está prohibido y qué sí
- **Permitido:** recalcular cuando se quiera. Solo los cortes de 12, 24, 36… meses tienen consecuencias.
- **Prohibido:**
  - cambiar reglas, parámetros o criterios;
  - usar cortes intermedios para ajustar nada;
  - evaluar dentro del período reservado.

## Adenda 1 (2026-10-17): decisión del usuario y estado inicial — sin cambios en las reglas

- **Rama elegida: A.** El usuario autoriza usar los **precios** del período reservado de H-CARRY solo como historia de la señal. Nada se evalúa dentro de ese período.
  - Primera ejecución: **2026-10-18**, con la decisión tomada al cierre del 2026-10-17. Ese cierre es justo el día 180 de la historia que empieza el 2026-04-20.
  - Evaluar con `rama="A"`. Las reglas (`d2e4e1fb…`) y el código (`73b22f3e…`) no cambiaron.
- **Historia de la señal descargada:** `datos_papel/{BTCUSDT,ETHUSDT}`, 2026-04-20 → 2026-10-16. Son 180 archivos diarios oficiales por activo, sin ausentes; los manifiestos se versionan y los datos, no.
- **Monitor del carry al 2026-10-01** (90 días: 2026-07-03 → 2026-09-30; fundingRate mensual oficial, cobertura 100 %): **6,5 % anual**. Por debajo del disparador del 12 %, así que **no se reabre H-CARRY**. También queda por debajo del ≈ 9,3 % que rev. 5 necesitaba para el 5 %.
- **Plan acordado:** papel y monitor, sin más desarrollo.
  - Primer corte con consecuencias a los 12 meses (2027-10-18). Revisión informativa a los 6 meses (2027-04-18).
  - El monitor puede consultarse en cualquier momento.
  - Script de estado: `papel/estado_inicial.py`, que no altera la huella de `src/`.

## Adenda 2 (2026-10-17, 15:40 UTC; sin observaciones prospectivas todavía): procedimiento operativo — reglas sin cambios

Reglas (`d2e4e1fb…`) y código de `src/` (`73b22f3e…`): **sin cambios**. Esta adenda corrige el **procedimiento**, no la estrategia. Detalle en `papel/VERIFICACION_OPERATIVA_2026-10-17.md`.

1. **Cada corte se ejecuta con `papel/corte.py AAAA-MM-DD`.** El comando de «Cómo se evalúa» corresponde a la rama B. Usado con la rama A, la señal quedaba **sin historia** durante 180 días y el código congelado la tomaba como exposición 0 sin avisar.
   - El ejecutor descarga la historia completa desde el 2026-04-20 y bloquea la evaluación si falta historia, si hay datos obsoletos o no publicados, si hay huecos o repeticiones, si un archivo ya registrado fue revisado o si las huellas no coinciden.
   - Registra las decisiones día a día (cierre usado, momento de disponibilidad y precio de referencia) y deja constancia en `papel/cortes/REGISTRO.jsonl`, que solo admite añadidos.
2. **Fechas de corte** (`corte` es exclusivo; el código mide los meses como días / 30,44):

| Revisión | Corte | Días | Consecuencia |
|---|---|---|---|
| 6 meses | 2027-04-18 | 182 | Informativa |
| 12 meses | **2027-10-19** | 366 | Primera con consecuencias. Con el corte 2027-10-18 serían 365 días = 11,99 «meses», y el código congelado la trataría como informativa |
| 24 meses | 2028-10-18 | 731 | Posible confirmación |

3. **Monitor del carry:** siempre con meses completos. El ejecutor lo calcula en el primer día del mes del corte, porque con un mes incompleto la función congelada divide por 90 días y sesga el resultado a la baja. Es informativo: no activa nada.
