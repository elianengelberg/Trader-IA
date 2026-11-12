# Cierre de la auditoría de T (2026-10-20)

**Alcance.**
- Se verifican y preservan los artefactos de la ejecución histórica única de T fuera de muestra y del protocolo en papel.
- **No se recalculó ninguna rentabilidad.** No se ejecutó el script de uso único ni ninguna copia suya, y no se escribió nada en el repositorio.
- Toda la evidencia citada está en `evidencia/` (archivos 01–03), dentro de esta misma carpeta.

## 1. Estado del repositorio al auditar (`evidencia/01_estado_git.txt`)
- **HEAD:** `692f2b2d7af3189027b62e60367d104d855b0f3f`, en la rama `claude/algo-trading-simulation-platform-ngf7xo`.
- **Remoto:** `origin` está en `c6339e3fcd6041cb6c4ad7f5545f0ff306a4fd2f`. El local va **2 commits por delante** (`f518ac1` y `692f2b2`) y 0 por detrás.
- **Los artefactos del fuera de muestra viven en `692f2b2`, que solo existe en local:** su congelado no es verificable desde fuera mientras no se publique.
- **8 cambios preexistentes sin commit**, que no se tocaron. Sus hashes están en `evidencia/01`:
  - 3 modificados: `research/.gitignore`, `ARTEFACTOS_SHA256.txt` y `papel/PRERREGISTRO_PAPEL.md`;
  - 5 no seguidos: `datos_multi/nasdaq/`, `datos_multi/yahoo/`, `VERIFICACION_OPERATIVA_2026-10-17.md`, `papel/corte.py` y `tests/test_papel_corte.py`.

## 2. Artefactos de la ejecución fuera de muestra: SHA-256 completos (`evidencia/03_T_fuera_de_muestra.txt`)

| Artefacto (en `research/tendencia_btc/`) | SHA-256 actual | Registrado en el resultado | Registrado en `EVIDENCIA_T_MULTI.json` | Igual a HEAD |
|---|---|---|---|---|
| `PRERREGISTRO_FUERA_DE_MUESTRA_T.md` | `94a165560ba2a1807bf604b079dbf2c8eea7e7e4401fcc5ccb5db275464db58f` | **=** | **=** | sí |
| `experimentos/fuera_de_muestra_T.py` (script de una sola ejecución) | `941b6e11f6566319b93614ee671b184d60c7b5fbc64a3931a6ff2c8da17fe0fa` | **=** | **=** | sí |
| `experimentos/fuera_de_muestra_T.json` (resultado) | `4f8fafde372931aab29b94612eb658f5fac9259e51cdf7dace7a1b30fc633c45` | — | **=** | sí |
| Código de decisión `src/tendencia/*.py` (huella) | `73b22f3e3a8f21513d5533fb11a7553becae30b87c8736fb6880bccc36c11d2b` | **=** | **=** (`regla_T`) | sí |
| `datos/BTCUSDT/MANIFIESTO.json` | `5a0805a7e22797637c400a1e939ec6c2d10e0cdc26410566f212708211b6367b` | **=** | **=** | sí |
| `datos/ETHUSDT/MANIFIESTO.json` | `3998305bb38909a08a94f6365317695f930dea4ea10933b19a22e17b40998f6a` | **=** | **=** | sí |
| `INFORME_FUERA_DE_MUESTRA_T.md` | `08fa977b76fc03fe9934c237f02f83c9acc3e598960a753d78646969460d5621` | — | **=** | sí |
| `REVISION_CRITICA_FUERA_DE_MUESTRA_T.md` | `836d8ee38873331c3b139aaf247e45f36a888aa7eb20e9f6461f7794fc5b6c7f` | — | **=** | sí |
| `experimentos/revision_fuera_de_muestra_T.py` | `649c03e00f61f1854e1b651b4e3bc0f3dd0e1422cf71e48311e6593faae51898` | — | **=** | sí |
| `experimentos/revision_fuera_de_muestra_T.json` | `ccb8fcc73260e1207098ab28d568deac1841c98dae49a0b74415e91f01123630` | — | **=** | sí |

**Correspondencia entre lo que se usó y lo que se registró:**
- El resultado guarda los hashes del prerregistro, el script, el código y los dos manifiestos con los que se ejecutó. **Los cinco coinciden con los archivos actuales.**
- `EVIDENCIA_T_MULTI.json` (`experimentos/evidencia_t_multi.py verificar`, solo lectura) da «**secciones distintas: ninguna; datos crudos faltantes o distintos: ninguno (36 archivos)**» (`evidencia/02`).
- **Datos:** los 212 archivos diarios (106 de BTC y 106 de ETH, de 2017-08 a 2026-05) coinciden con su manifiesto y con el `.CHECKSUM` oficial (`evidencia/05_308.txt`).
  - Según la auditoría anterior (`../auditoria_T_REV_EMA9/resultado_verificacion.json`): 3210 días por activo, **0 faltantes**, 1612 días dentro de la ventana.

**Salvaguarda de uso único.**
- `fuera_de_muestra_T.py` termina con «ya existe: el prerregistro permite una sola ejecución» si el resultado existe.
- **No se ejecutó ni se copió para eludirla.**

## 3. Métricas registradas, verificadas contra `experimentos/fuera_de_muestra_T.json`

| Cifra informada antes | Valor en el JSON original | ¿Coincide? |
|---|---|---|
| Exceso anual del conjunto **+7,0 %** | `0.07048894365406465` | sí (+7,05 %) |
| IC90 **−8,8 % / +22,9 %** | `[-0.08820041316896611, 0.22869689090470152]` | sí |
| P(exceso > 0) **0,755** | `0.755` | sí |
| Período **2022-01-01 → 2026-05-31** | `ventana = ["2022-01-01", "2026-06-01"]` (fin exclusivo), `dias = 1612` | sí |
| Activos **BTC y ETH spot** | Bloques `BTC` y `ETH`; datos `spot/monthly/klines/{BTCUSDT,ETHUSDT}/1d` | sí |
| **Conclusión: EVIDENCIA INSUFICIENTE** | `decision_prerregistrada = "EVIDENCIA INSUFICIENTE"` | **sí: sigue registrada** |

**Otras cifras registradas (solo lectura del JSON; descriptivas, no cambian la decisión):**
- **BTC:** +9,12 %/año, IC90 −6,73 % / +24,95 %, P = 0,8355.
- **ETH:** +4,98 %/año, IC90 −13,35 % / +23,68 %, P = 0,6495.
- **Estrés, exceso del conjunto:** costes ×2 +4,38 %; costes ×3 +1,71 %; un día de retraso +7,67 %.
- **Nulo por desplazamiento circular (BTC):** percentil 0,869.
- **Subventanas, conjunto:** 2022–2023 +7,03 % (P 0,694); 2024-01 → 2026-05 +5,91 % (P 0,684).
- **Replicación del desarrollo (conjunto):** desarrollo +19,38 %, fuera de muestra +7,05 % (cociente 0,36); la cifra de desarrollo cae dentro del IC90 fuera de muestra.

**Regla de decisión aplicada (del prerregistro `94a16556…`):**
- **RESPALDADA:** P(conjunto) ≥ 0,95, P(BTC) ≥ 0,90 y exceso con costes ×2 > 0.
- **NO RESPALDADA:** P(conjunto) < 0,10.
- **INSUFICIENTE:** cualquier otro caso.
- Con P = 0,755 corresponde **INSUFICIENTE**: la regla se aplicó correctamente.

## 4. Limitaciones estadísticas (separadas de las métricas)
1. **P no es un valor p frecuentista:** es la fracción de medias bootstrap (bloques de 20 días, 2000 remuestreos) mayores que 0. P = 0,755 **no** permite afirmar una ventaja ni su ausencia.
2. **Potencia baja por diseño.** Según el propio prerregistro, P(alcanzar 0,95) era ≈ 37 % con el efecto de desarrollo, ≈ 16 % con la mitad y 5 % con un efecto nulo. Lo esperable era «insuficiente», aunque T funcione.
3. **La ventana no es ciega para quien diseñó la regla:** se conocían a grandes rasgos 2022–2026. La regla se fijó antes, con datos hasta 2021.
4. **El efecto de desarrollo probablemente está inflado por selección:** el conjunto pasa de +19,4 % a +7,0 % (z = 0,67 según el informe). Los datos no distinguen esa inflación del azar.
5. **Dos activos muy correlacionados, un solo mercado y una sola familia:** nada se generaliza a otros activos ni a otras estrategias.
6. **Costes supuestos de 10 + 5 pb por lado:** razonables para tamaños chicos en BTC y ETH; no medidos con órdenes reales.
7. **Benchmark:** el exceso se mide contra la estática con la misma exposición media, sin costes. Otro benchmark (buy and hold, efectivo) da otra lectura.

## 5. Reproducción
- **Fuera de muestra:** no se recalculó, a propósito.
- **Desarrollo (2017-08 → 2021-12, no es de uso único):** se reprodujo antes, en la auditoría del 2026-10-20 (`../auditoria_T_REV_EMA9/`). Los tres scripts dieron salidas **idénticas** a las registradas; por ejemplo, BTC +14,18 %/año, P = 0,842.
  - Las salidas están en `../auditoria_T_REV_EMA9/repro_desarrollo/experimentos/*.json` y sus hashes en `../auditoria_T_REV_EMA9/SHA256SUMS`.
  - Esta fase no repitió ningún cálculo.

## 6. Papel (prospectivo): calendario preservado, sin cortes
- **Reglas** `d2e4e1fb43b8219b80e19736ba7a9abed22d6e858f0b8955171496fa06e74939` (versión 1) y **código** `73b22f3e…`: verificados en la auditoría anterior.
- **No existe `papel/cortes/`:** no hay observaciones prospectivas registradas.

| Corte (exclusivo) | Días | Consecuencia | Fuente |
|---|---|---|---|
| **2027-04-18** | 182 | Revisión informativa | Adenda 2 de `PRERREGISTRO_PAPEL.md` (hash actual `695d1d0f0e952e3f8619f5be8783dc176a5a960160543b502bd07a83080a72c3`, con la adenda 2 sin commit) |
| **2027-10-19** | 366 | Primera con consecuencias (solo «detener» si P < 0,10) | Ídem; con el corte 2027-10-18, el código congelado la trata como informativa (11,99 «meses») |
| **2028-10-18** | 731 | Posible «ventaja respaldada» | Ídem |

- **Bloqueo:** `papel/corte.py` escribe `papel/cortes/REGISTRO.jsonl` **dentro del repositorio**. Antes del 2027-04-18 hace falta tu autorización específica o una ubicación externa acordada.

## 7. Dictamen
- **Auditoría de T cerrada.** La ejecución única fuera de muestra está íntegra, trazable por hash completo y preservada sin repetirse. Su conclusión sigue siendo **EVIDENCIA INSUFICIENTE**.
- **No hay evidencia de ventaja ni de su ausencia.**
- **Lo único que puede agregar evidencia sobre T** es el papel, en sus fechas de calendario.
