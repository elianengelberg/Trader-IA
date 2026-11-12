# Trader-IA · Informe de la misión de dirección técnica y cuantitativa (2026-10-26)

**NO AUTORIZADO PARA OPERAR CON DINERO REAL.**
- No hubo commits, push, PR, merge ni despliegue.
- No hubo conexión a exchanges ni a Testnet, ni uso de credenciales.
- El repositorio protegido queda sin cambios (ver `VERIFICACION_FINAL.txt`).

## 0. Los antecedentes, contrastados con sus fuentes

| Antecedente | Qué verifiqué | Estado real |
|---|---|---|
| **Correcciones 01–22** | Reconstruidas desde un clon nuevo de `72ffae5`. Cada árbol intermedio coincide con el registro (`reproducir_DT.sh`) | En pie. Se agregan 23–25 |
| **Kill switch** | P01 (parche 16) y sus pruebas, en la CI local de T25 | Conserva el stop. Falta verificarlo contra un venue real (P33) |
| **Errores declarados corregidos que no funcionaban** | P04 (R19 sin efecto en producción, ciclo 1). En este ciclo apareció otro de la misma clase: P16 apuntaba a un mecanismo equivocado, y el real dejaba la posición **sin stop** (P28) | Corregido (25). Lo que queda de esa misma causa está en P29 |
| **Alertas** | P05 (parche 19), con `test_alert_delivery.py` en la CI de T25 | En pie. La entrega por un canal real no está verificada (P33) |
| **Pruebas dependientes de la hora** | P25: reproducción determinista del ciclo 1 | Diferida a propósito, con mitigación operativa (P25 y P34) |
| **Huecos de mutación** | P09 y P24: 22/22 y 11/11 en T21 | En pie para T21. **Los parches 23–25 no pasaron por mutación**, solo por la prueba sin y con corrección |
| **0/18 hipótesis** | Registro `HIPOTESIS_PROGRAMA.json` y sus informes | Exagera: 7 refutadas, 8 sin ventaja, 3 **nunca probadas** (P32) |
| **E3-H1 pendiente** | `CIERRE_E3.md` y v3 §4.11 | El bloqueo era la regla (iv) de inicio, no «un dato». Destrabada y lista para correr (P31) |
| **Sin autorización para dinero real, publicación ni despliegue** | Repo protegido (HEAD `72ffae5`, índice `37490035…`), `validada_para_operar` | Se mantiene |
| **Validación en Binance Testnet pendiente** | P16, P28, P29 | Sigue pendiente. **Hoy no conviene hacerla:** sin P29 solo mostraría el freno (P33) |

## 1. Diagnóstico independiente

- **El cuello de botella es la información, no la infraestructura.**
  - El proyecto tiene 0 hipótesis respaldadas.
  - Los últimos ciclos endurecieron mucho el vivo. Eso tiene valor decreciente mientras no haya una razón económica para operar.
- **La única prueba pendiente que puede cambiar decisiones es E3-H1/H2.** Nunca se probó. Su bloqueo era metodológico (la cobertura del archivo web) y se resolvió con evidencia interna del venue, sin tocar ningún retorno.
- **El vivo tenía un defecto que ninguna prueba en papel podía ver.**
  - El papel cobra la comisión en la moneda de cotización; Binance spot la cobra, por defecto, en el activo comprado.
  - Con eso, el stop protector salía fuera de la grilla de lotes y lo rechazaban: posición sin stop después de cada entrada (P28, corregido).
  - Lo que queda de esa misma causa deja el vivo inoperable, aunque falla cerrado (P29). Es otra razón para no apurar Testnet.
- **Lo que hacíamos por inercia:**
  - seguir auditando el vivo como si fuera el camino crítico;
  - leer «0/18» como «todo refutado»;
  - tratar el bloqueo de E3-H1 como falta de un dato externo.

## 2. Correcciones y experimentos

| Id | Qué | Evidencia |
|---|---|---|
| **P26** (23) | Una sola sesión viva por cuenta entre procesos. Una base ilegible niega el arranque | 3 pruebas. Las 2 esenciales fallan sin la corrección |
| **P27** (24) | Un resto menor que un lote no es una posición | 3 pruebas (2 fallan sin la corrección; la tercera fija que una tenencia ajena ≥ 1 lote sigue frenando). Dos sondas |
| **P28** (25) | El stop se redondea al lote, nunca por encima de lo que hay | 1 prueba con un venue que cobra la comisión en el activo base y rechaza fuera de la grilla. Sin la corrección: `LOT_SIZE` y posición sin protección. Con ella: stop válido |
| **E3R** | Adendas R, R1′ y R2 congeladas; P0 por las dos reglas; orquestador congelado y probado en sintético | `E3R/` (ver P31). **Ningún retorno real calculado** |
| **Cadena 01–25** | Reconstruida en un clon nuevo: T07…T25 coinciden con el registro, ruff limpio y pruebas de cada parche en verde | `evidencia/arbol_candidato/` |
| **CI local** | Los dos jobs de `ci.yml` sobre T25, en el clon nuevo | **python:** 2070 pruebas, 2060 pasan, 0 fallan, 10 saltadas, compuerta `pass` (536 s). **PostgreSQL:** 2070/2070, compuerta `pass`, alembic arriba/abajo/arriba sin errores. Son 2063 de T21 más las 7 nuevas (`evidencia/ci_local/`). La CI remota no la corrí y no afirmo nada de ella |

## 3. Riesgos abiertos y severidad

| Riesgo | Severidad | Estado |
|---|---|---|
| P29: el vivo direccional supone la comisión en la cotización | **Alta para el vivo** (inoperable; falla cerrado) | Bloquea Testnet y dinero real |
| P28 sin verificar contra el exchange (el rechazo `LOT_SIZE` es documentación, no observación) | Media | Requiere Testnet (C) |
| P30: carrera del *lease* entre verificar y registrar | Media | Propuesta (migración) |
| Parches 23–25 sin medida de mutación | Media | Solo tienen la prueba sin y con corrección, escrita por mí: no es evidencia independiente |
| P25: CI roja ~18 min por día sin defecto | Baja-media | Mitigación operativa |
| E3R: contaminación declarada (el período es conocido) y resultado único | Inherente | Declarado en la v3 §1 y en el plan; ninguna clasificación autoriza capital |

## 4. Nuevas oportunidades

- **E3R** (P31): la de más valor por unidad de esfuerzo. Son 10–20 minutos de cómputo, decide la línea C5 y, con ella, las extensiones diferidas (funding transversal, CTREND).
- **P35:** un ejecutor en papel para la cartera transversal, **solo** si E3R da RESPALDADA.
- **P29 b + P30:** solo como precondición de Testnet, y Testnet solo con una hipótesis respaldada.
- **Razones para no hacer cosas:** P34.

## 5. Hipótesis: cuáles siguen y cuáles no

Detalle en P32.
- **Ninguna de las 15 probadas merece seguir con datos históricos.**
- **T** sigue solo por la vía prospectiva (T-papel), sin trabajo hasta el 2027-04-18.
- **E3-H1/H2** merecen su prueba única.
- **E3-H3** solo se habilita si la base da RESPALDADA.
- **H-XS-REV-1** (P19), después de E3-H1 y con datos que no se superpongan.

## 6. Experimento recomendado y por qué

**La ejecución única de E3-H1/H2 con la v3 + Adenda R + R1′ + Adenda R2 (opción B).**
- Plan, criterios y autorización exacta: `E3R/PLAN_EJECUCION_UNICA_E3R.md`.
- Cada elemento del §6 de la misión tiene su fuente fijada: hipótesis falsable, universo, datos, separación, referencia, costos, latencia, ejecuciones parciales, datos faltantes, métricas, potencia, controles de multiplicidad y criterios de continuar o descartar.

**Por qué B y no A:**
- la regla (ii) protege el universo elegible, y los apalancados nunca lo son;
- la elección es ciega al resultado;
- la potencia para un IC de 0,02 sube de 0,35–0,56 a 0,54–0,79.

**Su costo:** el precedente de corregir una regla después de ver qué ventana produce. Está escrito, y A sigue disponible.

**Qué decide** (fijado antes de ver datos):
- RESPALDADA → papel y ventana ciega, cada una con autorización aparte;
- INFORMACIÓN SIN VENTAJA o VENTAJA NO ROBUSTA → como mucho, papel informativo;
- EN CONTRA, INSUFICIENTE, NO CONCLUYENTE o INVÁLIDO → se cierra la línea C5 y se pausa la investigación histórica hasta T-papel.

## 7. Decisiones autónomas y sus fundamentos

- **Preparar E3R pero no ejecutarlo.** Consume una prueba única e incorpora reglas nuevas (las adendas): es categoría B, y el cierre de E3 exige autorización expresa.
- **Mantener R1 literal como resultado oficial de P0 y presentar R1′ como opción.** Así no corrijo en silencio una regla congelada; la elección queda en tus manos, por escrito.
- **Corregir P26, P27 y P28 (categoría A).** Son locales, con prueba que falla sin la corrección, y cierran riesgos concretos de pérdida de protección o de duplicación.
- **No implementar P25, P29 ni P30 ahora.**
  - P25 tiene costo alto y no es un riesgo de seguridad.
  - P29 y P30 son diseño y migración (B/C), y no están en el camino crítico mientras no haya una hipótesis respaldada.
- **Borrar mis archivos de prueba de las guardas del modo real.** Uno era una autorización casi completa, y no conviene que circule. Su resultado quedó registrado en `CONGELACION_ORQUESTADOR.txt`.
- **Clasificar las 18 hipótesis y recomendar no continuar ninguna con datos históricos**, salvo E3-H1/H2.

## 8. Artefactos reproducibles

- `reproducir_DT.sh`: reconstruye T25 desde `72ffae5` con este paquete y compara cada árbol con `registro/`.
- `parches/`: 01–15 y 16–22 (idénticos a la entrega anterior) y 23–25 (`CADENA_DT.txt`).
- `E3R/`:
  - adendas congeladas y sus registros;
  - P0 con los dos resultados;
  - orquestador congelado, sus pruebas sintéticas y su congelación;
  - plan y autorización.
- `evidencia/`: corridas sin y con cada corrección, sondas, armado del candidato y CI local.
- `herramientas/`: los scripts de cadena, candidato y CI. Tienen las rutas absolutas del entorno; para otro lado se usa `reproducir_DT.sh`.
- `MANIFEST.sha256` y `VERIFICACION_FINAL.txt`.

## 9. Autorizaciones necesarias

| Acción | Categoría | Qué hace falta |
|---|---|---|
| Ejecución única de E3R | B (consume la prueba única y adopta las adendas) | La frase y la opción A o B (`E3R/PLAN_EJECUCION_UNICA_E3R.md` §5) |
| Integrar los parches 23–25 (o toda la cadena 01–25) al repositorio | C | Autorización de commit/push/PR, con la rama elegida |
| Testnet | C | Solo después de P29 b y P30, y con una hipótesis respaldada |
| Comisiones en BNB (P29 a) | C (política de producción) | Decisión sobre la cuenta |
| Mutación periódica en la CI (P20) | C | Autorización para tocar la CI |
| Ventana C (A4) y evaluación P | C | Solo si E3R da RESPALDADA |

## 10. Decisión final sobre la asignación de esfuerzo

1. **Primero, y casi todo el esfuerzo:** E3R, en cuanto lo autorices (≈ 20 min de cómputo), y su informe con la clasificación tal como salga.
2. **Después, según el resultado:**
   - si da RESPALDADA: P35 y la ventana C;
   - si no: cerrar C5, no abrir nuevas líneas históricas sin datos nuevos, y esperar a T-papel.
3. **Infraestructura del vivo:** solo integrar 23–25 (cuando lo autorices). Nada más hasta tener una hipótesis respaldada; recién entonces, P29 b, P30 y Testnet, en ese orden.

**Recomendación concreta:** autorizá la ejecución única de E3R con la opción B. Es la acción de mayor valor disponible: decide en una sola corrida si el programa tiene una línea viva con datos históricos, y no arriesga capital.

## Autocrítica (§9 de la misión)

- **R1 (Adenda R):** la redacté sin verificar la semántica de las listas por lunes, que son filtradas. Lo corregí con R1′, congelada aparte y opcional, en lugar de cambiar la regla congelada.
- **Orquestador:** tenía tres errores contra el protocolo congelado: el intervalo de H2 por una regla ya reemplazada, la semilla del diagnóstico de §5.4 y la falta de la validez del §10. Los encontré al contrastarlo con el texto, **antes** de congelarlo. Las pruebas sintéticas no los habrían detectado.
- **P16:** en el ciclo 1 la propuse con un mecanismo equivocado. En este ciclo anoté «P16 refutada por inspección», y era solo media verdad: la forma original no ocurre, pero el defecto real (P28) dejaba la posición sin stop. «Una orden aceptada no es protección en todo el ciclo de vida» aplica también a mis propias conclusiones.
- **Prueba de P28:** la primera versión no probaba nada, porque se abrió un corto. La precondición explícita la delató.
- **Operativo:** un `pkill -f` con un patrón que aparecía en mi propia línea de comando terminó mi shell. No hubo daño; queda anotado.
- **Límites de mi evidencia:**
  - las pruebas de 23–25 las escribí yo contra venues falsos, así que no son evidencia independiente;
  - la CI local en verde no es la CI remota, de la que no afirmo nada;
  - una simulación no es rentabilidad;
  - el comportamiento de Binance ante `LOT_SIZE` está documentado, pero no lo observé.
