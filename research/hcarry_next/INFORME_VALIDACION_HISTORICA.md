# H-CARRY Next — informe de la validación histórica (2026-10-16)

## 0. Conclusión

| Pregunta prerregistrada | Conclusión |
|---|---|
| **P1.** ¿UmbralFunding mejora de forma neta y robusta al carry permanente de rev. 5? | **EVIDENCIA INSUFICIENTE** |
| **P2.** ¿El carry permanente de rev. 5 tiene una ventaja económica neta? | **EVIDENCIA INSUFICIENTE** |

**Motivo: no hay ni un solo dato histórico verificable.**
- `data.binance.vision` sigue denegado por la política de red del entorno. Lo comprobé de nuevo a las 19:40 UTC: `CONNECT tunnel failed, response 403`.
- Las otras 21 fuentes probadas también están denegadas.
- No eludí la restricción: no usé el bucket S3 de detrás del dominio, ni espejos, ni CSV de terceros.

Por eso **no ejecuté el test final**. La conclusión no dice que la ventaja exista ni que no exista: dice que todavía no se midió.

**Lo que sí quedó listo:**
- descarga e importación verificables;
- informe de calidad con filtros de aceptación;
- prerregistro con hash y evaluador automático.

Todo está probado de extremo a extremo con archivos fabricados en el formato oficial. Cuando haya datos, la evaluación es un comando y se ejecuta **una sola vez** (§8).

## 1. Separación estricta de resultados

| Categoría | Qué hay | Dónde |
|---|---|---|
| **Histórico** (datos oficiales verificados) | **Nada.** La carpeta `experimentos/historico/resultados/historico/` no existe. | — |
| **Sintético** (datos fabricados; **no es evidencia económica**) | 1) Ensayo del pipeline completo (semilla 101). 2) Características operativas de la regla de decisión en 40 mundos. 3) Experimentos de la fase anterior. | `experimentos/historico/resultados/sintetico/`, `…/resultados/caracteristicas/`, `experimentos/sintetico/`, `experimentos/estres_v2/` |
| **Prospectivo** (datos posteriores al prerregistro) | **Nada.** No hay ninguna prueba prospectiva iniciada. | — |

La separación la impone el código, no la disciplina:
- el evaluador lee la procedencia del `MANIFIESTO.json` de los datos y elige la carpeta de salida;
- con datos sintéticos, la conclusión oficial es siempre EVIDENCIA INSUFICIENTE;
- los archivos fabricados llevan una marca en el zip que impide importarlos como históricos;
- cada informe sintético lleva el aviso «SINTÉTICO: no es evidencia económica» y la línea «Evidencia prospectiva: ninguna».

## 2. Datos: descarga, verificación y calidad (puntos 1 y 2)

### 2.1 Qué está preparado y verificado

| Paso | Comando | Qué garantiza |
|---|---|---|
| Descarga directa (vía 1) | `python -m hcarry descargar --destino datos/binance_vision --desde 2019-10 --hasta 2026-06` | Baja spot, perpetuo, mark, funding y, opcionalmente, el índice de prima, cada zip con su `.CHECKSUM` oficial. Verifica el SHA-256 de cada archivo y guarda los checksums. Es reanudable y nunca sobrescribe con contenido distinto. Un mes no publicado (404) queda anotado, no aborta. Manifiesto `historico_oficial`. |
| Importación de una copia (vía 2) | `python -m hcarry importar --origen COPIA --destino datos/binance_vision` | Vuelve a verificar cada zip contra su `.CHECKSUM` oficial. Rechaza los archivos sin checksum, los que no coinciden y las copias mezcladas. Si los archivos llevan la marca SINTÉTICO, los etiqueta como sintéticos. |
| Calidad | `python -m hcarry calidad --directorio datos/binance_vision --salida …` | Filtros C1–C6 prerregistrados (§3). Si falla alguno, la evaluación no simula nada. |
| Panel | (dentro del evaluador) | Verifica cada archivo contra el manifiesto («¿archivo alterado?»), usa el primer mes común de las series y bloquea el período reservado en el código. |

**Verificación de extremo a extremo con archivos fabricados** (no con datos reales):
1. Fabriqué 400 archivos con el formato oficial: spot sin cabecera y con marcas en microsegundos desde 2025, futuros con cabecera y funding con un desfase de milisegundos.
2. `importar`: 400 verificados y etiquetados `sintetico`.
3. `calidad`: apto.
4. Evaluador: 11 s.

El resultado está en `experimentos/historico/resultados/sintetico/datos_9992d8439a4d/`, con su `calidad.md`.

**No existe un informe de calidad de datos reales.** Los criterios con que se juzgarán están fijados (§3), pero sin datos no hay nada que informar.

### 2.2 Fuentes alternativas (detalle en `experimentos/historico/FUENTES_ALTERNATIVAS.md`)

- **Descartadas:**
  - el S3 de Binance, porque usarlo sería eludir la denegación;
  - los CSV de terceros (Kaggle, CryptoDataDownload, repositorios de GitHub), porque su procedencia no es verificable;
  - otras bolsas, porque son otro instrumento: cambiarían la pregunta.
- **Vías legítimas que quedan, todas con una acción tuya:**
  1. **Habilitar `data.binance.vision`** en *Network access → Allowed domains* del entorno. Es la recomendada: la descarga verifica contra el emisor.
  2. **Descargar en tu máquina** con el mismo código (solo biblioteca estándar) y aportar la carpeta en una rama del repositorio. Drive no es fiable para varios MB: la herramienta devuelve el contenido en base64 dentro de la conversación. Riesgo: una copia manipulada a la vez en datos y `.CHECKSUM` no se detectaría. Para reducirlo, comprobá al azar algunos hashes contra la web.
  3. **Un proveedor con clave** (por ejemplo, Tardis.dev): requiere credenciales y habilitar su dominio. No es necesario mientras exista la vía 1.

## 3. Parámetros y criterios fijados antes de ver datos (punto 3)

Prerregistro: `experimentos/historico/PRERREGISTRO_VALIDACION_HISTORICA.md`, SHA-256 `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd`. El evaluador lo verifica.

- **Datos:** BTCUSDT 1 h; spot, perpetuo, mark y funding (prima opcional). Desde el primer mes común (≥ 2019-10) hasta 2026-06-01. El período reservado es inaccesible.
- **Filtros (si falla uno, la conclusión es EVIDENCIA INSUFICIENTE sin simular):**
  - C1: checksums;
  - C2: meses completos;
  - C3: ≤ 0,5 % de horas rellenadas y rachas ≤ 24 h;
  - C4: funding sin A2, A2b, A4, A7 ni A8;
  - C5: coherencia; mediana de |F/S − 1| ≤ 0,2 % y p99 de |M/F − 1| ≤ 1 %;
  - C6: fuera del período reservado.
- **Divisiones:** desarrollo 2019-10 → 2022-12 · validación 2023-01 → 2024-01 · test 2024-02 → 2026-05 (la ventana de rev. 5).
- **Políticas:**
  - rev. 5 = `Siempre`, ρ = 1, banda (0,5; 1,5), regla «omitir»;
  - UmbralFunding = ventana de 21 eventos, entrada al 10 % anual, salida al 3 %, permanencia de 72 h. **Sin optimizar con datos reales.**
- **Motor:** 10 000 USDT; margen de mantenimiento del 1 %; apalancamiento máximo 2.
- **Costes base:** spot 10 + 5 bps; perpetuo 5 + 5 bps (comisión de tomador minorista + slippage, como en rev. 5).
- **Sensibilidades en test:** costes ×0,5, ×2 y ×3; retraso de 1 h y de 3 h; pata del perpetuo adversa; funding ×0,75; nocional mínimo del perpetuo.
- **Diagnóstico previo, solo en desarrollo:** persistencia del funding. Predicción escrita: si la correlación es < 0,2, UmbralFunding no aportará.
- **Estadística:** bootstrap circular por bloques de 30 días, 2 000 remuestreos, semilla 20261016.
- **Criterios:**
  - **P1 VENTAJA RESPALDADA** exige todo esto:
    - datos aptos;
    - en test:
      - PnL de umbral mayor que el de rev. 5;
      - P(dif > 0) ≥ 0,95;
      - caída de umbral ≤ caída de rev. 5 + 5 pp, sin liquidaciones;
      - umbral sigue mejor con costes ×2, con pata adversa y con retraso de 3 h;
    - en validación, umbral ≥ rev. 5.
  - **NO RESPALDADA** si en test la diferencia es ≤ 0 o P < 0,5.
  - En otro caso, **INSUFICIENTE**.
  - **P2:** VENTAJA RESPALDADA si el CAGR en test es > 5 % y sigue > 0 con costes ×2; NO RESPALDADA si es ≤ 0.

**Adenda (sin cambios en criterios ni cálculos):** después del prerregistro el código cambió por la corrección de una etiqueta (§6) y por lint. Huella `2e35b68f…` → `68ddc304…`. Con el código actual, el ensayo sintético se reproduce **bit a bit** en desarrollo, validación, test, sensibilidad y bootstrap. Está registrado en la adenda del prerregistro.

## 4. rev. 5 frente a UmbralFunding en condiciones idénticas (punto 4) — **SINTÉTICO**

> **Todo lo de esta sección es sintético y no es evidencia económica.** Sirve para dos cosas: comprobar que el pipeline y la regla funcionan, y saber qué puede y qué no puede detectar la regla cuando lleguen los datos reales.

**Condiciones idénticas** (las impone el evaluador): mismos datos y horas, mismo motor, capital, ρ, banda, costes, regla ante lo inviable y mismas sensibilidades. Solo cambia la política. Las diferencias diarias se emparejan día a día.

### 4.1 Ensayo del pipeline completo (mundo base, semilla 101)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación anual |
|---|---|---|---|---|---|---|---|
| desarrollo | rev. 5 | 7,08 % | 5,68 % | 2 584 | 79 | 100 % | 1,8 |
| desarrollo | umbral | 10,76 % | 0,75 % | 4 283 | 409 | 75 % | 8,5 |
| validación | rev. 5 | 15,62 % | 2,22 % | 1 741 | 42 | 100 % | 2,8 |
| validación | umbral | 17,58 % | 0,38 % | 1 981 | 93 | 80 % | 6,1 |
| **test** | **rev. 5** | **4,16 %** | 0,68 % | 1 059 | 57 | 100 % | 1,9 |
| **test** | **umbral** | **3,30 %** | 0,36 % | 1 030 | 283 | 88 % | 9,4 |

- **Bootstrap en test** (umbral − rev. 5): −0,83 pp anuales; intervalo del 90 % [−1,47; −0,15] pp; P(> 0) = 0,0225.
- **Sensibilidad:** umbral pierde en los 8 escenarios. Con costes ×3 la diferencia de PnL es de −665 USDT y con pata adversa, de −496.
- **Conclusión oficial:** EVIDENCIA INSUFICIENTE, por ser sintético. En sombra, la regla habría dicho HIPÓTESIS NO RESPALDADA.

Este mundo muestra una trampa real: umbral gana en desarrollo y validación y pierde en test. Lo que decide es si en el test hay episodios largos de funding negativo, no la calidad de la regla.

### 4.2 Características operativas de la regla (40 mundos; `resultados/caracteristicas/RESUMEN.md`)

Cada mundo recorrió el pipeline real. Los mundos **nulos** son el mismo mundo con el funding barajado en el tiempo: no tienen persistencia, que es justo lo que UmbralFunding necesita.

| Grupo | Mundos | En sombra: VENTAJA | NO RESPALDADA | INSUFICIENTE | Persistencia (7 d) |
|---|---|---|---|---|---|
| base | 12 | **6** | 1 | 5 | +0,73 |
| base NULO | 12 | **0** | 12 | 0 | +0,00 |
| bajista suave | 8 | 0 | 5 | 3 | +0,62 |
| bajista suave NULO | 8 | **0** | 8 | 0 | −0,01 |

**Lectura:**
1. **Falsos positivos: 0 de 20 mundos nulos.** Por la regla del tres, la tasa es ≤ ~14 % con un 95 % de confianza. En los 20 mundos nulos la regla concluyó NO RESPALDADA.
2. **Potencia limitada.** En el mundo base el generador tiene el mecanismo por construcción (unos +5 pp en la ventana completa), y aun así la regla lo declaró solo en 6 de 12 mundos. Las otras veces lo impidieron la validación (2 mundos con P ≥ 0,98), una P < 0,95 con algún estrés fallido (3) o una diferencia negativa en la ventana de test (1). **Con datos reales, una ventaja modesta muy probablemente acabaría en EVIDENCIA INSUFICIENTE.** Es el precio de la exigencia, y está fijado a priori.
3. **La predicción del diagnóstico previo acierta en un solo sentido.** Con persistencia < 0,2 (los 20 nulos), umbral nunca aportó. Pero una persistencia alta no basta: en el bajista suave es de +0,62 y umbral no gana (mediana −13 USDT), porque el funding negativo es poco profundo y no paga la rotación.
4. **P2 en sombra:** VENTAJA en 12 de 20 mundos normales y en 13 de 20 nulos. El carry permanente no depende de la persistencia, sino del nivel medio del funding.

## 5. Costes y drawdown — **SINTÉTICO** (medianas en test, costes base)

| Grupo | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación anual | Liquidaciones |
|---|---|---|---|---|---|---|---|---|
| base | rev. 5 | 5,77 % | 5,65 % | 1 472 | 63 | 100 % | 2,0 | 0 |
| base | umbral | 7,94 % | 0,56 % | 2 162 | 282 | 75 % | 8,9 | 0 |
| base NULO | rev. 5 | 5,37 % | 0,43 % | 1 353 | 70 | 100 % | 2,2 | 0 |
| base NULO | umbral | **−1,25 %** | 3,89 % | 781 | **969** | 69 % | **34,1** | 0 |
| bajista suave | rev. 5 | 11,14 % | 1,47 % | 2 876 | 70 | 100 % | 2,2 | 0 |
| bajista suave | umbral | 10,65 % | 0,94 % | 2 939 | 331 | 80 % | 10,2 | 0 |
| bajista suave NULO | rev. 5 | 8,05 % | 0,28 % | 2 041 | 78 | 100 % | 2,4 | 0 |
| bajista suave NULO | umbral | 6,67 % | 0,83 % | 2 067 | 555 | 90 % | 17,5 | 0 |

**Sensibilidad.** Diferencia de PnL umbral − rev. 5 (mediana), con el número de mundos en que es > 0:

| Grupo | base | costes ×0,5 | ×2 | ×3 | retraso 1 h | 3 h | pata adversa | funding ×0,75 |
|---|---|---|---|---|---|---|---|---|
| base | +649 (11/12) | +759 (11/12) | +439 (8/12) | +233 (7/12) | +641 (11/12) | +646 (11/12) | +339 (8/12) | +253 (8/12) |
| base NULO | −1 257 (0/12) | −806 | −2 095 | −2 844 | −1 261 | −1 271 | −2 465 | −1 175 |
| bajista suave | −13 (3/8) | +126 (5/8) | −267 (1/8) | −475 (1/8) | −9 (4/8) | −6 (4/8) | −427 (0/8) | −135 (3/8) |
| bajista suave NULO | −603 (0/8) | −392 | −1 032 | −1 516 | −589 | −608 | −1 296 | −585 |

**Lectura de costes y riesgo:**
- **Lo que paga UmbralFunding.** Su coste es la rotación: de 4 a 14 veces los costes de rev. 5. Cada ida y vuelta cuesta 50 bps del nocional. Sin persistencia entra y sale sin parar y pierde (−1,25 % de CAGR en los nulos base). Es la política más sensible a los costes y a la pata adversa. **El supuesto de costes es decisivo:** con ×2, la ventaja mediana del mundo base cae un tercio.
- **Lo que compra.** Menor caída cuando hay episodios largos de funding negativo (base: 0,56 % frente a 5,65 %). Sin ellos, la caída es igual o mayor.
- **rev. 5.** Caídas medianas de 0,3–5,7 % en test y ninguna liquidación en ningún escenario. Con ρ = 1, la liquidación está a un salto del +48,5 % desde el borde de la banda. Su riesgo no es la liquidación sino rendir por debajo del comparador del 5 %. Las cifras de D1–D4 de rev. 5 (reconstrucción, regla R0) en test sintético: descartada en 3, no descartada en 7 y sin veredicto en 10 de 20 mundos normales.
- **Retrasos de 1–3 h:** efecto despreciable en ambas. El nocional mínimo del perpetuo (5 USDT) no cambia nada con 10 000 USDT de capital.

## 6. Defectos encontrados y corregidos en el entorno aislado (punto 6)

Todos con pruebas. Ninguno afecta a los recuperados ni a las simulaciones previas.

| Defecto | Por qué impedía una evaluación válida | Prueba |
|---|---|---|
| Cualquier carpeta con formato oficial se etiquetaba «binance_vision» | Un ensayo sintético podía pasar por histórico | `test_pipeline_datos.py` (procedencia) |
| El panel no verificaba los archivos contra el manifiesto | Un archivo alterado después de la descarga no se detectaba | ídem (alteración) |
| `cargar_datos` registraba todo lo oficial como «datos reales» | El registro del laboratorio mezclaba categorías | ídem (registro) |
| `importar` podía etiquetar archivos fabricados como históricos | Se resolvió con la marca SINTÉTICO y su detección | ídem (importación) |
| Un 404 abortaba la descarga y no se guardaban los `.CHECKSUM` | No había verificación reproducible ni descarga completa | ídem (404 y reanudación) |
| Un `.CHECKSUM` mal formado se reintentaba como un error de red | Esperas inútiles y un error enmascarado | ídem |
| **Nuevo en esta sesión:** `importar` escribía `via: "copia aportada por el usuario"` también para archivos fabricados | Atribución falsa en los manifiestos e informes sintéticos | `test_importar_verifica_los_checksums_y_declara_la_via` |

Sobre el último: el primer ensayo (`resultados/sintetico/datos_5be948c0fb03/`) quedó con esa etiqueta falsa. **Lo conservo tal cual, con un `ERRATA.md`**, y lo repetí en `datos_9992d8439a4d/` con el código corregido: los resultados son idénticos.

## 7. Incertidumbres y limitaciones

1. **Sin datos históricos, nada de lo anterior estima la rentabilidad real.** El generador da persistencia al funding por construcción. La ventaja sintética de UmbralFunding puede ser un artefacto del generador. Lo único que se transfiere a los datos reales es lo que se sabe de la *regla*: no inventa ventajas en mundos sin persistencia y tiene una potencia aproximada del 50 % cuando la ventaja existe y es grande.
2. **Una sola ventana de test** (unos 28 meses). Basta para descartar, pero es escasa para confirmar. Si el test histórico da EVIDENCIA INSUFICIENTE, solo hay dos fuentes de datos nuevos: el período reservado, con tu autorización, o una prueba prospectiva. **No se repite el test.**
3. **Costes supuestos, no medidos:** comisión de tomador minorista y slippage de rev. 5. Con costes de creador o descuentos por volumen, UmbralFunding mejoraría (costes ×0,5); con libro de órdenes fino, empeoraría. Sin datos de ejecución no se puede calibrar.
4. **Riesgo de liquidación real no modelado:** tramos de margen, ADL, liquidación dentro de la hora, caídas del exchange. Con ρ = 1 el margen es amplio, pero el modelo no captura esos eventos.
5. **Interés y tope del funding** recordados de la documentación (supuesto S1 de rev. 5), no verificados contra la API.
6. **Reconstrucción ≠ código congelado de rev. 5.** Reproduce exactamente las cifras documentadas, pero su veredicto D1–D4 no sustituye al de rev. 5.
7. **El prerregistro no es independiente:** lo escribió el mismo agente que construyó el generador y vio los resultados sintéticos. Los parámetros de UmbralFunding se fijaron en la fase anterior, con datos sintéticos. No hay riesgo de sobreajuste a datos reales (no se vieron), pero sí de que estén ajustados al generador.
8. **Vía 2:** su procedencia depende de la integridad de la copia aportada (§2.2).

## 8. Qué falta para una conclusión real

1. **Acción tuya:** habilitar `data.binance.vision` (vía 1) o aportar la copia por una rama del repositorio (vía 2). Especificación exacta y lista de los 800 archivos en `experimentos/historico/REQUISITOS_DATOS_HISTORICOS.md`; procedimiento en `experimentos/DATOS_REALES.md`. Si cambiar la red reinicia el contenedor, se pierde todo lo no versionado: **guardá antes el ZIP adjunto.**
2. Después, desde `research/hcarry_next` con `PYTHONPATH=src`:
   ```
   .venv/bin/python -B -m hcarry descargar --destino datos/binance_vision --desde 2019-10 --hasta 2026-06   # o importar
   .venv/bin/python -B -m hcarry calidad   --directorio datos/binance_vision --salida experimentos/historico/calidad.md
   .venv/bin/python -B -m hcarry historico --datos datos/binance_vision
   ```
   Si la calidad no es apta, el resultado es EVIDENCIA INSUFICIENTE y no se simula. Si es apta, el test se ejecuta una vez y la conclusión sale de los criterios de §3.
3. **Prospectivo:** solo con datos posteriores al prerregistro, simulado y sin operar. No se ha iniciado.

## 9. Qué cambió en el entorno aislado en esta fase

Todo está en `research/hcarry_next/`, sin versionar.
- **No hubo** commits, pushes, despliegues ni operaciones de trading.
- No se tocó producción ni se interrumpió ningún proceso ajeno.
- `recuperado/` sigue intacto (`SHA256SUMS` verificado), igual que las simulaciones previas.

- **Nuevos:**
  - `src/hcarry/data/fabricar.py`, `src/hcarry/data/calidad.py`, `src/hcarry/lab/historico.py`;
  - `tests/test_pipeline_datos.py`, `tests/test_historico.py`;
  - `experimentos/historico/` (fuentes, prerregistro con adenda, scripts de caracterización, resultados sintéticos);
  - este informe.
- **Modificados:**
  - `src/hcarry/data/binance_vision.py` (procedencia, verificación, importación, descarga reanudable, etiqueta `via`);
  - `src/hcarry/lab/experimento.py`, `src/hcarry/__main__.py`;
  - lint en `analisis.py`, `sintetico.py` y `historico.py` (sin efecto en cálculos, verificado);
  - `README.md`, `DECISIONS.md` (D-14 a D-16), `CHANGELOG.md` (0.2.0 y 0.2.1), `experimentos/DATOS_REALES.md`.
- **Pruebas:** 78, todas pasan. `ruff` sin avisos.
