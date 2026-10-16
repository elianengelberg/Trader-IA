# Paquete para la revisión independiente de H-CARRY (rev. 5)

Fecha: 2026-10-16.

> **Este paquete NO es una revisión independiente, ni la sustituye.** Lo preparó el mismo agente que escribió el código, las pruebas, el borrador y los documentos. Las comprobaciones que figuran como «hechas» las ejecutó el autor. Sirven para que el revisor sepa qué debería obtener, no como evidencia independiente.
>
> **No se ha realizado ninguna revisión independiente.** Este entorno no permite una: no hay una segunda persona ni una máquina separada, y quien revisa no puede ser quien preparó el expediente.

## 1. Qué se pide al revisor

Dictaminar si el expediente está listo para que el responsable autorice **una** evaluación histórica. En concreto:

1. **Reproducción.** Que el inventario, las pruebas y las huellas coinciden con lo declarado (§4).
2. **Fidelidad.** Que el código implementa lo que dicen el borrador y el expediente: D1–D4, precedencia, R0, costes, filtros, funding y condiciones del veredicto.
3. **Integridad.** Que el flujo en siete etapas, el ledger, las autorizaciones y el verificador impiden lo que dicen impedir, y **solo** eso (adenda, §D).
4. **Afirmaciones de la adenda (§A–§C).** En particular:
   - que en un calendario real de 8 h toda omisión de funding deja huella;
   - que las omisiones indetectables pueden sesgar en cualquier dirección;
   - que ningún escenario reconstruye los filtros históricos.
5. **Ausencia de contaminación.** Que nada del paquete contiene ni usa datos reales de mercado, de funding ni del período reservado, y que no hay parámetros elegibles a la vista de resultados.
6. **Dictamen.** Apto, apto con cambios (enumerados) o no apto, con los hallazgos clasificados.

**El revisor NO debe:**
- descargar datos de mercado, de funding ni de exchangeInfo;
- ejecutar `prechequeo_exchangeinfo.py` con una autorización;
- congelar un plan en modo protocolo;
- ejecutar la evaluación.

Todo lo de este paquete funciona sin red y con datos sintéticos.

## 2. Archivos que debe recibir

- **Origen.** Todos están en `research/strategy_lab/saneamiento/fase_transicion/g4_validacion/`, en la rama `claude/algo-trading-simulation-platform-ngf7xo`.
- **No están en el control de versiones.** `research/` no está rastreado y no se hizo ningún commit. El responsable debe transferir una copia por un canal autorizado. El autor no los publicó.
- **Contenido.** El inventario `h_carry/INVENTARIO_HCARRY_REV5.sha256` enumera cada archivo con su SHA-256.
- **Canal del hash.** El SHA-256 **del propio inventario** debe llegarle al revisor por un canal distinto del de la copia, por ejemplo directamente del responsable. Si no, quien altere los archivos puede recalcular también el inventario (adenda, §D).

| Grupo | Archivos |
|---|---|
| Normativos | `h_carry/protocolo_hcarry.json` (1.0, sin cambios), `h_carry/protocolo_hcarry_v1_1_borrador.json` (rev. 5), `h_carry/plan_protocolo_rev5.json` (vista previa exacta del plan) |
| Código del experimento (13 módulos de `HC.MODULOS`) | `h_carry/hc_comun.py`, `modelo_carry.py`, `invariantes.py`, `hc_plan.py`, `hc_ledger.py`, `hc_descarga.py`, `hc_transporte_http.py`, `hc_datos.py`, `hc_metricas.py`, `hc_informe.py`, `hc_evaluacion.py`, `hc_verificacion.py`, `ejecutor_hcarry.py` |
| Herramienta aparte (no es del experimento) | `h_carry/prechequeo_exchangeinfo.py` |
| Pruebas | `tests/hc_sintetico.py`, `tests/test_hc_*.py` (8 archivos), `tests/test_h_carry_*.py` (5 archivos), `tests/conftest.py` (solo para el arnés G4; las pruebas de H-CARRY no lo usan) |
| Documentos | `h_carry/EXPEDIENTE_EVALUACION_HCARRY_REV5.md`, `ADENDA_DECISIONES_HCARRY_REV5.md`, `SOLICITUD_EXCHANGEINFO_HCARRY.md`, `PLANTILLA_INFORME_RESULTADOS_HCARRY.md`, `INFORME_CIERRE_HCARRY_REV5.md`, `INFORME_HCARRY_REV5.md`, este paquete |
| Reproducción y registros | `h_carry/reproducir_suite_hcarry_rev5.sh`, `pytest_h_carry_cierre_rev5.log`, demostraciones y sus salidas (`demostraciones.py`, `reconciliacion.py`, `revision3.py`, `auditoria_r1.py` y sus `*_sintetica(s).txt`) |
| Archivo histórico | `h_carry/archivo_rev4/` (ejecutor y pruebas de la rev. 4, retirados) y `h_carry/archivo_rev5/` (scripts que transformaron el borrador) |

**Hashes clave**, que el revisor debe recibir también por el canal independiente:

| Artefacto | SHA-256 |
|---|---|
| Protocolo 1.0 | `edde54cc1f8509a120564e8d71d06d6a3700f6a357020bbbec385b55982de9f5` |
| Borrador rev. 5 | `c1f6b110300a0fa4694c59805ce10a5544f796509202ed06af1fcba00717d53c` |
| Plan (vista previa) | `eb4a53112a8aeec5044e2a9beffad1a984e0eb2a5e0e0885f8d7141afd7bda4d` |

## 3. Entorno

- Python 3.11 (probado con 3.11.15), pytest 9.1.1 e hypothesis 6.168.0.
- Sin red: las pruebas bloquean la red, y el transporte HTTP solo se ejercita con un `urlopen` sintético.
- Con `--noconftest` no hacen falta PostgreSQL ni psycopg2. El autor comprobó que, así, pasan las mismas 351 pruebas.
- Cualquier sistema con `sha256sum`. Las rutas se resuelven desde los propios archivos.

## 4. Comandos de reproducción y resultado esperado

Desde la raíz de la copia de `g4_validacion` (la carpeta que contiene `h_carry/` y `tests/`):

```
# 1. integridad de la copia (comparar antes el hash del inventario con el recibido aparte)
sha256sum h_carry/INVENTARIO_HCARRY_REV5.sha256
sha256sum -c h_carry/INVENTARIO_HCARRY_REV5.sha256                       # esperado: todas las líneas OK

# 2. suite completa de H-CARRY, sin red y sin cachés
python -B -m pytest -p no:cacheprovider -o addopts="" --noconftest tests/test_hc_*.py tests/test_h_carry_*.py
                                                                          # esperado: 351 passed

# 3. huellas en dos procesos nuevos (deben ser idénticas)
python -I -B h_carry/ejecutor_hcarry.py
python -I -B h_carry/ejecutor_hcarry.py
                                # esperado: plan_sha256 eb4a5311…7bda4d, protocolo_sha256 c1f6b110…d53c

# 4. la vista previa del plan es exactamente el plan que se congelaría (también lo comprueba test_hc_integridad)
python -I -B -c "import sys; sys.path.insert(0,'h_carry'); import ejecutor_hcarry, hc_comun as HC, hc_plan as PL; \
  print(HC.canonico(PL.construir('protocolo')) == open('h_carry/plan_protocolo_rev5.json','rb').read())"   # esperado: True

# 5. demostraciones de revisiones anteriores, byte a byte
cd h_carry && for f in demostraciones reconciliacion revision3 auditoria_r1; do
  o=${f}_sintetica.txt; [ $f = demostraciones ] && o=demostraciones_sinteticas.txt
  python -I -B $f.py | cmp - $o && echo "$f: IDÉNTICA"; done; cd ..

# 6. sin cachés tras ejecutar
find . -name __pycache__ -o -name .pytest_cache -o -name '*.pyc' | wc -l  # esperado: 0
```

**Dentro del repositorio,** con su `.venv`, el script `bash h_carry/reproducir_suite_hcarry_rev5.sh registro.log` hace los pasos 1, 2, 3, 5 y 6. Necesita git y el `.venv` del repositorio, y usa el `conftest.py`.

**Registro del autor:** `h_carry/pytest_h_carry_cierre_rev5.log`. No es evidencia independiente.

## 5. Lista de comprobaciones

| # | Comprobación | Dónde mirar | Resultado que obtuvo el autor |
|---|---|---|---|
| R1 | El inventario coincide y su hash es el recibido aparte | §4.1 | Coincide (51 archivos) |
| R2 | 351 pruebas pasan, sin red y sin cachés | §4.2, §4.6 | 351 pasan; 0 cachés |
| R3 | Huellas reproducibles; plan y protocolo con los hashes de §2 | §4.3, §4.4 | Idénticas |
| R4 | El 1.0 está intacto, y el borrador no contradice al 1.0 en D1: el 1.0 no fija días | `test_d1` | Sí |
| R5 | Criterios, umbrales, costes, capital y ventana del borrador = `config` del plan | Borrador frente a `plan_protocolo_rev5.json` | Sí, por script del autor. Las versiones intermedias no se conservaron (`archivo_rev5/README.md`). |
| R6 | D1 = (n − 1)/24 = 850,9583 días fijos, también con la entrada retrasada | `hc_metricas.py`, `test_d1`, `test_d1b` | Sí |
| R7 | D4 incluye el equity final tras pagar la salida | `invariantes.py`, `hc_metricas.py`, pruebas de D4 en `test_hc_metricas.py` y `test_hc_cierre.py` | Sí |
| R8 | Omisiones de funding detectables → SIN VEREDICTO (A2, A2b) | `hc_datos.py:205-245`, `test_a1` (3 casos), `test_a1b` | Sí |
| R9 | Omisión indetectable con sesgo en los dos sentidos (±22,41 USDT) | `test_a2` (2 casos), cálculo a mano en la prueba | Sí |
| R10 | Todo veredicto lleva las 5 condiciones; SIN VEREDICTO no lleva ninguna | `hc_informe.condiciones`, `hc_evaluacion.py`, `test_a3`, `test_b1` | Sí |
| R11 | Distancia a la liquidación del modelo calculada a mano | `test_c1` | +0,985675 en la hora de entrada |
| R12 | La comprobación previa hace exactamente 2 GET y no conecta sin autorización | `prechequeo_exchangeinfo.py`, `test_x1`–`test_x3` | Sí |
| R13 | El informe, la lectura, el bloque informativo y la sensibilidad no alteran el resultado | `test_hc_informe.py` | Sí |
| R14 | Identidad del código, ledger, autorizaciones en dos fases, verificador en proceso nuevo y transporte HTTP en modo protocolo | `test_hc_integridad.py`, `test_hc_cierre.py`, `test_hc_flujo.py` | Sí |
| R15 | Corte antes de persistir (nada ≥ 2026-06-01) y procedencia de cada página | `hc_descarga.py`, `test_hc_descarga.py` | Sí |
| R16 | No hay datos reales en el paquete | Inspección de los archivos; los `*_sintetica*.txt` dicen SINTÉTICO | Ninguno |

**Puntos que requieren el juicio del revisor** (el autor no puede dictaminarlos):
- si la clasificación «veredicto limitado» de S10, S8, S11–S13 y S12 es aceptable, o si alguna condición debería bloquear el veredicto;
- si las condiciones adjuntas bastan para que un veredicto no sea engañoso;
- si el control sin firmas, con separación de funciones, es suficiente para la decisión que se va a tomar;
- si queda algún grado de libertad elegible a la vista de resultados: escenarios, umbrales de procedencia o parámetros informativos.

## 6. Dictamen esperado

Un documento firmado por el revisor, con:
- el hash del inventario revisado;
- los resultados de R1–R16;
- los hallazgos, clasificados como bloqueante, material o menor;
- el dictamen.

**Sin ese documento,** la decisión 1 del expediente (§12), la aprobación final del borrador, no puede tomarse, y la evaluación no debe autorizarse.
