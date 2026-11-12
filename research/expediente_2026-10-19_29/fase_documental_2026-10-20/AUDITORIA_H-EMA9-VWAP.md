# Auditoría de H-EMA9-VWAP: búsqueda del protocolo original (citado como «v1»)

**Fecha:** 2026-10-20. **Resultado:** **no se recuperó ningún original verificable.** La referencia citada (prefijo `3114b565…`, «v1 congelada») no corresponde a ningún archivo ni texto en las fuentes accesibles.

## 1. Fuentes revisadas y resultado

| Fuente | Cómo | Resultado | Evidencia |
|---|---|---|---|
| Árbol de trabajo del repositorio | Texto (`ema[-_ (]?9`, `ema9`, `ema\(9\)`, «VWAP» cerca de «EMA») y prefijo de hash, como texto y como inicio del SHA-256 de cada archivo | 0 protocolos | `evidencia/06_busqueda_nombres.txt`; `../auditoria_T_REV_EMA9/resultado_verificacion.json` |
| Todas las versiones de git (1258 blobs) y mensajes de commit | `git grep` sobre `git rev-list --all`; SHA-256 de cada blob | 0 | Ídem |
| Código del bot (`packages/tia`) | Búsqueda de EMA(9) y de reglas EMA+VWAP | **Solo** el indicador `vwap()` acumulado de toda la serie (no de sesión) y la característica `dist_vwap_pct`. No hay estrategia EMA(9)+VWAP | `packages/tia/src/tia/quant/indicators.py:88`, `features.py:223` |
| Rama remota en GitHub | API, solo lectura | Nada nuevo | `evidencia/01_estado_git.txt` |
| Scratchpad (sin datos crudos) y 25 paquetes comprimidos (11 614 miembros) | Texto y prefijo | 0 | `evidencia/06_busqueda_nombres.txt` |
| Historial completo de esta sesión | Por rol y origen | El nombre aparece por primera vez en tu mensaje del **2026-10-20 a las 12:01:10Z** | Ídem |
| Google Drive | «EMA9», «VWAP», prefijos, «Trader-IA», «prerregistro» | 0 relacionados; el conector funciona | Registro de acciones |

**Fuentes NO revisadas:**
- **Gmail:** requiere volver a autorizarlo.
- **Conversaciones externas, tu computadora, el VPS y repositorios no conectados:** no son accesibles.

## 2. Qué se puede y qué no se puede afirmar
- **Se puede:** en este entorno no existe ningún protocolo H-EMA9-VWAP, ni v1 ni otro.
- **No se puede:**
  - cuál era la v1: temporalidad, precio, anclaje del VWAP, entradas, salidas, stops ni período;
  - que `3114b565…` sea el hash de algún documento.
- **No es** E1-P1 (trend_following del bot en BTC a 1 h, descartada): esa estrategia usa EMA 12/26/50, ADX, DI y ATR (`packages/tia/src/tia/strategy/library.py:53`), no EMA(9) ni el VWAP de sesión. Igual queda como evidencia previa relevante sobre reglas de tendencia horarias después de costos (ver la matriz).

## 3. Decisión aplicada
- Se redactó **`PROPUESTA_PRERREGISTRO_H-EMA9-VWAP_v0.1.md`**: una **propuesta nueva**, pendiente de aprobación y **no ejecutada**.
  - Usa otro número de versión (v0.1), así que **no sustituye** a la «v1» mencionada: no se le asigna ese nombre ni ese hash.
  - Sus parámetros **no** reconstruyen los de la v1. Se eligieron por criterios conceptuales declarados en la propuesta.
- **Si la v1 aparece:**
  1. se verifica su SHA-256 completo contra `3114b565…`;
  2. la v1 prevalece y se audita intacta;
  3. la v0.1 se retira o pasa a ser un experimento distinto, por tu decisión.
