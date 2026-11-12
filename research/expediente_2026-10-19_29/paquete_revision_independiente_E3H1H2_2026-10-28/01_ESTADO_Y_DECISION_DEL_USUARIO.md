# Estado actual y decisión del usuario

**Fecha:** 2026-10-28.

## Decisión del usuario (2026-10-28)

1. **La revisión independiente es condición PREVIA a cualquier recomendación de autorización.** El usuario no aceptó convertirla en una mera recomendación previa a la firma.
   - El informe de cierre del 2026-10-27 (`evidencia/cierre_bloqueantes…/INFORME_CIERRE_BLOQUEANTES_E3H1H2.md`, §8) proponía ese cambio.
   - **Esa parte del §8 queda sin efecto.** El archivo no se modificó, para conservar la evidencia tal como se entregó.
2. Hasta que termine la revisión:
   - no se ejecuta E3-H1/H2;
   - no se crean ni se consumen autorizaciones;
   - no se modifican el repositorio ni los árboles congelados.
3. El revisor tiene que pronunciarse expresamente sobre:
   - la Adenda R;
   - GTO→GFT;
   - 158 frente a 160 semanas;
   - los riesgos residuales.
4. Si el revisor detecta contradicciones o evidencia insuficiente, se detiene y las documenta.
5. Después de la revisión, el usuario presentará las decisiones metodológicas pendientes y evaluará **por separado** si corresponde autorizar una única ejecución restringida a la ventana A.

## Estado

| Aspecto | Estado |
|---|---|
| E3-H1/H2/H3 | **CERRADAS · NO EVALUABLES** (`CIERRE_E3.md`, 2026-10-20). No se reabrió nada |
| Dictamen vigente sobre la solicitud de autorización | **NO APTO PARA SOLICITAR AUTORIZACIÓN hasta que concluya la revisión independiente** (decisión del usuario) |
| Bloqueantes técnicos de la revisión del 2026-10-26 | Corregidos en el v3, según el autor. **Pendiente de confirmación independiente** |
| Decisiones metodológicas (D-A/B/C, D-1, D-2, D-3, D-4, D-5) | **Abiertas.** Las presenta el usuario después de la revisión |
| Autorizaciones existentes | Ninguna. El v3 rechaza la ejecución sin una (`evidencia/cierre_bloqueantes…/verificaciones/entrada_real_sin_autorizacion.txt`) |
| Registro de intentos del v3 (`INTENTOS_E3.jsonl`) | No existe: nunca se inició un intento |

## Riesgo de conservación de la evidencia

Toda la evidencia vive en el scratchpad de una sesión en la nube, que es efímero. El repositorio no la contiene y no se modificó, por decisión del usuario.

Este paquete existe también para que la evidencia **salga** de ese entorno: el paquete principal y el de datos se entregan como archivos descargables.

Lo que **no** viaja en ninguno de los dos queda identificado por su sha256 en `registro/INVENTARIO_E3_COMPLETO.sha256`. Si se pierde el entorno, se puede reconstruir y verificar con ese inventario:
- los ZIP descargados de Vision;
- los índices de Common Crawl;
- los registros de descarga.
