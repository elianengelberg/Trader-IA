# Registro de defectos y limitaciones (al 2026-10-16)

## 1. Errores de implementación encontrados con datos reales (corregidos, con pruebas, antes de simular)

| # | Defecto | Efecto si no se corregía | Corrección y prueba |
|---|---|---|---|
| E-1 | El lector de velas esperaba un cierre a −1 ms también en el spot en µs (desde 2025); el real es −1 µs | La calidad abortaba y no se podía evaluar | `leer_klines` compara en la unidad nativa; `test_datos.py` actualizado con el formato real |
| E-2 | Una vela irregular (parada del exchange) abortaba toda la lectura | Igual que E-1 | Se excluye y se anota; `test_vela_irregular_se_excluye…` |
| E-3 | El fabricante sintético emulaba mal el cierre en µs (por eso el ensayo no detectó E-1) | Falsa confianza en el ensayo | `fabricar._kline` usa el formato real; el ensayo con semilla 101 se reproduce bit a bit |
| E-4 | El cerrojo del test dependía del manifiesto: una descarga nueva podía repetir el test | Reutilización del test | Cerrojo global `TEST_CONSUMIDO.json` con reserva exclusiva; `test_el_test_historico_tiene_un_cerrojo_global…` |
| E-5 | (Fase anterior) `importar` atribuía al usuario archivos fabricados | Etiqueta falsa | Corregido el 2026-10-16; `ERRATA.md` |
| E-6 | (Mío, en el análisis exploratorio) nocional calculado con el precio de entrada del corto | Funding por nocional exagerado (26 % en vez de 17,5 %) | Corregido antes de informar: nocional = \|importe/tasa\| por evento |

## 2. Problemas de datos
- **12 archivos de futuros no publicados** (2019-Q4). El inicio común pasa a 2020-01.
- **Mark: 192 h ausentes en los mensuales.** Completadas con los diarios oficiales.
- **Spot: 35 h sin vela y 8 velas irregulares** (paradas). Quedan como horas sin datos (39 en total).
- **Una diferencia de volumen** entre el archivo diario y el mensual (spot, 2021-12-24 03:00).

Todo está en `experimentos/historico/INFORME_DATOS.md`.

## 3. Limitaciones del modelo (no corregidas; delimitan las conclusiones)
- **Liquidación real:** no se modelan los tramos de margen, el ADL, la liquidación dentro de la hora ni las caídas del exchange. Por eso no se evaluaron variantes apalancadas.
- **Efectivo ocioso a 0 %:** sesga contra las políticas que salen del mercado (ver §6 del informe económico). No hay ninguna serie de rendimiento de USDT en Binance verificable; el T-bill es solo una aproximación.
- **Ejecución:** no hay libro de órdenes ni ejecuciones parciales. Los costes y el slippage son supuestos (conservadores); la pata adversa es un estrés extremo.
- **Riesgo de contraparte:** fuera del modelo.

## 4. Cuestiones metodológicas
- **M-1. Incoherencia del prerregistro:** P1 usa efectivo a 0 % y P2 un comparador del 5 %. Documentada, sin cambiar el resultado.
- **M-2. Guarda del laboratorio:** `experimento.correr` protege la división `"test"` por su **etiqueta**. Una división personalizada `{"desde", "hasta"}` que se solape con el test no se bloquea. No tuvo impacto, porque el test se ejecutó solo con el evaluador y bajo cerrojo, y los análisis por rango se hicieron después. Para un protocolo futuro, la guarda debería basarse en el rango temporal.
- **M-3. Decisiones de pipeline tomadas viendo los datos:** sí, pero no los resultados. La de D1 se tomó después de ver la discrepancia de volumen. Todas constan en la adenda 2, junto con la lectura estricta.
- **M-4. El prerregistro no es independiente:** lo redactó el mismo agente que construyó el motor. Los parámetros de umbral se fijaron con datos sintéticos.
