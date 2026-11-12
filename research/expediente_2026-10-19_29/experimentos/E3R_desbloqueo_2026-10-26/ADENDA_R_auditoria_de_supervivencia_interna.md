# E3 · Adenda R: auditoría de supervivencia con evidencia interna del venue

**Estado:** PROPUESTA, congelada antes de calcular la auditoría (P0). **No autoriza ninguna ejecución confirmatoria.**
**Fecha de redacción:** 2026-10-26 (UTC).
**Protocolo de base:** `PROTOCOLO_E3_v3_PROPUESTO.md` (`279a865f…`), sus notas, adendas 1 y 3 y la enmienda 2. **Ninguno de esos documentos se modifica.**

## 1. Por qué existe esta adenda

- La v3 calcula las salidas **sin leer anuncios**:
  - liquidación contable al último precio negociado (§4.10);
  - en H1, último precio negociado (§4.13).
- Los anuncios cumplen dos funciones. Mapean renombres; un renombre no mapeado se trata como salida más listado nuevo, que es conservador. Y **auditan** que Vision no tenga salidas truncadas (§2.3; §4.11 ii–iv).
- La regla §4.11 (iv) («salidas sin anuncio ≤ 10 % por año») falló porque **el archivo web no tiene anuncios**: en Common Crawl no hay ninguno con fecha efectiva posterior al 2024-11-06. No falló porque Vision esté incompleto.
- Evidencia ya registrada en E3, sin retornos:
  - el bucket conserva pares retirados (228 dejan de tener archivos antes de 2026-05);
  - de las exclusiones anunciadas y archivadas, **ninguna** quedó en la categoría D (par ausente en Vision);
  - las 4 en la categoría T son tokens apalancados (DOTUP, DOTDOWN, TRXDOWN) y BKRW. Por las listas fijas de §4.5, ninguno puede entrar en un universo.
- **Lo que la auditoría tiene que garantizar** es que cada salida de un par que el protocolo puede operar sea una salida real, sin días negociados que falten en los datos. Para eso hay evidencia que genera el propio motor de Binance y que Vision publica.

## 2. Reglas (reemplazan, solo para la ejecución con esta adenda, a §4.11 ii–iv y a la contabilidad de fallas de §2.3)

**R1 · Alcance de la contabilidad.**
- Una salida observada (N7) o una falla de §2.3 cuenta solo si el par está **en alcance**.
- Está fuera de alcance si figura en `lista_fija` o en `apalancados` de las listas fijas de F3 (`listas_fijas_por_lunes.json`, con hash en `MANIFIESTO_F3.sha256`). Se usa el último lunes ≤ L, o ≤ E en el caso de una falla.
- Si el par sale antes del primer lunes de las listas, se toma el primer lunes.
- **Fundamento:** esos pares nunca son elegibles (§4.5) y no entran en ningún cálculo.

**R2 · Evidencia de salida real.** Una salida en alcance, con último día activo L, tiene evidencia si cumple al menos una:
- **ANUNCIO:** la conciliación de la primera pasada (`conciliacion_pasada1/eventos.json`) tiene, para ese par, un evento de categoría A o B.
- **SUSPENSION:** el día L + 1 tiene una fila presente e **inválida** (`estado = 3`: duración distinta de un día u OHLC incoherente). Es la vela parcial que deja una suspensión a mitad del día; una truncación de datos no la produce.
- **COLA_CERO:** algún día de (L, L + 30] tiene una fila con 0 operaciones (`estado = 2`). Es la marca del venue tras dejar de negociar (issue #201).
- Si no cumple ninguna, es **SIN_EVIDENCIA**.

**R3 · Inicio de H.** El inicio es el más tardío de:
- (i) sin cambios: primer lunes con 13 semanas seguidas evaluables;
- (ii′) la semana siguiente a la fecha efectiva de la última falla **en alcance** de §2.3 (T, D o C no explicada);
- (iv′) el 1 de enero del primer año Y tal que, para **todos** los años de Y a 2026, las salidas en alcance SIN_EVIDENCIA son ≤ 10 % de las salidas en alcance del año. Un año sin salidas en alcance cumple.
- (iii) **no se aplica**: medía la cobertura del archivo, que esta adenda deja de exigir.

**R4 · Casos C de la primera pasada.**
- Los 5 casos C (ARK, CREAM, FTT, GFT e IQ, página «Notice of Addition & Removal of Trading Pairs – 2023-09-22») se resuelven con la lectura manual que prevé la Adenda 3 (A3.5), sobre el texto archivado local.
- Si el texto pone el par en la parte de **agregados**, es un error de extracción y se descarta.
- Si lo pone en la parte de **removidos**, sigue siendo C, y es falla si está en alcance y no se explica.
- Si el texto no se puede leer, el caso sigue siendo C.

**R5 · Sin cambios:**
- INVÁLIDO si H tiene < 156 semanas evaluables o > 20 % de semanas no evaluables;
- hipótesis, señal, universos, costos, inferencia, criterios, robustez (incluido R6, −30 % en cada liquidación contable), sensibilidad y registro de ejecuciones.

## 3. Qué se informa en P0 (sin retornos)
- Por año:
  - salidas observadas;
  - salidas en alcance;
  - evidencia por tipo (ANUNCIO, SUSPENSION, COLA_CERO; no excluyentes);
  - SIN_EVIDENCIA y su proporción.
- La resolución de cada caso C, con la cita del texto archivado.
- Los componentes (i), (ii′) y (iv′), el inicio de H, las semanas evaluables y el veredicto VÁLIDO o INVÁLIDO.
- **Insumos:** solo `estado` de las series de calidad (sin leer O, H, L, C ni QV), las listas fijas, la conciliación y los textos archivados. Se verifica el sha256 de cada insumo antes y después.

## 4. Consecuencias fijadas ahora
- **VÁLIDO:** se recomienda autorizar **una** ejecución confirmatoria de la v3 con esta adenda (H1 y H2 con Holm, H3 subordinada). Antes de ejecutar:
  - el código del orquestador queda congelado y probado con datos sintéticos;
  - se registra la autorización.
  - El resultado se lee como en la v3: «evidencia histórica con contaminación declarada», nunca como confirmación independiente ni como autorización de capital (§7.3).
- **INVÁLIDO:** E3-H1 sigue NO EVALUABLE. No se relaja ninguna regla de esta adenda. La alternativa es la de la hoja de ruta del 2026-10-21: compilación manual de la lista, o pausa de la familia transversal.

## 5. Contaminación y límites, declarados
- **Al escribir esta adenda conozco:**
  - las cuentas de salidas por año y la cobertura del archivo (informe de ejecución de E3);
  - que existen filas inválidas en el borde de los listados (242 de 279, sin desglose por salida).
- **No conozco:** cuántas salidas tienen SUSPENSION o COLA_CERO, ningún retorno de estrategia, ningún IC, ninguna relación entre señal y resultado. Nadie los calculó.
- **La adenda cambia un criterio de validez, no la prueba.** No puede inclinar el resultado de H1 o H2 hacia el rechazo: decide si la prueba corre, no qué da. El riesgo que sí agrega es aceptar como válida una historia con truncaciones sin rastro (una salida sin vela parcial ni cola). Ese riesgo lo acota el 10 % de (iv′), lo mide R6 y se declara.
- **Decisión que no me corresponde:** cambiar un criterio de validez de un protocolo congelado es una decisión estratégica (categoría B). Esta adenda se propone y se congela; la ejecución confirmatoria requiere tu autorización expresa.
