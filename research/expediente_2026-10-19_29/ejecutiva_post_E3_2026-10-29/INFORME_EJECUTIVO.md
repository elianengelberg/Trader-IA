# Informe ejecutivo · Cierre de E3 y siguiente experimento (2026-10-29)

**Carpeta:** `ejecutiva_post_E3_2026-10-29/`. Las rutas que siguen son relativas al scratchpad.

**Qué no se hizo:**
- no se ejecutó E3 ni ninguna prueba sobre las series reales;
- no se emitió, firmó ni consumió ninguna autorización;
- no hubo commits, push, merge ni deploy;
- no se modificó ni movió nada que ya existiera.

La única baja fueron 2 enlaces simbólicos de prueba creados en esta misma fase, que apuntaban a R1 y se borraron (ver punto 5).

## 1. Estado verificado de E3

**E3 está cerrado administrativamente** (`CIERRE_ADMINISTRATIVO_E3.md`).

| Elemento | Estado |
|---|---|
| E3-H1, E3-H2, E3-H3 | **NO EVALUABLE** |
| Candidata A | **INVÁLIDA**: según SL-v1 con la adjudicación de los BLVT empieza el 2024-04-08 y tiene 111 semanas, menos de las 156 exigidas |
| Ventana | No se modificó |
| Lectura principal alternativa (158 semanas) | No se adopta: sería una elección *post hoc* |

**NO EVALUABLE no es evidencia en contra, e INSUFICIENTE no equivale a refutar.** Por la hoja de ruta del 2026-10-21 (§3), la familia transversal no se cierra: queda sin prueba histórica posible y solo se puede evaluar de forma prospectiva.

## 2. Integridad de los artefactos

Comparé `registro/huellas_inicio.txt` (02:08Z) con `registro/huellas_fin.txt` (02:33Z).

- **Árboles congelados:** los 10 (E3, E3R, REP, RV, CB, PK, PKD, DEC, RA y V4) y las páginas archivadas tienen **huellas idénticas** al inicio y al final. También coinciden con las del cierre anterior.
- **`MANIFEST_CIERRE_DECISIVO.sha256`** (sha `94d629c6…`): **527/527 entradas OK**. Tiene 528 líneas porque la primera es un encabezado. Ver `registro/verificacion_fin.txt`.
- **Archivos `INTENTOS_E3.jsonl`:** hay 274. Están todos dentro de `revision_adversarial_E3H1H2_2026-10-28`, son de la inyección de fallos L-13 sobre copias y ya existían (el árbol RA no cambió). Ninguno corresponde a una ejecución real.

## 3. Git

| Dato | Valor |
|---|---|
| Rama | `claude/algo-trading-simulation-platform-ngf7xo` |
| HEAD | `72ffae5d2698440c8f1afaff12e07bd8adde66fb` |
| `git status --porcelain` | 0 líneas |
| Stash | 0 |

**Diferencias detectadas: ninguna**, ni respecto del inicio de esta fase ni del cierre anterior.

## 4. Ubicaciones verificadas hoy

La lista completa, con el hash de cada archivo, está en `registro/verificacion_fin.txt`.

**Series reales:** 757 `.npz` en cada copia, conjunto `6506fb03c211def7…`.

| Copia | Ruta |
|---|---|
| R1 | `experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3/resultados/calidad/series` |
| R2 | `paquete_revision_independiente_E3H1H2_2026-10-28_DATOS/evidencia/experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3/resultados/calidad/series` |
| Tarball con datos | `entrega_revision_independiente_2026-10-28/…_DATOS.tar.gz`, sha `0562b919…` |

**Orquestadores: 15 copias, todas IGUAL a su hash de referencia.**

| Orquestador | Hash | Copias |
|---|---|---|
| E3R | `3b64a04d` | 6 |
| v3 | `c089cc6a` | 3 |
| v2 | `01fc9344` | 6 |

## 5. Aislamiento

| | Qué | Evidencia |
|---|---|---|
| **Comprobado** | La **zona aislada** (`zona_aislada/ejecutar_aislado.sh`), con un espacio de montaje privado, tapa las 18 rutas de `PROTEGIDOS.tsv`. Adentro se ven 0 `.npz`, el v2 aparece con 0 bytes y cualquier escritura falla con «Read-only file system». Afuera los hashes no cambian y no queda ningún montaje global | `registro/prueba_zona_aislada.txt` |
| **Comprobado** | La **guarda de rutas** del código de E4 (`codigo/guarda_rutas.py`) rechaza las series, sus subarchivos, enlaces simbólicos y duros, rutas con `..` y orquestadores. Acepta una carpeta nueva | `e4_xsrev_prospectivo/registro/prueba_guarda.json` (9/9) |
| **Comprobado** | Se borraron los 2 enlaces simbólicos de esa prueba que apuntaban a R1. El hash de R1 es el mismo antes y después, y no queda ningún enlace simbólico en la carpeta | `registro/limpieza_enlaces.txt` |
| **Pendiente** | Una ejecución **manual directa**, fuera de la zona, todavía puede leer las copias. Para cerrar eso hay que sellarlas por renombre, lo que requiere tu autorización | `AISLAMIENTO_COPIAS_REALES.md` §3: comandos exactos, hashes antes y después, reversión y las 5 consecuencias. No se ejecutó |

## 6. Bloqueos, ya especificados

- **R-2 (ancla externa):** `ANCLA_EXTERNA_R2.md`.
  - Hay dos testigos: T1, la rama `registros` protegida por ruleset, que fija el orden y el último estado; y T2, OpenTimestamps, que prueba la existencia antes de una fecha.
  - Los eventos van en JSON canónico firmado con Ed25519. El anclaje es sincrónico: antes de abrir y antes de anunciar una decisión.
  - Si el ancla no está disponible antes de abrir, no se consume nada. Si falta después de abrir, hay reintentos durante 24 h y luego ERROR terminal.
  - **No existe todavía ninguna ancla real.**
- **L-17:** **no hay defecto.** Los 53 vectores negativos se rechazan, cada uno por la regla prevista (0 por otra regla), y los 10 controles positivos nuevos se aceptan (`l17/L17_analisis.json`). No se debilitó ningún control.
- **R-4:** cubierto por la zona aislada y la guarda. El cierre completo depende del sellado (punto 5).
- **Revisión independiente:** `REVISION_EXTERNA_PAQUETE.md`.
  - Detalla qué artefactos recibe el revisor y 10 afirmaciones (A1–A10), cada una con su procedimiento y lo que la refutaría.
  - **No hubo revisión independiente.** Todo lo de esta fase lo hizo el mismo agente.

## 7. Próximo experimento recomendado: E4, H-XS-REV-1 prospectiva

Prerregistro: `e4_xsrev_prospectivo/PRERREGISTRO_E4.md`. Es un BORRADOR v0 y **no está congelado**.

**Hipótesis:** el IC de Spearman diario entre la reversión de ayer, −r(t−1), y el retorno de mañana, r(t+1), es positivo. Se mide sobre las 100 monedas spot USDT de Binance con mayor volumen, con un día de rezago.

**Prueba:**
- t de Newey-West con 5 rezagos, unilateral, α = 0,025;
- una sola mirada a T0 + 365 + 3 días, sin reintentos;
- las clases de resultado están fijadas de antemano.

**Por qué aporta información nueva:**
- Usa **solo datos posteriores a T0**, así que no existen todavía. No hay contaminación por lecturas previas ni selección retrospectiva, y no comparte observaciones con E3 ni con los árboles congelados.
- Es la única vía que la hoja de ruta deja abierta para la familia transversal.
- Potencia analítica a 365 días: entre 0,41 y 0,97 para IC = 0,02, y entre 0,74 y 1,0 para IC = 0,03. El IC mínimo detectable con 80 % va de 0,015 a 0,032 (`registro/potencia_E4.txt`, supuestos [Hip]). Para comparar, E3 tenía entre 0,35 y 0,55.

**Benchmark y costos** (análisis secundario, que no cambia la clase): cartera solo compradora del quintil perdedor frente a la cartera equiponderada.
- Comisión taker de 7,5 pb más medio spread de 5 pb, con sensibilidad a 10 y 20 pb.
- Sin funding, porque es spot y solo compradora.
- Descarte rápido si el bruto es menor que 2 × costos.

**Arnés probado solo con datos SINTÉTICOS**, marcados con `SINTETICO.txt` y fechas ficticias de 2030 y 2031:
- **P1:** con efecto nulo, falsos positivos del 2,5 % en 200 simulaciones.
- **P2:** con efecto plantado, se detecta en el 100 % de los casos.
- **P3–P7:** fuga de futuro, exclusiones, salidas, rotación y clasificación, todas OK.
- **De punta a punta:** checksums, cadena de hashes, no sobrescritura y destino protegido, OK. El evaluador rechaza correr antes de tiempo, dos veces, con el prerregistro alterado y en modo real sobre datos sintéticos.

Ningún resultado sintético es evidencia sobre el mercado.

## 8. Comandos exactos (no se ejecutaron: requieren autorización)

Están en `COMANDOS_SIGUIENTE_FASE.md`:
- **§0** sellado;
- **§1** ancla;
- **§2** congelación del prerregistro, `ots stamp` y push a `registros`;
- **§3** recolección mensual, dentro de la zona aislada;
- **§4** evaluación única, no antes de T0 + 368;
- **§5** pruebas sintéticas, que se pueden repetir sin autorización.

**Límite práctico:** este contenedor es efímero y le quedan unos 390 MB libres. Los datos de E4 tienen que guardarse en almacenamiento persistente.

## 9. Decisiones humanas pendientes (mínimas)

1. **Sellado:** autorizar el renombre de R1 y R2 (`AISLAMIENTO_COPIAS_REALES.md` §3) o aceptar el aislamiento parcial actual.
2. **Ancla:** crear la rama `registros` con su ruleset, autorizar los push de `anclas/`, la instalación del cliente OTS con su red a los calendarios y la clave de máquina `ancla_e4`.
3. **E4:** revisar el prerregistro, autorizar su congelación y elegir el almacenamiento persistente. T0 queda fijado al confirmarse el ancla.
4. **Revisor externo real:** designarlo (otra persona, u otro proveedor) con el paquete de `REVISION_EXTERNA_PAQUETE.md`.
