# 03 — Cadena de confianza: de la hipótesis a la conclusión

**Una cadena es tan fuerte como su eslabón más débil.**
- Hoy **todos** los controles viven en el mismo equipo y los escribió el mismo autor.
- Detectan errores y alteraciones **incoherentes**, pero no a alguien que controle el equipo y reescriba todo de forma
  coherente.
- Eso solo lo cambia una referencia **fuera** del equipo (R-3, R-5) y una revisión independiente (B-7).

## 1. Esquema
```
 [1] Hipótesis ──► [2] Prerregistro ──► [3] Datos ──► [4] Código + dependencias ──► [5] Entorno
   tarjeta,          esquema PEC-1.0,     manifiesto     P4 reserva el hash del       P4 liga el
   mecanismo         semántica, hash      SHA-256 +      código, de las entradas      ejecutor y el
   (05 §4)           (congelar)           validador      y de la semilla              entorno a la
                     ▲ ancla externa:     V1–V9          ▲ falta un lockfile con      reserva
                     NO EXISTE (R-5)      ▲ procedencia  hashes de dependencias
                                          independiente:
                                          NO (B-4)
        │
        ▼
 [6] Ejecución + registro ──► [7] Resultado bruto ──► [8] Métricas derivadas ──► [9] Validación independiente
   P4 uso único, ancla          presellado en el ancla;  deterministas; P1         REPRODUCIDO exige una
   LOCAL; registro de           P1 lee una sola vez y    contrasta hashes; P2      reproducción autenticada
   decisiones encadenado        lo compara con el        recalcula la decisión     de otra persona o
   ▲ reescritura coherente:     presellado y el recibo                             entorno: NO HAY NINGUNA
     NO se detecta (local)                                                         (A9/A14, B-7)
        │
        ▼
 [10] Aprobación de la conclusión ──► [11] Autorización de publicación o integración
   tu firma con una raíz aprobada       P2 solo CONSTATA una autorización registrada;
   (VERIFICADO): NO EXISTE (R-3)        nunca la otorga. Registro de autorizaciones: VACÍO
```

## 2. Eslabón por eslabón
| # | Eslabón | Qué lo controla hoy | Qué detecta | Qué NO detecta | Control proporcionado pendiente | Evidencia |
|---|---|---|---|---|---|---|
| 1 | Identidad e integridad de la hipótesis | Tarjeta y prerregistro PEC-1.0; registro del programa (39 entradas) | Una hipótesis cerrada, descartada o no aprobada que se intenta iniciar | Una hipótesis «nueva» que en realidad es una variante, si se le cambia el nombre (juicio humano) | Revisión de la familia por un tercero | `test_registro_del_programa` |
| 2 | Prerregistro y parámetros | `pec.prerregistro`: esquema, semántica y SHA-256 canónico | Rejillas de parámetros, ventanas solapadas, el período reservado, α incoherente con Bonferroni, la fase prospectiva sin δ, reaperturas sin aprobación y cambios después de congelar | Que el congelamiento haya ocurrido **antes** de mirar los datos: el hash es local y sin fecha | Sello externo (O5) y cabeza en O2 al congelar | 31 pruebas en `test_decision_prerregistro_programa.py` |
| 3 | Procedencia e integridad de los datos | Manifiestos con SHA-256 (proyecto); validador V1–V9 (nuevo) | Corrupción, huecos, duplicados, conflictos, velas incompletas, OHLC incoherente y filas fuera de la ventana | Que la fuente sea correcta: solo hay sumas del mismo proveedor; no hay segundo proveedor | Muestra cruzada con un proveedor independiente (B-4, paso 5) | `test_datos_y_mirada_futuro.py` |
| 4 | Código y dependencias | P4 reserva el SHA-256 del código; parches con el SHA-256 de cada archivo | Un cambio del código reservado entre la reserva y el cálculo | Cambios en dependencias: el entorno no tiene un lockfile con hashes | Lockfile con hashes (`pip --require-hashes`) por hipótesis | v0.5 `test_p4_*` |
| 5 | Configuración y entorno | P4 liga ejecutor, entorno, límite y semilla a la reserva; el ejecutor exige un límite | Cambiar la configuración después de reservar | Diferencias de plataforma (otra versión de Python o de la biblioteca matemática) | Registrar la versión exacta y reproducir en otro entorno (A14) | v0.5 `evidencia/54_*` |
| 6 | Ejecución y registro de eventos | P4 uso único (diario, ancla local, `flock`, fsync); registro de decisiones encadenado | Repetición, sustitución, restauración del estado, truncamiento, cortes de energía simulados y entradas incoherentes inyectadas | **Una reescritura coherente** del diario y del ancla local, o del registro de decisiones, por quien controle el equipo. El registro de acciones de v0.5 además es una reconstrucción posterior (D-4) | Ancla externa O2 y sello diario de la cabeza del registro (O5) | v0.5 `test_inyeccion_en_el_registro` (límite documentado) |
| 7 | Resultados brutos | Presellado del SHA-256 en el ancla; P1 lee una sola vez | Que se cambie el archivo después del presellado | Que el presellado se haya hecho sin calcular (un recibo prueba registro, no cálculo) | Reproducción independiente | v0.5 X2/X13 |
| 8 | Cálculos y métricas derivadas | Funciones deterministas; P2 recalcula la decisión desde la evidencia | Que una decisión no coincida con su evidencia | Un error de fórmula **compartido** por la implementación y su verificación (mismo autor) | Contraste diferencial (hecho contra E3: mismo autor, limitado) y revisión por un tercero (B-7) | `test_diferencial_contra_la_implementacion_de_E3` |
| 9 | Validación independiente | P1 acepta REPRODUCIDO solo con una reproducción autenticada como tal | Una «reproducción» en memoria o no autenticada (F3) | **No existe ninguna reproducción independiente** de nada | Otra persona u otro entorno, con código determinista; presentar todas las reproducciones | v0.5 X21–X24 |
| 10 | Aprobación de la conclusión | P1 exige una raíz aprobada para VERIFICADO; `RAICES_CONFIANZA` está vacío | Firmas falsas, claves degeneradas (F1) y declaraciones de otro emisor | Dónde está la clave privada: el código no puede saberlo | Tu firma con una clave fuera de línea (R-3) | 807 casos contra OpenSSL |
| 11 | Autorización de publicación o integración | P2 separa validez de autorización; registro de autorizaciones vacío; `accion_ejecutada = NINGUNA` | Que una evidencia válida se convierta sola en una autorización (X4, X16, X26) | Una autorización registrada por quien controla el equipo | Autorización firmada por el propietario y anclada | v0.5 `test_X4_*`; análisis estático B6 |

## 3. Qué demuestra la criptografía de este sistema, y qué no
- **Ed25519 demuestra** que quien tenía la clave privada correspondiente a una clave pública firmó **esos bytes**.
  Con las comprobaciones de v0.5 (sin cofactor, rechazo de claves y R de orden pequeño o mixto, s canónico), no se
  puede falsificar sin la clave.
- **No demuestra:**
  - que el contenido firmado sea verdadero o legítimo;
  - que el firmante fuera quien decimos;
  - que la clave esté fuera de este equipo;
  - **cuándo** existió algo antes de la firma.
- **La autenticidad de T no la prueba Ed25519:** la prueba tu firma, si la clave es tuya y está fuera del equipo. Aun
  así, solo prueba lo que aceptás en la fecha de la firma.
- **Una cadena de hashes local** (registro de acciones, registro de decisiones, diario de P4) prueba coherencia
  interna. Quien controle el equipo puede **regenerarla entera** de forma coherente. La detección exige que su cabeza
  esté fuera (O2/O5), y eso solo vale tanto como la independencia y la disponibilidad de esa referencia.
- **No se agrega más criptografía:** ninguna amenaza actual la justifica. La brecha no es criptográfica sino de
  **ubicación** de la referencia (fuera del equipo) y de **independencia** de las personas (revisión y reproducción).
