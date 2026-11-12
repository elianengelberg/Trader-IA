# 00 — Informe final: decisiones metodológicas pendientes y PEC-1.1 (2026-10-21)

**En una línea:**
- A-S1 está verificado y reproducido byte a byte.
- **El diseño secuencial de 5 miradas controla el error global** (SEC-1.0: APTO; ≤ 2,70 % demostrado).
- **PEC-1.1 está justificado y creado.**
- **δ no está determinado:** queda tu decisión, con alternativas y su texto exacto.
- **La fase prospectiva sigue bloqueada.**

Todo con datos sintéticos.
- No hubo commits, push, despliegues, operaciones ni datos de mercado.
- r1, v0.5 y el ZIP A-S1 no se modificaron; se usaron extracciones nuevas, verificadas por hash.
- Nada se firmó en tu nombre.

## 1. Qué verifiqué efectivamente
- **ZIP A-S1:** SHA-256 completo `37af592c…f64e6` coincide. Además:
  - `unzip -t` correcto;
  - manifiesto con 70 de 70 archivos, ninguno de más ni de menos.
- **Correspondencia del código** (`codigo/f1/recuento_a_s1.py`, escrito de nuevo):
  - los 15 hashes de código registrados coinciden con r1 y con los archivos;
  - parámetros `28764d31…`, semilla, B y réplicas iguales en parámetros, celdas y resultado;
  - **96 000 réplicas** y **48 comprobaciones por regla**, recontadas desde los valores p crudos;
  - las 48 filas son idénticas a las del resultado.
- **Definiciones exactas** de C1–C6 y de las métricas, leídas del código (`informe/01` §3).
- **Alcance real de lo que A-S1 llamó «independiente»:** no lo es en sentido estricto, porque comparte autor, máquina y
  código. Es un recuento por otro camino de código más pruebas de determinismo (`informe/01` §5).
- **Hallazgos:**
  - **F1-1:** las celdas de A-S1 no son independientes. Comparten la semilla del bootstrap, y C4 reutiliza las series de
    C2. La cifra de ≈ 62 % es solo una aproximación; el veredicto no cambia.
  - **F1-2:** la identidad byte a byte depende de Python 3.11.17. Con 3.13, 603 de 4800 valores p difieren en ≤ 3,4·10⁻¹⁴,
    sin ninguna decisión distinta.
  - **F1-3:** N-6, que es solo documental.
  - Por separado: **el defecto de unidades de δ en PEC-1.0**.

## 2. Qué resultados reproduje
- **A-S1 completo:** las 96 000 réplicas, reejecutadas desde extracciones limpias. El resultado y **las 48 celdas son
  idénticos byte a byte**, y `verificacion.json` también.
- **Lecturas descriptivas de A-S1:** regeneradas, idénticas.
- **Mi propia calibración nueva, SEC-1.0:**
  - 234 trayectorias recalculadas con la regla completa, sin el cortocircuito, coinciden todas;
  - el cortocircuito es exacto frente a `respaldo` (240 de 240 en desarrollo).
  - **SEC-1.0 no está reproducida por otra persona ni en otra máquina.** `verificar.sh REEJECUTAR_SEC=1` lo permite.

## 3. Qué decisiones metodológicas resolví, y con qué justificación
- **El diseño secuencial completo** (`informe/03`).
  - **Formalización:** 5 miradas sobre prefijos anidados, regla máx con B = 9999 y una sola semilla, fronteras OBF sobre
    p y futilidad omitida (cota superior).
  - **Criterio fijado antes:** cota superior de Clopper–Pearson ≤ 3,0 %, con Bonferroni sobre 18 celdas y R = 36 000.
    Se eligió para que una prueba exacta lo pase con probabilidad ≥ 0,95, corrigiendo el defecto de A-S1.
  - **Ejecución confirmatoria única,** con semillas nuevas.
- **PEC-1.1** (`informe/04`, `protocolo_cuantitativo_PEC-1.1/PEC-1.1.md`):
  - la regla decisiva;
  - la política de ausentes, inválidos e inconclusos;
  - los criterios de parada;
  - n_max por fórmula y dentro del rango calibrado;
  - δ en escala anual, convertido a diaria;
  - la relación entre lo sintético y lo prospectivo.
- **Lo que no resolví, porque no es técnico:** δ. Sí dejé su definición exacta, el marco
  δ = (F/K + π)/(1 − d), tres alternativas (5, 10 y 15 %) con sus consecuencias y una recomendación técnica no vinculante
  (`informe/02`).

## 4. Qué requiere tu decisión o autorización
| Ítem | Qué tenés que hacer |
|---|---|
| **δ (A8 / D-S4)** | Completar y firmar el texto de `informe/02` §8: valor, ámbito y base (K, F, π, d) |
| **D-G1** | Aprobar una hipótesis que pase la criba con IR de diseño δ/TE entre 1,27 y 1,64. Hoy no hay candidata |
| **B-4** | Autorizar una fuente de datos |
| **D-G4** | Decidir dónde se escriben los registros (para T-papel, antes del 2027-04-18) |
| **R-5** | Autorizar el ancla externa (O2 + O5). Sin ella, los «fijado antes» siguen dependiendo de registros locales |
| **Calibración** | Si querés n_max fuera de [1096, 1826], o procesos distintos de C1–C6, autorizar una calibración nueva |
| **Interpretación de la fase 3** | La traté como autorizada por tu mensaje (`registro/F3_NOTA_PREVIA_SECUENCIAL.md` §1). Si no era tu intención, decímelo: el resultado queda marcado como tal |
| **Pendientes anteriores** | Siguen como estaban en r1 `06`: firma de T, publicar commits y revisor independiente |

## 5. ¿El diseño secuencial controla el error global?
**Sí, dentro del umbral prerregistrado.**
- **Cota superior (95 % conjunto):** ≤ 2,70 % en las 18 celdas.
- **Estimación puntual:** entre 2,23 % y 2,46 % en C1–C3, C5 y C6, y entre 0,73 % y 0,97 % en C4, el proceso disperso.
- **Alcance:** la regla máx con B = 9999; procesos C1–C6; n_max ∈ {1096, 1461, 1826}; miradas equiespaciadas; sin
  faltantes; futilidad omitida.
- **Potencia real en los puntos de diseño:** 75–80 %, frente al 80 % de la prueba z.

## 6. ¿PEC-1.1 está justificado?
**Sí, y está creado** como versión nueva.
- PEC-1.0 queda intacto dentro del mismo directorio, con los mismos hashes; solo cambia el README.
- **115 de 115 pruebas pasan,** y ruff no encuentra nada.
- El código calibrado es byte a byte el de r1, y los umbrales coinciden con los de SEC-1.0.
- **No cambia ninguna regla aplicada antes.**

## 7. ¿La fase prospectiva sigue bloqueada?
**Sí.** El método ya está calibrado, pero faltan cinco requisitos explícitos, todos tuyos: **δ, D-G1, B-4, D-G4 y R-5.**
- Además, ninguna hipótesis actual tiene un IR de diseño dentro del rango calibrado.
- El código lo hace cumplir: un prerregistro PEC-1.1 prospectivo sin δ, o con n_max fuera de rango, no se congela.

## Contenido del paquete
| Ruta | Qué es |
|---|---|
| `informe/01–04` | Fases 1 a 4 |
| `registro/` | Nota previa de SEC-1.0, propiedades del criterio, huellas previas y equivalencia de desarrollo |
| `codigo/f1`, `f2`, `f3` | Verificación de A-S1, consecuencias de δ, simulador y análisis de SEC-1.0, con sus especificaciones |
| `evidencia/` | Salidas de las fases 1 y 2 |
| `sec_1_0/` | Datos crudos de las 24 celdas, registros y análisis |
| `sec_1_0_desarrollo/` | Corrida de desarrollo (semilla 20261104, **no es evidencia**), incluida para presentar todo |
| `protocolo_cuantitativo_PEC-1.1/` | El protocolo |
| `verificar.sh` | Reproducción desde una extracción limpia |
| `SHA256SUMS.txt` | Manifiesto |

**Reproducir:**
```
R1_ZIP=<r1.zip> AS1_ZIP=<A-S1.zip> PY=<python con pytest> bash verificar.sh <dir_nuevo>
```
Agregá `REEJECUTAR_SEC=1` o `REEJECUTAR_AS1=1` para las reejecuciones completas.

**Riesgos que siguen:**
- Todo vive en el scratchpad efímero.
- Los registros temporales no tienen ancla externa.
- Mismo autor en todo: no hay revisión independiente.
- La calibración cubre procesos sintéticos, no el mercado real.
