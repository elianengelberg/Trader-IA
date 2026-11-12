# B-1 (y D-G6) — Plan para aplicar los parches 0001–0007 y publicar commits

**Nada de esto se hizo.** El repositorio sigue en HEAD `692f2b2`, con la huella `87b9585d…` y sus cambios preexistentes.

## 1. Qué hay
- `parches/v0.5/0001…0007` del ZIP v0.5 (`5bf9bc5d…`): diffs unificados que **solo agregan archivos** bajo
  `research/tendencia_btc/verificacion/` (60 rutas).
- Comprobados de nuevo en esta misión (`evidencia/B7_parches.txt`, extraído de la reproducción limpia):
  - `git apply --check` y `git apply` en orden: OK sobre HEAD exportado (`692f2b2`) y sobre origin exportado (`c6339e3`);
  - la suite pasa en las dos copias;
  - ninguna ruta existe ya en la copia de trabajo.

## 2. Dos decisiones acopladas
| Decisión | Opciones | Consecuencia |
|---|---|---|
| **Base de la rama** | (a) desde HEAD `692f2b2` | Publicar la rama publica también `f518ac1` y `692f2b2`, el congelado de T-MULTI. Es D-G6 |
| | (b) desde origin `c6339e3` | No publica T-MULTI. Los parches también aplican y pasan ahí |
| **Publicar** | No / sí | Sin publicar, nada es verificable desde fuera. Publicar es **irreversible** en la práctica: puede quedar en cachés o forks |

**Recomendación:** (a) y publicar, porque además da la fecha pública que necesita R-3. Si preferís no publicar T-MULTI
todavía, (b).

## 3. Procedimiento exacto (una vez autorizado)
```
# 0. integridad del paquete
sha256sum SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip   # debe dar 5bf9bc5d004b51188fdd407ae71eaae2ccefec7251af7001f8d89b264b4f5308
unzip -q SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip && (cd solucion_final_trader_ia_v0.5_2026-10-20 && sha256sum -c --quiet SHA256SUMS.txt)
# 1. rama nueva, sin tocar los cambios preexistentes (research/.gitignore, ARTEFACTOS_SHA256.txt, PRERREGISTRO_PAPEL.md,
#    corte.py, etc. quedan fuera: se agregan solo rutas exactas)
git switch -c verificacion-v0.5 692f2b2        # o c6339e3 con la opción (b)
for p in solucion_final_trader_ia_v0.5_2026-10-20/parches/v0.5/000[1-7]-*.patch; do
  git apply --check "$p" && git apply "$p" || { echo "FALLA $p"; exit 1; }
done
git status --porcelain | grep -v '^?? research/tendencia_btc/verificacion/' # solo deben aparecer los cambios preexistentes
(cd research/tendencia_btc && python -m pytest -q verificacion/pruebas)      # mismo resultado que evidencia/61_*
git add research/tendencia_btc/verificacion/
git commit -m "Verificación v0.5 (P1, P2, P4, ejecutor aislado): parches 0001-0007 sin modificar"
# 2. publicar, SOLO con tu autorización expresa
git push -u origin verificacion-v0.5
```
**Reversión:**
- antes de publicar: `git switch -` y `git branch -D verificacion-v0.5`;
- después: `git revert` del commit. No se reescribe una historia publicada.

## 4. Lo que este plan NO incluye
- Versionar `papel/corte.py`: es una decisión aparte sobre el papel congelado de T.
- Aprobar una raíz (R-3): un commit separado y revisado que agrega tu clave pública a `RAICES_CONFIANZA`.
- La corrección v0.5.1 de la etapa 13 (`correcciones_propuestas_v0.5.1/`): es del arnés del paquete y no entra en el
  repositorio.
