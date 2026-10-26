# AVISO — rama de revisión `revision/candidata-v3`

> **Esta rama NO está aprobada para merge, ni para Binance Testnet, ni para operar con dinero real.**
> Existe solo para que la candidata v3 se revise y se corra la CI remota.
> Una CI en verde **no** demuestra seguridad operativa ni rentabilidad.

## Qué es

- **Base:** `c6339e3fcd6041cb6c4ad7f5545f0ff306a4fd2f`, ancestro de la punta de la rama por omisión (`claude/algo-trading-simulation-platform-ngf7xo`, `72ffae5`).
- **Los 4 commits que la rama por omisión tiene después de `c6339e3`:** solo `research/`. No tocan ningún archivo de esta serie. La serie aplica limpia sobre ellos y da el mismo diff.

| # | Commit | Contenido |
|---|---|---|
| 1 | `090087fa0c87779670df1c947116c47bb6dc3cef` | Correcciones de la misión v2 (32 parches; tree `c56419157a81…`) |
| 2 | `16c09929699c66e1b431681cfa09f837e9ec2e19` | H11: lock de sesión entre procesos |
| 3 | `05c7c0d0b8e6a7b4c18a8b3f2bfba60e7d89033a` | B1 + B2: semántica del venue para el stop |
| 4 | `bcf3a6e235d6d0e7fdd6e6251ef4225fb01fa1e3` | D21: filtros del venue al iniciar la sesión live |
| 5 | `ad338011410f26323ad20bf191613422941f45e3` | D3: SIGTERM y tope del apagado |
| 6 | `e6a80c1caa3d7a18005ed694390ef0ad5ad6d05b` | CI v3 (tree `ef1983b6c87414478a8ed139ea79e91919f46c0e`) |
| 7 | (ver `git log`) | CI de revisión: PostgreSQL aislado, rol sin superusuario, conteos como anotaciones |
| 8 | (ver `git log`) | Este aviso, el informe de la revisión independiente y los bloqueantes |

Los commits 1 a 6 son exactamente los de la entrega local v3: mismos hashes, verificables con el bundle de esa entrega. Los commits 7 y 8 se agregaron para publicar.

**Identidad de los commits:**
- 1 a 6: «Trader-IA candidata local (Claude) <noreply@anthropic.com>»;
- 7 y 8: «Claude <noreply@anthropic.com>».

Ningún commit está firmado ni se atribuye al dueño del repositorio.

## Estado

| | Etapa | Estado |
|---|---|---|
| A | Integridad de la entrega | Aprobada |
| B | Calidad técnica (para merge) | **No aprobada** |
| C | Publicar esta rama de revisión | Autorizado por el dueño (2026-10-26) |
| D | CI remota | Autorizada por el dueño (2026-10-26) |
| E | Binance Testnet | **No aprobada** |
| F | Dinero real | **No aprobada** |
| G | Rentabilidad | No evaluable: ninguna prueba de software la demuestra |

## Por qué no se aprueba para operar

Hay defectos críticos del camino live, demostrados con pruebas sobre un venue simulado y verificados en el código. El detalle está en `BLOQUEANTES_OPERATIVOS.md` y en `INFORME_REVISION_INDEPENDIENTE_V3.md`:

1. Los fills que llegan después del envío (un stop que salta, una limit que se llena después) nunca se registran.
2. Al ajustar el stop, se cancela la protección válida antes de confirmar la nueva.
3. Comisión en el activo base o en BNB: estados sin stop, polvo que bloquea y comisiones valuadas como si fueran USD.
4. No hay exclusión entre el market maker live y la sesión live sobre una misma cuenta.
5. El apagado no entra en el plazo de `docker stop` y se cuelga si PostgreSQL deja de responder.

## Qué no debe hacerse con esta rama

- Merge a cualquier rama.
- Desplegarla.
- Activar `TIA_LIVE__ENABLED`.
- Correrla contra Binance Testnet o contra una cuenta real.
- Correr la suite PostgreSQL contra un servidor compartido con un rol superusuario.
