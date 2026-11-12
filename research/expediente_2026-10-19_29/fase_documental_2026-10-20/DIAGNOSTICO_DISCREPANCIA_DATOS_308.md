# Diagnóstico de la discrepancia de los «308 archivos»

**Fecha:** 2026-10-20. **Método:** solo lectura de manifiestos, datos en disco, paquetes de preservación e historial de la sesión. No se descargó nada, no se modificó ningún manifiesto y no se ejecutó ninguna estrategia. La evidencia está en `evidencia/04_manifiestos.txt` y `evidencia/05_308.txt`, y los listados de los paquetes en `evidencia/lista_paquete_v1.txt` y `evidencia/lista_paquete_v2.txt`.

## 1. Dictamen
**Resuelta.** «308» es la suma exacta de dos conjuntos de archivos de **precios spot** que los manifiestos **versionados** en git enumeran y que `research/.gitignore` excluye **a propósito** del repositorio:

| Conjunto | Proyecto | Archivos | Detalle |
|---|---|---|---|
| Velas diarias de BTCUSDT y ETHUSDT (spot 1d, mensuales) | **T** | **212** (106 + 106) | `tendencia_btc/datos/{BTCUSDT,ETHUSDT}/MANIFIESTO.json`; meses de 2017-08 a 2026-05 |
| Velas horarias de BTCUSDT (spot 1h) | **H-CARRY** (los mismos archivos usó E1) | **96** (80 mensuales + 16 diarios de complemento) | Entradas `tipo = spot` de `hcarry_next/datos/binance_vision/MANIFIESTO.json`; de 2019-10 a 2026-05 |
| **Total** | | **308** | |

**Los dos diagnósticos describen alcances distintos y son compatibles:**
- **«Faltan 308 archivos»** es cierto en **un clon del repositorio**, local o GitHub. Los manifiestos están versionados (también en el remoto `c6339e3`), pero los `.zip` y `.CHECKSUM` no. En git solo hay 3 zips, todos entregas de H-CARRY. *Inferencia:* el diagnóstico se habría hecho sobre el repositorio o un clon, comparando los manifiestos con los archivos presentes.
- **«Los datos están completos y coinciden con sus manifiestos»** es cierto **en este entorno**. Los 308 archivos existen, su SHA-256 coincide con el manifiesto y coincide con el `.CHECKSUM` oficial de Binance (`evidencia/05_308.txt`: `ok` en 106 + 106 + 96).

**El diagnóstico «308 faltantes» no es de esta sesión.** En todo el historial accesible, la cifra aparece **solo en tus mensajes** del 2026-10-20 («308 precios» y «308 archivos»), nunca en respuestas ni en salidas de herramientas. La aclaración de que los datos estaban completos sí es de esta sesión (`../auditoria_T_REV_EMA9/`). **No pude verificar quién produjo el «308 faltantes», con qué alcance ni en qué fecha:** la fuente no es accesible desde este entorno.

## 2. Verificación detallada

### 2.1 Manifiestos (SHA-256 completo; ruta relativa a `research/`)

| Manifiesto | SHA-256 | Archivos | En disco |
|---|---|---|---|
| `tendencia_btc/datos/BTCUSDT/MANIFIESTO.json` (T) | `5a0805a7e22797637c400a1e939ec6c2d10e0cdc26410566f212708211b6367b` | 106 spot 1d | 106 coinciden; 0 faltan |
| `tendencia_btc/datos/ETHUSDT/MANIFIESTO.json` (T) | `3998305bb38909a08a94f6365317695f930dea4ea10933b19a22e17b40998f6a` | 106 spot 1d | 106 coinciden; 0 faltan |
| `hcarry_next/datos/binance_vision/MANIFIESTO.json` (H-CARRY) | `8bdabde706bffadca3f4b7ca39937bff14a95ab3ecdc77707bfe4bb434f381d1` | 412: spot 96, perp 77, mark 85, premium 77, funding 77 | 412 coinciden; 0 faltan |
| `hcarry_next/datos/MANIFIESTO_solo_mensual.json` (H-CARRY, variante sin complementos diarios) | `7c08ac3dec404465d23301c39de91bd9d0ea3b643cdaebffabe857b2f219d283` | 388 | 388 coinciden, con rutas relativas a `datos/binance_vision/` |
| `tendencia_btc/datos_papel/BTCUSDT/MANIFIESTO.json` (papel) | `efb175d92032b03c996ef013f5b3f3e0d328d9a253c20c983b3368236ea02022` | 180 spot 1d diarios (2026-04-20 → 2026-10-16) | 180 coinciden |
| `tendencia_btc/datos_papel/ETHUSDT/MANIFIESTO.json` (papel) | `6aa31937ed02503d27978eaeb82012ea2920ffae5e79ceb13d655353bc7fda49` | 180 | 180 coinciden |
| `tendencia_btc/datos_papel/funding_BTCUSDT/MANIFIESTO.json` (monitor del carry) | `f3a0e5f85a3f97a37c589575433c601b6d87289f5e38860998f45ab082a4ab50` | 3 fundingRate | 3 coinciden |
| `tendencia_btc/datos_multi/MANIFIESTO.json` (**T-MULTI**) | `c64f3bf4c055aad4af6ecde32b30cca0dc42a3728580647d92644805514fb4ad` | 36 respuestas (Yahoo 12, Nasdaq 24) | 36 coinciden; `evidencia_t_multi.py verificar` sin diferencias |

**Nota sobre una lectura errónea mía.** En la primera pasada de `evidencia/04` el manifiesto `MANIFIESTO_solo_mensual.json` mostró «faltan = 388». La causa fue que se resolvieron sus rutas contra `hcarry_next/datos/`. Resueltas contra `datos/binance_vision/`, como corresponde, coinciden las 388 (`evidencia/05_308.txt`). **No es un faltante.**

### 2.2 T, T-MULTI y H-CARRY: mismos símbolos, períodos y archivos

| | T | T-MULTI | H-CARRY / E1 |
|---|---|---|---|
| Fuente | data.binance.vision (oficial) | Yahoo y Nasdaq (no oficiales; no se pueden volver a bajar idénticos) | data.binance.vision (oficial) |
| Símbolos | BTCUSDT y ETHUSDT spot | 11 ETF + 1 de contraste | BTCUSDT spot (1h), perpetuo, mark, premium y funding |
| Intervalo | 1d | Sesión diaria | 1h (spot y perp), 8h (funding) |
| Período | 2017-08 → 2026-05 | 2011-01 → 2026-09 | 2019-10 → 2026-05 |
| ¿Entra en los 308? | **Sí (212)** | **No** | **Sí: solo spot 1h (96)** |

**Comprobaciones adicionales:**
- **Superposición:** los 96 archivos horarios de **E1** (`manifiesto_datos.json` de E1, huella de la lista `4931ee70…a7ba9`) son **los mismos nombres y los mismos SHA-256** que los 96 spot de H-CARRY.
- **Paquete de preservación v2** (`trader-ia_preservacion_2026-10-18_v2.tar.gz`, SHA-256 `171ef216667d896085ca314a7df3f758ddda25e0a52ecea7b8d5eb6a728f4450`, igual al registrado): **contiene** los 212 + 96. En total trae 1137 zips: 212 de T 1d, 96 spot 1h, 316 de futuros de H-CARRY, 363 del papel, 146 de otros símbolos y 4 entregas.
- **Paquete v1** (`trader-ia_preservacion_2026-10-18.tar.gz`): 52 entradas y **0 zips**. No incluía ningún dato de Binance; la v2 lo corrigió.

### 2.3 Archivos completos frente a velas completas (no confundir)
- **T (1d):** 0 días faltantes en 3210 por activo (auditoría anterior).
- **Spot 1h de BTCUSDT (H-CARRY / E1):** los 96 **archivos** están completos, pero **dentro** de los datos faltan **38 de 58 440 velas horarias** (19 huecos de 5 h como máximo). Además, 3 horas en conflicto entre el archivo mensual y el diario se excluyeron. Fuente: `resultados/real/manifiesto_datos.json` de E1, leído, no recalculado.
- **Esto no es un faltante de archivos.** Pero es relevante para cualquier experimento horario, como H-EMA9-VWAP: hay que tratarlo sin rellenar (ver la propuesta).

## 3. Qué queda sin poder verificarse
- El origen, el autor, la fecha y el alcance exacto del diagnóstico «308 faltantes». No está en ninguna fuente accesible: repositorio, historial de la sesión, scratchpad, paquetes ni Google Drive. Gmail no estaba disponible: requiere volver a autorizar el conector en claude.ai.
- Si ese diagnóstico se refería a precios dentro de los archivos y no a archivos. Si fuera así, la cifra no coincide con ningún recuento: T tiene 0 velas faltantes, el horario 38 y sumados 38.

## 4. Consecuencias
- **Para T:** ninguna. Sus datos están completos y verificados; la incidencia queda **cerrada**.
- **Para reproducir desde un clon limpio:** los 308 archivos (y los demás datos no versionados) hay que obtenerlos del paquete v2 o volver a bajarlos de data.binance.vision y verificarlos contra los manifiestos versionados. **No se hizo, ni hace falta en esta fase.**
