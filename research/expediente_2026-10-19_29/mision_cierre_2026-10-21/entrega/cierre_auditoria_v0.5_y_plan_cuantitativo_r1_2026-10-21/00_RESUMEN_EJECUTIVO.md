# 00 — Resumen ejecutivo: cierre de la auditoría v0.5 y preparación de la fase cuantitativa (r1, 2026-10-21)

**Estado:** cierre técnico de la auditoría de v0.5, con **autenticidad pendiente**.
- T sigue INCONCLUSO (`SIN_REFERENCIA_INDEPENDIENTE`) y P2 NO_CANDIDATA.
- Nada está autorizado ni integrado.
- El protocolo de la fase cuantitativa está construido y probado con datos sintéticos, pero **no validado
  empíricamente** hasta la calibración A-S1.

## Qué verifiqué realmente
- **El ZIP v0.5** (`5bf9bc5d…`): SHA-256, `unzip -t`, `verificar_zip.py`, una comprobación independiente, `sha256sum -c`
  en una extracción nueva, la cadena del registro de acciones y el 95 recalculado byte a byte.
- **La reproducción completa** de v0.5 desde una extracción nueva del ZIP final: 81 minutos y resultados iguales a los de v0.5 (449 pruebas, matriz 48/48, mutaciones 11/11, 20/20, 4/4 y 10/10, P2 86.400/86.400, parches OK; 36 de 37 comparaciones y 139 de 139 archivos idénticos). La única diferencia, «estado git cambió», la causó mi incidente I-1, no v0.5.
- **27 cifras declaradas por v0.5 frente a lo observable:** 26 coinciden. «X1–X26» son 24 escenarios (D-3).
- **Estado del repositorio:** HEAD `692f2b2`, huella `87b9585d…`, huella fuerte idéntica a la del cierre de v0.5. T y
  T-MULTI son iguales a HEAD según git.
- **Preservación:** 25 ZIP y 18 manifiestos, sin un solo fallo, al empezar y al terminar.
- **Ejecutor:** análisis estático; sin red, sin acciones reales, `ACCION = NINGUNA`.
- **La declaración de T para firmar:** bytes canónicos y hashes vigentes.

## Qué corregí
**En v0.5** (en una copia aislada; v0.5 queda intacto, con las correcciones propuestas y probadas antes y después):
- **D-1:** la etapa 13 no veía enlaces ni directorios nuevos.
- **D-2:** las pruebas dejan temporales en TMPDIR.

**En mi propio código nuevo**, antes de entregar:
- **N-1:** cuantiles en coma flotante, hallado por el contraste con E3.
- **N-2:** un punto ciego de B2.
- **N-3:** procesos sintéticos centrados.
- **N-4 y N-5:** `__pycache__` y temporales; ahora lo impide una prueba de higiene.

**Incidente I-1:** creé por error un `.pyc` en el `.venv` del repositorio. Lo detectó la huella fuerte; borré solo ese
archivo y no toqué ningún mtime. Queda una única diferencia de metadatos, informada como desviación conocida.

## Qué decidí (categoría B, criterios en 02)
| ID | Decisión |
|---|---|
| D-S1 | Bootstrap-t, ℓ = 20, B = 9999 |
| D-S2 | Bonferroni |
| D-S3 | Máx de tres valores p |
| D-S5 | O'Brien–Fleming |
| D-S6 | El nulo emparejado es descriptivo |
| D-S7 | Sin compuerta por resultado |
| A3 | La robustez no veta |
| A4/A7, A6 | Se mantienen |
| A9/A14 | REPRODUCIDO, independiente, determinista y con todas las reproducciones |
| A10 | 0 reintentos, determinismo y límite de tiempo |
| A13 | Política de raíces |
| D-T2 | No enmendar T-papel |

Todas valen para hipótesis **futuras**; ninguna toca T ni T-MULTI.

**Recomendaciones de priorización:**
- **H-REV-SHOCK v0.2: no iniciar.** Exige ≥ 7,9 % neto por evento para confirmarse en 3 años y reabre una familia
  descartada.
- **H-EMA9-VWAP v0.2:** solo prospectiva y aceptando de antemano «no concluyente».
- **No propongo hipótesis nuevas** sin pasar la criba.

## Qué evidencia nueva produje
- `protocolo_cuantitativo/` (PEC-1.0): prueba primaria, diseño secuencial, potencia y criba, contabilidad con funding y
  liquidación, validador de datos, B1/B2, decisión, prerregistro, registro del programa y calibración bloqueada.
  **72 pruebas** sintéticas; contraste con E3; valores publicados de O'Brien–Fleming; Monte Carlo independiente.
- `auditoria/`: inventario de preservación, afirmaciones frente a la evidencia, comprobaciones de v0.5, criba y
  manifiesto.
- `correcciones_propuestas_v0.5.1/`: dos parches con pruebas antes y después.
- `documentos_para_autorizar/`: la declaración de T con su guía; el ancla (O2 + O5); A-S1 y δ; B-1; B-3/B-4/B-7.
- `03` cadena de confianza, `04` 27 amenazas con controles priorizados, `05` plan cuantitativo.
- **El hallazgo cuantitativo central:** confirmar en 3 años exige un **IR neto ≥ 1,64**. T tiene ≈ 0,35, y le haría
  falta ≈ 66 años.

## Qué riesgos quedan
- **Todo está en el scratchpad efímero** (A-01).
- Los registros son locales: una reescritura coherente no se detecta (A-02).
- La prueba primaria no está calibrada (A-14).
- Mismo autor en todo, sin revisión independiente (A-15).
- La procedencia de los datos no tiene una segunda fuente (A-09).

## Qué puede avanzar ya, sin nada tuyo
Nada más dentro de los permisos actuales: todo el trabajo técnico reversible está hecho.

## Qué necesita tu autorización
Ver `06_AUTORIZACIONES_PENDIENTES.md`, en orden:
1. descargar los ZIP;
2. A-S1;
3. δ;
4. firmar T;
5. publicar commits;
6. el ancla O2 + O5;
7. la ubicación de los registros (antes del **2027-04-18**);
8. B-1;
9. D-G1/D-G5;
10. el revisor;
11. B-4;
12. B-3.

## Próximo paso de mayor valor
**Descargar los ZIP hoy y autorizar A-S1**: valida el método para toda hipótesis futura en unas horas de CPU, sin
datos reales y sin riesgo para T.

## Paquete
- `CIERRE_AUDITORIA_v0.5_Y_PLAN_CUANTITATIVO_r1_2026-10-21.zip`, SHA-256 en `SHA256SUMS_DEL_ZIP.txt`, junto al ZIP, y en
  el mensaje final.
- Reproducir con:
  ```
  V05_ZIP=<ZIP v0.5> REPO=<repositorio> SCRATCH=<carpeta de entregas> bash ejecutar_verificacion.sh
  ```
- v0.5 no se copia: se referencia por su SHA-256.
