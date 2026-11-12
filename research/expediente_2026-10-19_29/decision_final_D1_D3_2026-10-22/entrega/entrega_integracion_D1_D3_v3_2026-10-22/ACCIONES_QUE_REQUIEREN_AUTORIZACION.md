# Acciones que todavía requieren tu autorización explícita

**Ninguna se ejecutó.** Cada una se autoriza por separado, en este orden.

| # | Acción | Dónde | Efecto | Reversible |
|---|---|---|---|---|
| 1 | Crear la rama local `fix/backtest-d1-d3-and-engine-provenance` desde `72ffae5` | `/home/user/Trader-IA` | Modifica el repositorio original: refs y árbol de trabajo | Sí (borrar la rama) |
| 2 | Aplicar 01 + 02v3 y **un** commit | Ídem | Primer commit de la unidad inseparable | Sí (reset local antes del push) |
| 3 | Aplicar 03 y su commit | Ídem | Commit de pruebas | Sí |
| 4 | `git push -u origin fix/…` | GitHub `elianengelberg/trader-ia` | Publica la rama; **dispara la CI por primera vez** | La rama se borra, pero el push queda visible en el historial de eventos |
| 5 | Abrir el PR en borrador hacia `claude/algo-trading-simulation-platform-ngf7xo` | GitHub | PR visible | Se puede cerrar |
| 6 | (Opcional) 04: commit o PR aparte con `constraints/ci-py311.txt` y el cambio de `ci.yml` | GitHub | Cambia la configuración de CI | `git revert` |
| 7 | Merge del PR | GitHub | Integra en la rama base | `git revert`, con PR de reversión |

**Fuera de esta lista y fuera del alcance de cualquier autorización de integración:**
- deploy, reinicio de servicios o cambios de configuración operativa;
- trading real, envío de órdenes o cambios en `validada_para_operar`;
- tocar E1, E3-H1, T-MULTI, T-papel, el prerregistro o las ventanas reservadas.

**Lo que no requiere autorización** porque no publica ni modifica nada:
- repetir las verificaciones (`reproducir.sh`, `COMANDOS_DE_VERIFICACION.md`) en directorios nuevos;
- leer la evidencia.
