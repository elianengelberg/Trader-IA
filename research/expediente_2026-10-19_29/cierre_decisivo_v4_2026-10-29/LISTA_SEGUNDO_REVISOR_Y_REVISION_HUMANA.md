# Qué tiene que verificar un segundo revisor real y qué requiere revisión humana

**Segundo revisor real:** una persona, u otro sistema, que no haya escrito ni encargado nada de E3, la reparación, el v3, el v4, el v4.1 ni SL-v1, y que no comparta familia de modelos con el autor ni con el lector.

En esta fase **no hubo ninguno**. Lo más parecido fue:
- el lector y el adjudicador de SL-v1;
- el revisor del diseño v4 de la fase anterior;
- el verificador de la matriz.

Los tres son agentes separados, pero de la **misma familia**, corren en el **mismo contenedor** y los lanzó el autor.

Rutas relativas a `cierre_decisivo_v4_2026-10-29/`, salvo indicación.

## A. Evidencia que tiene que verificar el segundo revisor (técnica, reproducible)

| # | Qué | Cómo | Criterio |
|---|---|---|---|
| A1 | SL-v1 se congeló antes de armar el paquete y de leer | Comparar `registro/CONGELACION_SL-v1.txt` (00:24:56Z) con `registro/LANZAMIENTO_LECTOR.txt` (00:26:24Z) y `registro/RECEPCION_RONDA1.txt` (00:40:24Z). Recalcular los sha256 | Las horas están en orden y los hashes coinciden. Límite: las horas las genera el mismo entorno |
| A2 | El paquete era ciego | Leer `segunda_lectura/paquete/ITEMS.json` y `ENCARGO_LECTOR.md` | No hay fechas de pasadas anteriores, categorías ni nada de la ventana |
| A3 | La lectura es fiel al texto | Releer en las páginas de `paquete/paginas/` los 13 ítems decisivos: DOTUP, DOTDOWN, TRXDOWN y LINKUP (E_N5); ARK, CREAM, FTT, GFT e IQ (AGREGA); BKRW (CORRIGE_PAR); AUTO, NEBL y YFII (E de 2023). Muestrear al azar 10 de los 34 restantes | Ninguna discrepancia en los decisivos; cualquier discrepancia se documenta con cita |
| A4 | La conversión mecánica es correcta | Revisar `segunda_lectura/herramientas/construir_resoluciones_L2.py` y repetir la corrida | Se reproduce `calculo/L2_resoluciones/comparacion_L2.json` |
| A5 | Escaneo Ω | Revisar las expresiones de `herramientas/escaneo_omega.py` y proponer omisiones de recall. Releer 15 de los 169 candidatos clasificados `NO_SPOT` | No hay ningún candidato spot mal clasificado. Las propuestas de recall se corren como SL-v2 si encuentran algo |
| A6 | Ventana L2 | Repetir `herramientas/calcular_ventana.py` (con el control de la segunda pasada primero) | Se reproducen `calculo/control_pasada2/ventana.json` y `calculo/L2/ventana.json` en componentes, fallas, inicio, semanas y veredicto |
| A7 | Máquina de estados v4.1 | Repetir `tecnico/r2_maquina/prueba_exhaustiva.py` y `prueba_senales_proceso.py`. **Escribir mutantes propios** | 0 violaciones fuera del límite declarado; sus mutantes se detectan, y si no, es un hallazgo |
| A8 | Validador de autorización | Repetir `tecnico/l17_autorizacion/prueba_autorizacion.py` con `/usr/bin/python3` y agregar vectores propios | Solo se acepta el positivo de prueba |
| A9 | Potencia | Revisar `metodologia/potencia_D8.py`: fórmula, supuestos de la v3 §7.1 y AR(1) | Se reproduce `potencia_D8.txt` |
| A10 | Inventario R-4 | Repetir el `find` de `tecnico/r4_aislamiento/inventario.txt` | Las mismas 2 copias reales extraídas, el mismo tarball y los mismos 15 orquestadores (o la diferencia explicada) |
| A12 | Adjudicación de los BLVT, que es el punto que decide la validez | Releer `segunda_lectura/adjudicacion/paquete/paginas/…updates-on-binance-leveraged…json` y la regla R-E. Evaluar `adjudicacion.json` y la observación del lector | Dictamen propio sobre qué fecha fija la regla congelada, **sin** recalcular la ventana para elegirla |
| A11 | Nada cambió | Repetir las huellas de `registro/huellas_inicio.txt` y `registro/huellas_fin.txt`, y `git status` | Son iguales |

## B. Cuestiones que requieren revisión humana (no se resuelven técnicamente)

| # | Cuestión | Por qué es humana |
|---|---|---|
| B1 | D-1(c): reabrir E3 para ejecución y adoptar la Adenda R, que sustituye (iv) por (iv′) y dispensa la condición del CIERRE §4 | Revierte tu propia decisión de cierre. `ADENDA_R` l. 73 la reserva para vos (categoría B) |
| B2 | D-8: si una ejecución con P(RESPALDADA) ≤ 0,13–0,17 y potencia de H1 de 0,35–0,55 sirve para alguna decisión tuya, y qué lectura previa se registra para un INSUFICIENTE | Valor de la información para tus decisiones |
| B3 | D-9: sellar (o empaquetar y retirar) las 2 copias reales extraídas de las series | Modifica árboles congelados. Sin tu orden, L-25 sigue abierto |
| B4 | D-11 y A-1: mecanismo del ancla externa y verificación de que la salida estándar o la transcripción quedan fuera del contenedor | Solo vos podés comprobar dónde se conserva la transcripción y custodiar el ancla. Las pruebas muestran que sin ancla no hay garantía ante un disco que miente |
| B5 | Ratificar D-3, D-4 y D-6 | Se deducen de la precedencia documental, pero fijan la ventana y el universo: conviene que conste tu conformidad antes de cualquier autorización |
| B6 | D-10: si alcanza con revisores de la misma familia | Es tu criterio de independencia |
| B7 | Herramienta de firma, custodia de la clave y prueba de interoperabilidad (N-L17-3) | Requiere tu clave, que nunca tiene que estar al alcance del agente |
| B8 | A-3: cómo se verifica Ed25519 en el intérprete del orquestador (instalar `cryptography` fijada o hacer un paso previo con `/usr/bin/python3`) | Instalar requiere red y autorización. El paso previo cambia el entorno fijado |
