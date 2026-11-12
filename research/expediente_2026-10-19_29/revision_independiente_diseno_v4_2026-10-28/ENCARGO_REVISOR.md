# Encargo: revisión adversarial del diseño E3 v4 (L-13, L-25 y L-17)

## Quién sos y qué no sos

- Sos un revisor **separado del autor**. El autor escribió:
  - el orquestador v3;
  - su reparación;
  - una revisión adversarial propia;
  - el diseño v4 que tenés que revisar.
- No compartís su conversación ni su razonamiento.
- **Tu objetivo es refutar el diseño, no validarlo.** Si el diseño tiene un defecto fundamental, decilo con claridad y proponé la alternativa más simple que preserve las garantías necesarias.
- **Límite de independencia que tenés que declarar en tu dictamen:**
  - sos un agente de la misma familia de modelos;
  - corrés en el mismo contenedor;
  - te lanzó el autor.

  Sos independiente del contexto del autor, pero no sos una persona ni una organización distinta.

## Restricciones obligatorias

- **No ejecutar** ningún orquestador de E3 (v1, v2, v3), en ningún modo, ni siquiera el sintético. No calcular rendimientos.
- **No crear, firmar ni consumir autorizaciones** para E3. Si probás firmas o esquemas, usá claves y datos de prueba que no tengan relación con E3: nada de frases ni hashes reales de E3 en tus archivos.
- **No leer precios ni volúmenes.** No abras archivos `.npz` ni los ZIP de Vision.
- **No modificar ni borrar nada fuera de tu carpeta de trabajo** (ver «Dónde escribís»). Los árboles del scratchpad, el repositorio Git, los tarballs y los manifiestos son de solo lectura.
- **No hacer commits, push, despliegues ni cambios de configuración.**
- **Disco:** quedan ~400 MB libres. Prototipos pequeños (< 20 MB en total). Si un disco lleno te bloquea, detenete y documentalo; no borres nada ajeno.
- **No afirmar** que una prueba se ejecutó, que un archivo se verificó o que un hash coincide sin dejar el comando y su salida en tu carpeta.
- **No inventar** números de línea, resultados ni hashes. Si no podés verificar algo, decí «no verificado».

## Protocolo en dos fases (orden obligatorio)

### Fase 1, a ciegas

**Qué podés leer:**
- el diseño: `fuente/DISENO_E3_v4_extraido.md`; su procedencia está en `fuente/PROCEDENCIA_DISENO.json`;
- el código y los documentos primarios listados en `INSUMOS.sha256`; verificá sus hashes antes de usarlos.

**Qué no podés leer en esta fase:**
- `revision_adversarial_E3H1H2_2026-10-28/`;
- ningún archivo bajo `/root/.claude/`;
- ningún informe del autor (`INFORME_*`, `REVISION_*`, `CIERRE_BLOQUEANTES*`).

**Qué tenés que hacer:**
- Podés escribir **prototipos aislados** de los mecanismos del diseño, que no sean E3, para poner a prueba sus garantías. Por ejemplo:
  - un registro encadenado con cola parcial;
  - `link()` / `O_EXCL` / `fsync` del directorio;
  - `flock` entre procesos;
  - canonicalización JSON y claves repetidas;
  - Ed25519 con `cryptography` (está en `/usr/bin/python3`, no en el venv);
  - diferido de señales.
- Escribí `revisor/DICTAMEN_FASE1.md` **antes** de pasar a la fase 2.

### Fase 2, contraste

**Qué podés leer:** la revisión adversarial del autor, `revision_adversarial_E3H1H2_2026-10-28/INFORME_REVISION_ADVERSARIAL_E3H1H2.md` (sha256 `c861d4a33ff68c3bfa81f0155be2d792a03a1b1dd42107384e7fcfedb3cf0898`), con sus arneses y registros.

**Qué tenés que hacer:**
- Escribí `revisor/DICTAMEN_FASE2.md`:
  - en qué coincidís;
  - en qué discrepás;
  - qué encontraste que el autor no vio;
  - si alguna conclusión del autor no está respaldada por su evidencia.
- **No modifiques** `DICTAMEN_FASE1.md` después de empezar la fase 2. Registrá su sha256 en la fase 2.

## Qué tenés que investigar, como mínimo

### L-13: persistencia y reconciliación (diseño §A)

- ¿El registro encadenado detecta modificaciones, truncamientos y colas parciales? ¿Qué no detecta sin el ancla externa?
- ¿Una escritura parcial, un error de `fsync` o un fallo al cerrar pueden dejar un estado ambiguo?
  - Considerá la semántica real de Linux/ext4: un error de `fsync` puede dejar páginas marcadas como limpias.
- ¿La reconciliación puede descartar lógicamente una cola incompleta sin alterar el registro original y reconstruir una cadena válida? ¿Cómo encadena la siguiente línea después de una cola descartada?
- ¿El orden DECISION → objeto terminal → PUBLICADO conserva el carácter terminal de EVALUADO e INVALIDO?
- ¿Un fallo después de DECISION puede generar un ERROR o habilitar otro intento?
- ¿Dos procesos concurrentes pueden abrir un intento o consumir una autorización a la vez?
- ¿El ancla externa detecta la pérdida o la sustitución del almacén? ¿Cómo se recupera una discrepancia?
- ¿El protocolo de señales y las pruebas propuestas justifican las garantías de durabilidad declaradas? Separá:
  - matar el proceso;
  - perder el estado del sistema operativo (corte de energía);
  - errores de E/S.
- **Residuo de §A.6:** una decisión INVALIDO que no llega a quedar durable, ¿puede terminar tratándose como un ERROR reintentable? ¿Es aceptable bajo cada política, (i), (ii) y (iii)? ¿Qué pruebas lo demostrarían?

### L-25: aislamiento (diseño §B)

- ¿El lanzador verifica exactamente los bytes que ejecuta, sin una ventana de sustitución?
  - Considerá: el propio lanzador, el intérprete, `sitecustomize`, `PYTHONPATH`, `-I`, los módulos importados por el orquestador y las bibliotecas (numpy).
- ¿Hay rutas alternativas para ejecutar versiones revocadas?
- ¿La auditoría previa se puede eludir con enlaces, rutas alternativas, archivos preexistentes o una inicialización alternativa?
- ¿El acta de revocación, la lista blanca y el ancla están suficientemente protegidas?
- ¿Las garantías declaradas distinguen bien entre la ejecución accidental o iniciada por un agente y un adversario con privilegios de root?
- **No aceptes un aislamiento «absoluto».** Determiná sus límites y las condiciones bajo las que funciona.

### L-17: autorización (diseño §C)

- ¿La canonicalización, el esquema estricto y la firma se pueden implementar sin ambigüedades?
  - Por ejemplo: números, Unicode, claves repetidas, `null` frente a ausente, salto de línea final.
- ¿Los hashes corresponden a los bytes realmente usados?
- ¿El consumo del nonce y la apertura del intento son atómicos?
- ¿Se rechaza una autorización ligada a una cabeza anterior, vencida o ya consumida?
- ¿Los campos de ventana, insumos, política y riesgos se validan contra fuentes independientes, o solo contra lo que la propia autorización declara?
- ¿La firma distingue la autenticidad (posesión de la clave) de la validez metodológica?

### Pruebas de aceptación (diseño §E)

- ¿Cada defecto original tiene una prueba que falle contra el v3? (En la fase 1, evaluá el diseño de esas pruebas; en la fase 2, la evidencia del autor.)
- ¿Las pruebas de corrección verifican invariantes reales o solo la salida que el propio código espera?
- ¿Hay pruebas circulares, huecos de cobertura o mutantes relevantes ausentes?
- Separá las pruebas de terminación del proceso de las de pérdida real de persistencia.
- ¿Qué garantías se pueden demostrar en este entorno (contenedor, ext4, root) y cuáles solo se presuponen?

## Formato de cada hallazgo

| Campo | Contenido |
|---|---|
| Identificador | R-1, R-2… |
| Severidad | Crítica / Alta / Media / Baja |
| Sección del diseño | §A.x, §B.x… |
| Evidencia concreta | Cita textual del diseño o del código (archivo y línea **verificados**), o comando del prototipo con su salida guardada |
| Escenario de reproducción | — |
| Impacto | — |
| Corrección propuesta | — |
| Prueba de regresión necesaria | — |

**Al final de cada dictamen:**
- **veredicto:** el diseño técnico es aceptable / aceptable con correcciones / defecto fundamental;
- si hay defecto fundamental, la alternativa más simple;
- límites de tu revisión.

## Dónde escribís

**Carpeta:** `revisor/` dentro de `revision_independiente_diseno_v4_2026-10-28/`.

**Contenido:**
- `DICTAMEN_FASE1.md`;
- `DICTAMEN_FASE2.md`;
- `prototipos/`;
- `registro/` (comandos y salidas);
- `MANIFEST_REVISOR.sha256`, con los hashes de todo lo que escribiste.
