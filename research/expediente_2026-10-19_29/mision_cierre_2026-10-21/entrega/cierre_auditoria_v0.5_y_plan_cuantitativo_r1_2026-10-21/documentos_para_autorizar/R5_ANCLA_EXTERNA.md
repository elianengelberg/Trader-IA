# R-5 / B-2 — Ancla externa: comparación y recomendación

**Estado: NO EXISTE NINGÚN ANCLA EXTERNA.**
- Lo que está probado es el **cliente** (`AnclaFirmada`) contra un **doble de prueba** local (v0.5, contrato C1–C8).
- Nada de este documento está activado.

## 1. Qué tiene que resolver
| Necesidad | Por qué | Eslabón (03_CADENA_DE_CONFIANZA.md) |
|---|---|---|
| **Comparación y escritura atómica** (una reserva por cálculo) | Uso único: impide correr varias veces y quedarse con la mejor (G3) | 6 |
| **Fecha pública de un hash** | Prueba que un prerregistro o un resultado existía antes de cierta fecha | 1, 2, 7 |
| **Cabeza del registro fuera del equipo** | Hoy una reescritura **coherente** del registro local no se detecta (D-4 y amenaza A-02) | 6, 10 |

## 2. Opciones (las de `DISENO_ANCLA_EXTERNA.md` §6, más OpenTimestamps)
Escala: 1 = peor, 5 = mejor. La puntuación es mi juicio técnico; la justificación está en la última columna.

| Opción | Independencia | Verificable por terceros | Resistencia a la manipulación | Recuperación | Costo operativo | Comparación y escritura | Justificación |
|---|---|---|---|---|---|---|---|
| O1 servicio propio con KMS/HSM | 3 | 3 | 4 | 3 | 1 | Sí | Fuerte, pero hay que operarlo y la confianza recae en quien lo administra |
| **O2 repositorio git remoto con rama protegida** | 4 | 4 | 4 | 5 | 5 | **Sí** (empuje sin forzar = avanzar solo si la punta es la esperada) | Gratis, historial completo en cada clon. El administrador debe ser otra persona que el entorno de ejecución |
| O3 registro de transparencia público (Sigstore/Rekor) | 5 | 5 | 5 | 4 | 4 | No | Excelente para sellos; puede asociar una identidad pública a la entrada |
| O4 sello de tiempo RFC 3161 | 4 | 4 | 4 | 3 | 4 | No | Depende de la autoridad y de sus certificados |
| **O5 OpenTimestamps** (cadena de bloques pública) | 5 | 5 | 5 | 5 | 5 | No | Gratis, sin cuenta, solo publica un hash; la prueba se verifica sin conexión. La confirmación tarda horas |

## 3. Recomendación concreta
**O2 + O5:**
1. **O2 para la comparación y escritura atómica y la cabeza del registro.** Un repositorio privado y dedicado
   (p. ej. `trader-ia-ancla`), separado del de investigación, con:
   - una rama `ancla` protegida: sin forzar, sin borrar, commits firmados;
   - un administrador que seas vos, con doble factor por llave física;
   - un token de grano fino con escritura **solo** en ese repositorio y **sin** permisos de administración, entregado
     al entorno como secreto, nunca en el chat.

   Así el entorno puede avanzar la rama pero no reescribirla.
2. **O5 para la fecha pública.** Sellos de:
   - la declaración firmada de T;
   - cada prerregistro al congelarlo;
   - la cabeza diaria del registro.

   Solo sale un hash; el contenido nunca sale.
3. **Por qué no O1:** el costo de operar un servicio no se justifica con la amenaza actual: un único operador, sin
   adversario externo con incentivos.
4. **Por qué no solo O5:** no ofrece la comparación y escritura atómica del uso único.

## 4. Lo que exige activarlo (cada paso requiere tu autorización)
| Paso | Quién | Duración estimada | Reversible |
|---|---|---|---|
| Crear el repositorio, la protección y el token | Vos | 30 min | Sí, se borra |
| Adaptador `AnclaGit` que cumpla el contrato C1–C8, probado primero contra un repositorio local sin red | Yo, con autorización | 1 día | Sí |
| Publicar hashes en OpenTimestamps | Yo, con autorización expresa: **publicar es irreversible** | Minutos | **No** (el hash queda público para siempre; el contenido no) |
| Integrar en un ejecutor (B-3) | Yo, con autorización | Ver B-3 | Sí, hasta el primer uso real |

## 5. Riesgos residuales de la recomendación
- **Compromiso de tu cuenta de la plataforma:** se mitiga con doble factor por llave física y con O5 como segunda fuente.
- **Disponibilidad de la plataforma:** el ejecutor debe fallar **cerrado** (sin ancla no hay cálculo) y nunca seguir
  en local.
- **Metadatos públicos (O5):** la hora de cada sello es pública; el contenido no.
- **Un recibo prueba registro, no cálculo:** eso solo lo resuelve una reproducción independiente (A14).
