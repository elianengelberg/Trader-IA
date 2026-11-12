# R-3 / A12 — Declaración de T para revisar y, si estás de acuerdo, firmar

**Nadie la firmó.** No se creó, usó ni simuló ninguna clave tuya. Este documento existe para que puedas decidir en
pocos minutos.

## 1. Qué firmarías: exactamente estos bytes
| Archivo (en esta carpeta) | SHA-256 | Qué es |
|---|---|---|
| `DECLARACION_A_FIRMAR_FUERA_DE_MUESTRA_T.bin` | `d7515c0dbd55beacbe0fa82d48a5168fa514b940515fd31e56926c6aadc504f4` | **Lo que se firma**: la forma canónica del JSON |
| `DECLARACION_A_FIRMAR_FUERA_DE_MUESTRA_T.json` | `ae6694213c611446243eaef64aff6dc06643ac994f0266d5c96c44661c09466c` | El mismo contenido, legible |

Las dos son copias idénticas de las de v0.5 (`trazabilidad_T/`, ZIP `5bf9bc5d…`).

Comprobado en esta misión, de forma independiente (`evidencia/C1_declaracion_T.txt`):
- el `.bin` es exactamente `json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` del `.json`;
- los tres SHA-256 declarados coinciden con los archivos actuales de `research/tendencia_btc`.

**Contenido** (tres artefactos, nada más):

| Ruta | SHA-256 |
|---|---|
| `experimentos/fuera_de_muestra_T.json` | `4f8fafde372931aab29b94612eb658f5fac9259e51cdf7dace7a1b30fc633c45` |
| `experimentos/fuera_de_muestra_T.py` | `941b6e11f6566319b93614ee671b184d60c7b5fbc64a3931a6ff2c8da17fe0fa` |
| `PRERREGISTRO_FUERA_DE_MUESTRA_T.md` | `94a165560ba2a1807bf604b079dbf2c8eea7e7e4401fcc5ccb5db275464db58f` |

**Contexto** dentro de los bytes:
- `emisor: PROPIETARIO-T`;
- `emitida_utc: 2026-10-20T20:45:39Z` (fecha de preparación; la fecha de tu firma es otra);
- `commit_local: 692f2b2…`;
- un propósito.

Si querés otra fecha u otro texto, hay que regenerar los bytes: cualquier cambio cambia el hash.

## 2. Qué significa tu firma, y qué no
| Sí significa | No significa |
|---|---|
| «Yo, con mi clave, acepto que estos tres archivos, con estos hashes, son los artefactos fuera de muestra de T» | Que el prerregistro **precediera** al resultado: los tres entraron en el mismo commit local sin publicar |
| P1 pasa de INCONCLUSO a VERIFICADO, si la raíz se aprueba con un cambio de código revisado | Que T tenga ventaja: sigue siendo EVIDENCIA INSUFICIENTE (P = 0,755) y P2 sigue NO_CANDIDATA |
| A partir de la fecha de la firma, nadie puede alterar esos archivos sin que se detecte | Que nada cambiara **antes** de la firma |
| | Que la clave esté fuera de este equipo: eso lo garantizás vos, el código no lo puede comprobar |

## 3. Requisitos
- Clave Ed25519 generada y guardada **fuera** de este entorno: idealmente una llave física o un equipo sin conexión.
  `openssl genpkey -algorithm ed25519` genera claves válidas; P1 v0.5 rechaza claves degeneradas.
- El procedimiento exacto con OpenSSL está en `trazabilidad_T/INSTRUCCIONES_FIRMA.md` de v0.5 y fue probado con una
  clave sintética (`test_procedimiento_de_firma_del_propietario_con_openssl`).
- **Aprobar la raíz:** agregar tu clave pública a `RAICES_CONFIANZA` mediante un cambio de código revisado (B-1). Mientras
  el verificador no esté en un commit publicado y revisado, quien edite el verificador puede agregar otra raíz
  (`04_MATRIZ_DE_AMENAZAS.md`, A-19).

## 4. Recomendación
**Firmar y, por separado, autorizar la publicación de `f518ac1` y `692f2b2`** (D-G6). Sin la publicación, la firma
fija los hashes desde hoy, pero no da ninguna prueba pública de fecha. Con ella, un tercero puede ver cuándo existieron
esos commits.

**Alternativas:**
- (a) **No firmar:** T queda INCONCLUSO para siempre; no se puede repetir.
- (b) **Firmar sin publicar:** VERIFICADO, sin prueba pública de fecha.
- (c) **Firmar y publicar:** la opción más fuerte disponible.

Ninguna cambia la conclusión económica sobre T.

## 5. Si firmás, devolvé solo esto
- la clave pública (64 hexadecimales);
- la firma (128 hexadecimales);
- la fecha de aprobación de la raíz (`AAAA-MM-DDTHH:MM:SSZ`).

**Nunca** la clave privada.
