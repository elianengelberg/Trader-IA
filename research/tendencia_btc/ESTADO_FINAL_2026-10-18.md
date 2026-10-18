# Trader-IA, estado final: fin de la investigación histórica y paso a la validación prospectiva (2026-10-18)

**Convenciones:** **[H]** hecho comprobado · **[I]** interpretación estadística · **[N]** hipótesis no demostrada · **[D]** decisión autorizada.

## 1. Evidencia histórica cerrada
| Línea | Resultado | Conclusión que permite |
|---|---|---|
| H-CARRY (carry de funding) | [H] P1 y P2: EVIDENCIA INSUFICIENTE; el carry rindió +3,76 % en test, por debajo de su comparador del 5 % (`hcarry_next/INFORME_CIERRE_HCARRY.md`) | [I] No hay ventaja neta demostrada. [D] Línea cerrada; solo puede reabrirla el disparador del monitor del carry |
| V (volatilidad gestionada) | [H] No pasó las puertas de desarrollo: Sharpe 0,92 frente a 0,96 de buy and hold, P = 0,38 | [D] Descartada |
| T, desarrollo (2018–2021) | [H] Exceso de timing en BTC +14,2 %/año, P = 0,84 (< 0,90): no avanzó | [I] Efecto no significativo, elegido después de verlo |
| T, fuera de muestra cripto (2022-01 → 2026-05) | [H] Conjunto +7,0 %/año, IC90 −8,8 % / +22,9 %, P = 0,755: EVIDENCIA INSUFICIENTE | [I] Compatible tanto con cero como con el efecto de desarrollo (z = 0,67) |
| **T-MULTI** (11 ETF no cripto, 2013-01 → 2026-09) | [H] E = −0,48 %/año a 10 % de volatilidad, IC90 −1,55 % / +0,65 %, P = 0,24: **EVIDENCIA INSUFICIENTE**. Sin costes: +0,97 %, P = 0,94. Con costes ×2: −1,93 % | [I] Una ventaja neta transferible ≥ 0,65 %/año queda excluida (95 % unilateral). Un valor bruto de ≈ 1 %/año no queda excluido |

- [N] Que T tenga una ventaja **neta** en cripto o en otros mercados.
- [N] Que una versión de T con menos operaciones tenga ventaja neta: sería una hipótesis **nueva**, motivada por estos resultados.
- [D] Ninguna estrategia justifica dinero real. Se cierra la investigación histórica de T: no se vuelve a probar T con datos históricos ni se ajustan sus parámetros.

## 2. Reproducir y verificar T-MULTI
- [H] La evidencia está en `EVIDENCIA_T_MULTI.json`, que se regenera de forma determinista y se verifica con `experimentos/evidencia_t_multi.py verificar`. Al 2026-10-18 verifica sin diferencias.
  - **8 artefactos:** prerregistro `7781e725…`, script `17d6b947…`, resultado `9bb4a55c…`, informe, manifiesto, validación y los dos manifiestos cripto que usa la autoprueba.
  - **36 respuestas crudas** de Yahoo y Nasdaq, con su URL, estado y cabecera `Date`.
  - **22 archivos de código** que el experimento importa realmente, todos versionados y sin cambios.
  - **Commits:** `89278f7` (regla T), `f518ac1` (congelado de T-MULTI) y `c6339e3` (último commit conocido del remoto). Python 3.11.17, sin dependencias externas.
- [H] La cadena prerregistro → script → datos → validación → resultado → commit cierra por hashes. Las 30 cifras clave del informe coinciden con el JSON; se corrigió un redondeo (la caída máxima de T en LQD es 14 %, no 15 %).
- [H] **Límite:** `f518ac1` y los datos crudos (`datos_multi/yahoo`, `datos_multi/nasdaq`; 8,4 MB) **existen solo en este entorno**. Los datos de Yahoo no se pueden volver a bajar idénticos (`adjclose` cambia con cada dividendo nuevo), así que **son la única evidencia exacta**. Sin publicarlos o guardarlos aparte, se pierden.

## 3. Mecanismo prospectivo: qué quedó comprobado
- [H] Regla `d2e4e1fb…` y código `73b22f3e…` idénticos a `89278f7`.
- [H] La adenda 2 del prerregistro del papel **solo agrega** líneas (+17, −0) y no está publicada.
- [H] **No hay ninguna observación prospectiva:** no existen `papel/cortes/` ni ningún `REGISTRO.jsonl`. La historia de la señal termina el 2026-10-16. La primera vela evaluable (2026-10-18) recién cierra el 2026-10-19 a las 00:00 UTC.
- [H] Pruebas sobre el código actual: mecanismo de cortes y evaluador 53/53; suite completa 59/59; autoprueba de T-MULTI exacta; ruff limpio. Cubren:
  - el bloqueo de cortes ya evaluados (C7);
  - la coherencia del registro y su cadena de hashes (C8);
  - el cerrojo entre procesos, incluida la muerte real de un proceso (C9);
  - las fechas no canónicas (C10).
  - Ninguna prueba toca `papel/cortes/`.
- [I] **Un corte no puede «inventarse» antes de su fecha:** para evaluar hace falta que el archivo oficial del día corte − 1 esté publicado y tenga checksum. El control lo dan los datos, no el reloj.
  - Correr un corte antes de tiempo deja un resultado provisional (SIN OBSERVACIONES o NO EVALUABLE) y una línea en el registro. El prerregistro lo permite («recalcular cuando se quiera»), pero **conviene ejecutar solo en las fechas del calendario**.

## 4. Pendiente
- [D] **Solo una decisión tuya: publicar o no.** Hoy quedan sin publicar:
  - el commit `f518ac1`;
  - el commit local de este cierre;
  - C7–C10 (`papel/corte.py`, sus pruebas, el informe de verificación, la adenda 2, `ARTEFACTOS_SHA256.txt` y `.gitignore`).
- No queda trabajo técnico necesario.

## 5. Calendario prospectivo (sin cambios; tomado del prerregistro y del código congelado)
| Evento | Fecha del corte (exclusiva) | Días | Consecuencia |
|---|---|---|---|
| Inicio (rama A) | primera ejecución 2026-10-18 (decisión con el cierre del 2026-10-17) | — | Empiezan las observaciones |
| **Próximo evento: revisión de 6 meses** | **2027-04-18** | 182 | Solo informativa |
| Revisión de 12 meses | 2027-10-19 | 366 | Única decisión posible: **detener** si P(exceso BTC + ETH > 0) < 0,10 |
| Revisión de 24 meses | 2028-10-18 | 731 | Ventaja respaldada si P ≥ 0,95, P(BTC) ≥ 0,90 y exceso con costes ×2 > 0; si no, continuar |

- **Ambigüedad documentada; no la resuelvo cambiando reglas:**
  - La adenda 1 (publicada) nombra el **2027-10-18** como corte de 12 meses.
  - El código congelado calcula meses = días / 30,44, así que ese corte da 11,99 y es **informativo**. El primer corte con ≥ 12 meses es el **2027-10-19**: es lo que documenta la adenda 2, sin publicar.
  - El criterio vinculante («en un corte con ≥ 12 meses», `prerregistro_papel.json`) y el código no cambian. Correr los dos cortes está permitido.
- **El monitor del carry** puede consultarse en cualquier momento. Si supera el 12 % anual, se propone reabrir H-CARRY con un prerregistro nuevo; no cambia nada de T.

## 6. Qué hay que acumular antes de reconsiderar
- [D] **≥ 366 días** de observaciones (corte 2027-10-19) para la primera decisión posible, y **≥ 731 días** (2028-10-18) para poder respaldar una ventaja. **Los resultados históricos no justifican adelantar ni cambiar nada.**
- [I] **La potencia es baja:** con un efecto de ≈ +7 %/año, la probabilidad de «respaldada» a los 24 meses es ≈ 8–14 %. Lo esperable es «insuficiente: continuar».

## 7. Revisión extraordinaria: solo por un defecto técnico o de integridad
Son condiciones que ya prevén el prerregistro y el ejecutor; no hay criterios nuevos:
- **Huellas:** la de reglas o la de código no coincide con `d2e4e1fb…` / `73b22f3e…` (el resultado no vale).
- **Estado del registro:** el ejecutor se detiene con `CorteInconsistente` (procedimiento manual de `papel/VERIFICACION_OPERATIVA_2026-10-17.md`).
- **Datos:** un corte da NO EVALUABLE por datos obsoletos o no publicados, huecos, un archivo oficial revisado o historia incompleta.
- **Fuente:** data.binance.vision deja de publicar los archivos con su checksum.
- **Código:** aparece un error concreto y demostrable en el código congelado (por ejemplo, una mirada al futuro). Requiere un prerregistro nuevo, no un ajuste.
- **No son motivo de revisión:** un resultado intermedio favorable o desfavorable, ni los resultados históricos.

## 8. Archivos sin versionar: clasificación
- **Evidencia de T-MULTI, en el commit local de cierre:**
  - `INFORME_T_MULTI.md`, `experimentos/t_multi.json`, `datos_multi/MANIFIESTO.json`, `datos_multi/VALIDACION.json`;
  - `EVIDENCIA_T_MULTI.json`, `experimentos/evidencia_t_multi.py` y este documento.
- **Cadena histórica de T, en el mismo commit:**
  - `PRERREGISTRO_FUERA_DE_MUESTRA_T.md`, `experimentos/fuera_de_muestra_T.py`, `experimentos/fuera_de_muestra_T.json`;
  - `INFORME_FUERA_DE_MUESTRA_T.md`, `REVISION_CRITICA_FUERA_DE_MUESTRA_T.md`, `experimentos/revision_fuera_de_muestra_T.py`, `experimentos/revision_fuera_de_muestra_T.json`.
- **Datos originales que hay que preservar, fuera de git:** `datos_multi/yahoo/` y `datos_multi/nasdaq/`. Son datos de proveedores no oficiales: no conviene redistribuirlos en el repositorio. Sus hashes están en el manifiesto, y se entregan aparte en un archivo comprimido.
- **Pendientes de tu autorización, sin commitear:** C7–C10 y los cambios en `ARTEFACTOS_SHA256.txt`, `.gitignore` y la adenda 2. Afectan al mecanismo del papel y su publicación es una decisión tuya.
- **Temporales:** no hay ninguno en el repositorio. Los ensayos sintéticos y las mutaciones están en el scratchpad de la sesión.
