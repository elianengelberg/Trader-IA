# R-2 · Mecanismo concreto de ancla externa (especificación; **no existe todavía ninguna ancla real**)

## Por qué hace falta

Las pruebas de la fase anterior (`cierre_decisivo_v4_2026-10-29/tecnico/registro/R2_exhaustiva.json`) mostraron:
- Con un disco que confirma `fsync` sin persistir y **sin** registro externo, hubo 15 reaperturas después de leer datos y 14 decisiones calculadas clasificadas como «no decidido».
- Con un registro externo, 0.

Ningún mecanismo local puede detectar una falsa confirmación de persistencia que se perdió en un corte: hace falta un testigo **fuera** del contenedor.

## Qué servicio lo provee: dos testigos independientes

Son los dos de la hoja de ruta del 2026-10-21 (§5, D-G4 y R-5).

| Testigo | Qué es | Qué prueba | Qué no prueba |
|---|---|---|---|
| **T1 · Rama `registros` protegida en GitHub** (este repositorio) | Ruleset con:<br>• push forzado prohibido;<br>• borrado prohibido;<br>• historia lineal;<br>• solo vos actualizás, sin excepción para administradores.<br>Un commit por evento, con el sha256 del registro local y el del commit anterior | **Orden y «último estado»:** el lanzador lee la cabeza anclada más reciente con `git ls-remote` o `git fetch` y la compara | Independencia de GitHub y de vos: los dos lo controlan |
| **T2 · OpenTimestamps** | `ots stamp` sobre el mismo archivo de eventos. Los calendarios públicos lo anclan en Bitcoin en unas horas | **Existencia antes de una fecha**, independiente de GitHub y de vos | Orden ni completitud: no sirve como «último estado». Tampoco autoría (para eso está la firma) |

## Qué se firma

**Un evento por línea, en JSON canónico** (claves ordenadas, sin espacios, solo ASCII):

```
{"experimento":"E4","evento":"ABIERTO_DURABLE|ANUNCIO_DECISION|PUBLICADO_DURABLE|EVALUACION|CIERRE",
 "seq":<int>,"cabeza_sha256":"<sha256 de la última línea durable del registro local>",
 "prerregistro_sha256":"<…>","utc":"YYYY-MM-DDTHH:MM:SSZ"}
```

- **Firma Ed25519** con una clave de máquina dedicada (`ancla_e4`). Su clave pública queda fijada en el prerregistro.
- **La clave privada no sale del entorno aislado.** No es una autorización de E3 ni de nada: solo atestigua eventos.
- **Archivo anclado:** `anclas/E4/EVENTOS.jsonl` en la rama `registros`, con la firma en `.sig` y la prueba OTS en `.ots`.

## Cuándo se ancla (sincrónico, regla del R-2)

| Momento | Regla |
|---|---|
| Antes de leer cualquier dato | `ABIERTO_DURABLE` anclado en T1 (el push confirmado devuelve el sha del commit) |
| Antes de escribir una DECISION | `ANUNCIO_DECISION` anclado en T1 (anuncio previo) |
| Después de publicar | `PUBLICADO_DURABLE` en T1, y OTS del archivo |
| En E4 | `EVALUACION` anclado antes de escribir `RESULTADO_E4.json`, y cada lote semanal de `RECOLECCION` (para fijar qué datos existían antes de evaluar) |

## Cómo se verifica

**Comprobación previa, antes de cualquier apertura:**
- se lee la última línea anclada de T1;
- el registro local tiene que contener esa misma `cabeza_sha256` en el mismo `seq`.

| Situación | Resultado |
|---|---|
| T1 tiene un `ABIERTO_DURABLE` que el registro local no tiene | INCIERTO terminal. Nunca se reabre |
| T1 tiene un `ANUNCIO_DECISION` que el registro local no tiene | DECISION_ANUNCIADA_NO_PERSISTIDA |
| Cualquier otra discrepancia de cabeza | BLOQUEADO (revisión humana) |

**Auditoría posterior:**
- `ots verify` de cada `.ots` contra Bitcoin;
- verificación de la firma Ed25519 de cada línea con la clave pública fijada.

## Qué pasa si el ancla no está disponible

| Momento | Consecuencia |
|---|---|
| **Antes de `ABIERTO`** | La comprobación previa falla y no se consume nada; se puede volver a intentar cuando el ancla esté disponible |
| **Después de `ABIERTO`, al anunciar la decisión** | El proceso **no escribe** la DECISION. Reintenta el anclaje con espera exponencial hasta 24 h. Si no lo logra, escribe `ERROR(ancla_no_disponible)` y termina: NO EVALUABLE, terminal, sin repetición (D-7) |
| **Si muere mientras espera** | La reconciliación ve una etapa de decisión sin anuncio anclado: INCIERTO, terminal |
| **Si T2 (OTS) no está disponible** | No bloquea: se reintenta en la auditoría. T1 es el testigo operativo y T2 el independiente |

## Qué requiere tu autorización (nada de esto se hizo)

1. Crear la rama `registros` desde `72ffae5` y configurar su ruleset en GitHub (lo hacés vos).
2. Autorizar los push a `registros`: **solo** archivos bajo `anclas/` y registros de experimentos, un evento por commit.
3. Instalar el cliente `opentimestamps-client`, fijado por hash, en el entorno aislado, y habilitar la salida de red a los calendarios de OpenTimestamps.
4. Generar la clave de máquina `ancla_e4` y fijar su clave pública en el prerregistro.

## Límite honesto

- T1 depende de GitHub y de tu cuenta.
- T2 no da orden.
- Juntos detectan la pérdida o el retroceso del registro local y la falsa persistencia. **No** impiden que alguien con tu cuenta reescriba T1.
