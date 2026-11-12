# Calibración A-S1 de la prueba primaria (PEC-1.0, MEC v0.2 §5) — 2026-10-21

**Decisión vinculante:** según la tabla de A-S1, **se usa la regla de respaldo**: p = máx(p_ℓ20, p_ℓ40, p_NW), con el
intervalo envolvente. Toda hipótesis futura debe declararla como inferencia decisiva en su prerregistro.
- **La prueba primaria (bootstrap-t por bloques, ℓ = 20) NO queda validada.** Rechaza de más, y de forma grave, en el
  proceso disperso por eventos (C4, tipo H-REV-SHOCK).
- **La regla de respaldo cumple las 48 comprobaciones.** Es conservadora, sobre todo en C4.

**Alcance:** solo datos sintéticos. No se tocó T, T-MULTI, el repositorio, las entregas históricas ni el paquete r1, y
no se usaron datos de mercado.

## Qué se ejecutó
- **Autorización:** el propietario la dio en el chat («autorizo A-S1, ejecutá la calibración»). Se transcribió; no hay
  firma (`registro/00_REGISTRO_AUTORIZACION.md`).
- **Código:** el del paquete r1 (`a8056ced…`), extraído de nuevo y verificado (80 archivos OK).
- **Parámetros congelados:** `28764d31…`, sin cambios. Son 6 procesos, n ∈ {1612, 366, 731, 1096}, 2000 réplicas,
  B = 1999 y semilla 20261103. En total, **96.000 réplicas** (48.000 por regla).
- **Una sola ejecución,** el 2026-10-21 de 16:15:23 a 16:46:25 UTC (31 min, 4 procesos), sin reanudaciones.
  - Las réplicas las calculó la función `_replica` del script congelado, repartida en 4 procesos.
  - El archivo de resultado lo escribió el **`main()` congelado**: `salida/resultado_calibracion.json`, `76a99c6b…`.
- **Lo fijado antes de la ejecución,** por SHA-256 a las 16:15:17 UTC
  (`registro/huellas_previas_a_la_ejecucion.txt`): el criterio, la lectura descriptiva, el código de verificación y una
  limitación conocida del criterio.

## Resultado
Rechazo cuando p ≤ α. El criterio congelado exige ≤ 3,20 % al 2,5 % y ≤ 5,97 % al 5 %. La tabla completa por celda está
en `verificacion/TABLA_CALIBRACION.md`.

| Regla | Comprobaciones que cumplen | Incumplimientos | Sobre-rechazo significativo con Holm (no vinculante) | Sub-rechazo |
|---|---|---|---|---|
| Bootstrap-t, ℓ = 20 | 33 / 48 | 15 | **7, todos en C4** | 0 |
| Regla de respaldo (máx) | **48 / 48** | 0 | 0 | 10 (7 en C4) |

**Prueba primaria, por proceso:**
- **C4, disperso por eventos (tipo H-REV-SHOCK): sobre-rechazo grave.**
  - Con n ≥ 731: 5,1–6,2 % al 2,5 % y 10,3–11,5 % al 5 %. Es el doble del nominal, con p binomial entre 10⁻¹¹ y 10⁻³⁰,
    así que **no es ruido de Monte Carlo**.
  - Con n = 366, 316 réplicas no tienen ningún evento: son degeneradas y cuentan como no rechazo. Entre las demás
    réplicas: 3,6 % al 2,5 % y 9,3 % al 5 %.
- **C2 (GARCH), C3 (AR(1)) y C5 (intradía):** incumplimientos sueltos, de 3,25 % a 3,55 % al 2,5 % y de 6,35 % a 6,55 %
  al 5 %. Su p binomial va de 0,001 a 0,02, y ninguno es significativo con Holm.
- **Fuera de C4, la tendencia es levemente liberal.** Es una lectura posterior (`verificacion/descriptivo_posterior.json`),
  con el IC de Wilson al 95 %:
  - al 2,5 %: 2,86 % [2,70; 3,03];
  - al 5 %: 5,60 % [5,38; 5,83].

**Regla de respaldo:**
- **Fuera de C4:** 2,30 % [2,16; 2,45] al 2,5 % y 4,72 % [4,52; 4,93] al 5 %. Es levemente conservadora.
- **En C4, muy conservadora al 2,5 %:** 0,3–1,1 % entre las réplicas no degeneradas. Eso **cuesta potencia** en
  estrategias dispersas.
- **En C5 (tipo H-EMA9-VWAP):** 2,2–2,9 % y 4,4–5,35 %, cerca del nominal.

**La decisión no depende del defecto de multiplicidad declarado antes de ejecutar.** El criterio congelado hace incumplir
a una prueba perfecta con probabilidad ≈ 62 % (`registro/multiplicidad_previa.json`). Aun así, la primaria falla también
con la lectura con Holm (C4, p ≈ 10⁻¹⁹), y la regla de respaldo no tiene ningún incumplimiento con ninguna de las dos
lecturas.

## Verificación
| Comprobación | Resultado | Archivo |
|---|---|---|
| Recuento independiente desde los 96.000 valores p crudos frente a la salida del `main()` congelado | Idéntico, 48 filas | `verificacion/verificacion.json` |
| p_respaldo ≥ p_primaria réplica a réplica, y degeneración coincidente | 0 réplicas incoherentes de 48.000 | ídem |
| 96 réplicas recalculadas en un proceso nuevo, elegidas al azar con semilla fijada antes | 96 / 96 idénticas | ídem |
| Huellas de parámetros, salida y código r1 | OK | `salida/ejecuciones.jsonl` |
| Orquestador frente al script secuencial, en una copia reducida con otra semilla | Byte a byte idéntico, también tras reanudar; no sobrescribe | `registro/prueba_extremo_a_extremo.log` |
| Prueba negativa: un valor p alterado | Detectado | ídem |
| Huellas previas a la ejecución | Las 7 OK después de ejecutar | `registro/huellas_previas_a_la_ejecucion.txt` |

**Independencia:** mismo autor, mismo código r1 y misma máquina, así que no es una verificación independiente en el
sentido de la cadena de confianza. Lo que se verificó es la **coherencia interna** y el determinismo. El recuento no usa
la agregación del script congelado.

## Qué no muestra
- La validez en datos reales: solo el tamaño en estos 6 procesos sintéticos (MEC §5).
- **La potencia:** requiere δ, y A8 sigue pendiente.
- **El error de tipo I global del diseño secuencial** (5 miradas O'Brien–Fleming). Se calibró el tamaño de cada mirada
  como prueba de tamaño fijo, no la secuencia conjunta. Queda abierto (ver abajo).
- **B:** la calibración usa B = 1999, como estaba congelado; las evaluaciones usarán B = 9999.

## Consecuencias para el plan (r1, que no se modifica)
1. **Evaluaciones pasadas:** **ninguna cambia.** Según el registro del programa, ninguna evaluación confirmatoria usó
   esta prueba como decisiva (E3-H1 a E3-H3 quedaron NO_EVALUABLE).
2. **D-S1 / D-S3:** la inferencia decisiva de toda hipótesis futura pasa a ser la regla de respaldo, y la primaria queda
   como descriptiva. `pec/decision.py` ya recibe p e IC90 como entradas, así que no cambia.
   - El esquema PEC-1.0 hoy solo admite `prueba.metodo = bootstrap_t_bloques_circulares`, con `regla_respaldo`
     declarada.
   - **Hace falta un PEC-1.1** que declare explícitamente la regla de respaldo como decisiva y lo compruebe en
     `validar_semantica`. Es un cambio menor; no se hizo aquí.
3. **H-REV-SHOCK (tipo C4):** el único método validado tiene un tamaño real de ≈ 0,3–1,1 % frente al 2,5 % nominal. Eso
   le resta potencia a una hipótesis que ya exigía ≥ 7,9 % neto por evento. **Se refuerza «no iniciar».**
4. **H-EMA9-VWAP (tipo C5):** la regla de respaldo tiene un tamaño casi nominal. Sigue la recomendación de r1: solo
   prospectiva, aceptando «no concluyente».
5. **La criba** (IR ≥ 1,64 para confirmar en 3 años) suponía una prueba de tamaño nominal. Con una regla conservadora,
   el IR requerido es **algo mayor**. No se cuantificó porque requiere δ.

## Qué necesita tu decisión
- **δ (A8):** es el próximo paso de mayor valor, porque habilita la potencia y la fase prospectiva.
- **El criterio de calibración para versiones futuras.** El de MEC v0.2 §5 incumple con probabilidad ≈ 62 % aun con una
  prueba perfecta. Si querés uno corregido (más réplicas, o un control de multiplicidad declarado de antemano), es una
  versión nueva y se recalibra con otra semilla.
- **Si se calibra también el diseño secuencial completo** (error de tipo I global con 5 miradas). Es una ejecución
  sintética nueva y requiere su propia autorización.
- **Si se hace PEC-1.1** (punto 2 de las consecuencias).

## Hallazgos menores, solo documentales
- **N-6:** el docstring de `sintetico.proceso` dice «centradas exactamente (media muestral 0)». El código no centra la
  serie (corrección N-3) y lo explica en un comentario.
- **N-7:** A-S1 estimaba ≈ 1,3 h / 3,9 h. `F4` medía 2,09 h / 6,27 h en un solo núcleo. Con 4 procesos tardó 31 min.

## Reproducir y verificar
```
R1_ZIP=<CIERRE_AUDITORIA_v0.5_Y_PLAN_CUANTITATIVO_r1_2026-10-21.zip> bash orquestador/reproducir.sh <directorio_nuevo>
```
- El script reproduce la calibración (≈ 30–90 min) y la compara byte a byte con la salida y las 48 celdas empaquetadas.
- Las réplicas son deterministas, así que reproducir no es una segunda calibración.
- Para solo verificar, sin volver a calcular la calibración:
  ```
  python3 -B -I orquestador/verificar_calibracion.py <paquete_r1_extraido> salida <destino>
  ```
