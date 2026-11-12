# Plan de auditoría y reproducción (2026-10-20)

**Alcance de los hashes:**
- Un SHA-256 **identifica** un artefacto e impide cambiarlo sin que se note.
- **No** garantiza que el contenido sea correcto, que la estadística sea válida ni que el período sea independiente.
- Inventario completo, con fecha, en `evidencia/03_inventario_hashes.txt`, `evidencia/01_integridad_inicial.txt` y los directorios citados.

## 1. Estado de referencia verificado (2026-10-20 a las 15:46Z)
- **Repositorio:** HEAD `692f2b2d7af3189027b62e60367d104d855b0f3f`, 2 commits por delante y 0 por detrás de `origin` (`c6339e3fcd6041cb6c4ad7f5545f0ff306a4fd2f`).
- **Cambios preexistentes:** 8 entradas.
- **sha256(`git status --porcelain --ignored`)** = `87b9585d31924f8193a6d3eb6d0712a3d3880978681c75d0dd77e00d08f34a8e`, el mismo valor que en las verificaciones anteriores de hoy.
- **Documentos previos intactos:**
  - `fase_documental_2026-10-20/SHA256SUMS` (18 de 18);
  - `auditoria_T_REV_EMA9/SHA256SUMS` (12 de 12);
  - manifiesto de cierre de E3 (176 de 176).

## 2. Artefactos de referencia (SHA-256 completo)
| Artefacto | SHA-256 |
|---|---|
| T fuera de muestra: prerregistro | `94a165560ba2a1807bf604b079dbf2c8eea7e7e4401fcc5ccb5db275464db58f` |
| T fuera de muestra: script (uso único) | `941b6e11f6566319b93614ee671b184d60c7b5fbc64a3931a6ff2c8da17fe0fa` |
| T fuera de muestra: resultado | `4f8fafde372931aab29b94612eb658f5fac9259e51cdf7dace7a1b30fc633c45` |
| T: huella del código `src/tendencia/*.py` | `73b22f3e3a8f21513d5533fb11a7553becae30b87c8736fb6880bccc36c11d2b` |
| T-papel: hash de las reglas | `d2e4e1fb43b8219b80e19736ba7a9abed22d6e858f0b8955171496fa06e74939` |
| T-papel: `prerregistro_papel.json` (archivo) | `ce6b1ac15f351661e0341a60548f30eaa6e1a662fdaa1fcbb1175201dba25388` |
| T-papel: `corte.py` (sin commit) | `b5bc9a59263ac42f1615219c7ed02776a2f1775a7b5091be2300a7b5d1ab05a0` |
| Manifiestos 1d de BTC y ETH | `5a0805a7e22797637c400a1e939ec6c2d10e0cdc26410566f212708211b6367b` / `3998305bb38909a08a94f6365317695f930dea4ea10933b19a22e17b40998f6a` |
| Manifiesto de H-CARRY (incluye spot 1h de BTC) | `8bdabde706bffadca3f4b7ca39937bff14a95ab3ecdc77707bfe4bb434f381d1` |
| Lista de archivos 1h de E1 | `4931ee703bf5c8f2da95a84cd01e7d576fd12580918499bc9aabf35cc50a7ba9` |
| `EVIDENCIA_T_MULTI.json` | `bd496e41d63f009bcbf78c529373a78af7bf19a1045614ba21bb2123a2718480` |
| T-MULTI: prerregistro, script y resultado | `7781e7258916d819abcbc204b0bc0d6ae7e252e5ff349b8c5c1a199c87cee324` / `17d6b947fcf4897c120883e8f64803f206c7286ba4a71752e4b79344648bccde` / `9bb4a55c412c5454aff0abac694b56374c23feedba2039226374967e9d079956` |
| Implementación de P (`hcarry/lab/estadistica.py`) | `6592dfe3e623de8e02ee2c66d0bc22d541df415899a62c61fcf24052675a8b55` |
| Bootstrap-t de E3 (`inferencia.py`), candidato para el MEC | `7b28038621c1d366655d726bb885ca0105f1a25cfcdb9615e86a7fe39e85f3e1` |
| Cierre de E3 y su manifiesto | `503a2e09f5325680c5a1b9c47724993a3e3cd0184fc6f1b5b094c9de4499c9c1` / `bbc90970f4661cdc24cafbf84c59e6a2daa71184b25bf09f02cd1bd26d4c6aba` |
| Registro de hipótesis vigente | `0e59229558c044c2928a033f3f31135cceb281159ea9ae7de09cbb5b646c56c0` |
| Propuestas v0.1 (H-REV-SHOCK / H-EMA9-VWAP) | `6e3875630f823918ff438743a321ff0d4ecba5469b9f1fe52bbc964342bb8e1f` / `6a22ccbfdf536e4b4f8f202ef8f655fabbc436e612af06c844757f5e9ccab63a` |
| Paquete de preservación v2 | `171ef216667d896085ca314a7df3f758ddda25e0a52ecea7b8d5eb6a728f4450` |

- **Entorno:** Python 3.11.17 (sistema, venv de H-CARRY y venv de E1). T y T-MULTI usan solo la biblioteca estándar. E1 y E3 usan sus propios venvs con hashes de dependencias.

## 3. Verificaciones de solo lectura reproducibles hoy
```
cd /home/user/Trader-IA/research/tendencia_btc
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../hcarry_next/src ../hcarry_next/.venv/bin/python -B experimentos/evidencia_t_multi.py verificar
sha256sum -c ARTEFACTOS_SHA256.txt
cd <scratchpad>/expediente_metodologico_2026-10-20 && sha256sum -c SHA256SUMS
cd <scratchpad>/fase_documental_2026-10-20 && sha256sum -c SHA256SUMS
cd <scratchpad>/experimentos/E3_seleccion_posicion_2026-10-19 && grep -v '^#' CIERRE_E3_MANIFIESTO.sha256 | sha256sum -c
```
- **Comprobación de que no se escribe en el repositorio:** comparar sha256(`git status --porcelain --ignored`) antes y después de cada verificación.

## 4. Procedimiento para las fases futuras (cuando se autoricen)
1. **Congelado del protocolo:** el texto aprobado se guarda fuera del repositorio. Su SHA-256 completo se registra en el registro de ejecuciones **antes** de leer cualquier dato de D.
2. **Código:**
   - huella SHA-256 de todos los archivos que se importan (lista explícita, como en `EVIDENCIA_T_MULTI.json`);
   - entorno con versiones fijadas y hashes de las dependencias (`--require-hashes`, como en E1).
3. **Datos:** manifiesto con el SHA-256 de cada archivo y su `.CHECKSUM` oficial. Lista ordenada con un hash propio.
4. **Candado de uso único para E:** el script se niega a correr si existe el resultado o una marca de ejecución. El resultado guarda los hashes del protocolo, el código, los manifiestos, la semilla y el entorno. **No se copia ni se renombra para volver a correrlo.**
5. **Registro de solo añadidos:** JSONL donde cada línea incluye el hash de la anterior (cadena) y **todas** las corridas, incluidas las fallidas o inválidas, con su motivo.
6. **Reproducción independiente:** un segundo proceso, en un directorio nuevo y con los datos verificados contra el manifiesto, recalcula el estadístico y compara la salida byte a byte. En E, solo **después** de la ejecución única y sin decidir nada nuevo.
7. **Revisión independiente por otro modelo:** si se autoriza, se le entregan el MEC, las propuestas y las fórmulas (MEC §11). Se registran sus objeciones y cómo se resolvieron. **Hasta hoy no ocurrió.**
8. **Persistencia:** nada de esto vale si se pierde el scratchpad efímero (D-G0).

## 5. Qué no se pudo verificar
- **El origen del diagnóstico «308 faltantes»:** está fuera de la sesión.
- **Los originales de H-REV-SHOCK y H-EMA9-VWAP.**
- **Gmail:** el conector requiere volver a autorizarlo.
- **La fecha externa de los congelados locales de T:** sin publicar, no es verificable por terceros.
