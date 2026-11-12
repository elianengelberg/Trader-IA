# Auditoría de H-REV-SHOCK: búsqueda del protocolo original

**Fecha:** 2026-10-20. **Resultado:** **no se recuperó ningún original verificable.** La referencia citada (prefijo `69758896…`) no corresponde a ningún archivo ni texto en las fuentes accesibles.

## 1. Fuentes revisadas y resultado

| Fuente | Cómo | Resultado | Evidencia |
|---|---|---|---|
| Árbol de trabajo del repositorio | Texto (nombre y variantes: `rev[-_ ]?shock`, `revshock`) y prefijo de hash, como texto y como inicio del SHA-256 de cada archivo | 0 | `evidencia/06_busqueda_nombres.txt`; `../auditoria_T_REV_EMA9/resultado_verificacion.json` (4228 archivos) |
| Todas las versiones de git (1258 blobs de todos los commits) y mensajes de commit | `git grep` sobre `git rev-list --all`; SHA-256 de cada blob; `git log --grep` | 0 | Ídem |
| Rama remota en GitHub (`c6339e3`) | API de GitHub, solo lectura; sin `fetch` | No tiene commits que no estén en local | `evidencia/01_estado_git.txt` |
| Scratchpad de la sesión (sin datos crudos de mercado) | Texto y prefijo | 0 | Ídem (38 721 archivos) |
| Paquetes comprimidos (preservación v1 y v2, entregas de H-CARRY, recuperación rev. 5, investigación) | Nombres y contenido de cada miembro | 0 (25 paquetes, 11 614 miembros) | `evidencia/06_busqueda_nombres.txt` |
| Historial completo de esta sesión | Búsqueda por rol y origen | El nombre aparece por primera vez en tu mensaje del **2026-10-20 a las 12:01:10Z**; nunca antes, ni en respuestas ni en salidas de herramientas | `evidencia/06_busqueda_nombres.txt` |
| Otras sesiones de Claude en la cuenta | API de sesiones (solo títulos) | Ninguna de Trader-IA, salvo esta | Auditoría anterior, §1 |
| Google Drive (conector) | `fullText` y `title` con «REV-SHOCK», prefijos, «Trader-IA», «prerregistro» | 0 relacionados. Una búsqueda de control confirmó que el conector funciona | Registro de acciones |

**Fuentes NO revisadas** (no se afirma nada sobre ellas):
- **Gmail:** el conector requiere volver a autorizarlo en la configuración de conectores de claude.ai.
- **Conversaciones de claude.ai o de otros asistentes fuera de esta sesión:** no son accesibles.
- **Tu computadora, el VPS y repositorios no conectados:** tampoco son accesibles.

## 2. Qué se puede y qué no se puede afirmar
- **Se puede:** en este entorno no existe ningún protocolo de H-REV-SHOCK, ni congelado ni borrador.
- **No se puede:**
  - que el original no exista en otro lugar;
  - cuáles eran sus reglas, activos, período o umbrales;
  - que `69758896…` sea el hash de algún documento.
- **No es** E1-P2 (mean_reversion del bot), ni la familia R (reversión diaria), ni C10 (reversión tras extremos). No se supone ninguna equivalencia (ver la revisión crítica en `MATRIZ_VALIDACION_COORDINADA.md`).

## 3. Decisión aplicada
- Según la regla del pedido, se redactó **`PROPUESTA_PRERREGISTRO_H-REV-SHOCK_v0.1.md`**: una **propuesta nueva**, pendiente de aprobación y **no ejecutada**.
  - **No es** una reconstrucción del original y no hereda su nombre de versión ni su hash.
  - Solo usa la hipótesis conceptual del pedido: «un movimiento excepcional seguido de señales de agotamiento podría presentar una reversión aprovechable después de costos».
- **Si el original aparece:**
  1. se verifica su SHA-256 completo contra `69758896…`;
  2. el original prevalece;
  3. esta propuesta se retira o, si tú lo decides, pasa a ser un experimento distinto con su propio nombre.
