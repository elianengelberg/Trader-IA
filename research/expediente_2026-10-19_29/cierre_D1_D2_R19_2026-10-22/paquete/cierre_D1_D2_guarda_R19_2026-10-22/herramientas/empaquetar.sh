#!/usr/bin/env bash
# Arma el paquete de esta misión (solo copia; no modifica las fuentes). Uso: empaquetar.sh <M> <nombre>
set -euo pipefail
M="$1"; N="$2"; D="$M/paquete/$N"
[[ -e "$D" ]] && { echo "$D ya existe"; exit 1; }
mkdir -p "$D"/{fase1,fase2/{guarda,parche,evidencia,herramientas},fase3/{herramientas,validacion_sonda},registro,herramientas}
cp "$M"/docs/*.md "$D/"
cp "$M"/fase1/entrega/entrega_integracion_D1_D3_v3r3_2026-10-22.zip "$M"/fase1/entrega/entrega_integracion_D1_D3_v3r3_2026-10-22.zip.sha256 \
   "$M"/fase1/entrega/VERIFICACION_EXTRACCION_LIMPIA_v3r3.txt "$D/fase1/"
cp "$M"/fase1/build/entrega_integracion_D1_D3_v3r3_2026-10-22/CAMBIOS_REVISION_r3.md "$M"/fase1/build/entrega_integracion_D1_D3_v3r3_2026-10-22/CAMBIOS_r3_v3r2_a_v3r3.diff "$D/fase1/"
cp "$M"/fase2/JUSTIFICACION_GUARDA_VERSION.md "$D/fase2/"
cp "$M"/fase2/guarda/test_engine_version_contract.py "$D/fase2/guarda/"
cp "$M"/fase2/parche/05_propuesta_guarda_version_motor.patch "$D/fase2/parche/"
cp "$M"/fase2/G_mutantes_guarda.json "$M"/fase2/G_mutantes_guarda.txt "$M"/fase2/G_mutantes_guarda_final.json "$M"/fase2/G_mutantes_guarda_final.txt "$M"/fase2/permanencia_stop_tiempo.txt "$M"/fase2/margenes_g_obl.json "$M"/fase2/margenes_g_solo02.json "$D/fase2/evidencia/"
cp "$M"/fase2/robustez/*.json "$M"/fase2/robustez/RESUMEN_ROBUSTEZ.txt "$D/fase2/evidencia/" 2>/dev/null || true
cp "$M"/fase2/evidencia_extra/* "$D/fase2/evidencia/" 2>/dev/null || true
cp "$M"/fase2/guarda/medir_margenes.py "$M"/fase2/guarda/mutantes_guarda.py "$M"/fase2/guarda/robustez_guarda.py "$M"/fase2/guarda/lanzar_robustez.sh "$M"/fase2/guarda/resumir_robustez.py "$M"/fase2/guarda/permanencia_sin_rechazo.py "$D/fase2/herramientas/"
cp "$M"/fase3/PLAN_R19_ENMIENDA_1.md "$M"/fase3/R19_RESULTADOS_Y_LIMITES.md "$M"/fase3/plan_r19_enmienda1.json "$D/fase3/"
cp "$M"/fase3/herramientas/*.py "$D/fase3/herramientas/"
cp "$M"/fase3/validacion_sonda/arbol/tests/integration/test_validacion_sonda_r19.py "$D/fase3/validacion_sonda/"
for v in v2 v3 mecanica2; do mkdir -p "$D/fase3/validacion_sonda/$v"; cp "$M"/fase3/validacion_sonda/$v/*.json "$M"/fase3/validacion_sonda/$v/*.log "$D/fase3/validacion_sonda/$v/" 2>/dev/null || true; cp "$M"/fase3/validacion_sonda/$v/*.jsonl "$D/fase3/validacion_sonda/$v/" 2>/dev/null || true; done
cp "$M"/fase3/validacion_sonda/plan_mecanica.json "$D/fase3/validacion_sonda/"
cp "$M"/registro/*.txt "$D/registro/"
cp "$M"/herramientas/estado_repo.sh "$M"/herramientas/verificar_extraccion_limpia.sh "$M"/herramientas/empaquetar.sh "$D/herramientas/"
cp "$M"/../cierre_revision_D1_D3_2026-10-22/herramientas/congelados.sh "$D/herramientas/"
find "$D" -name __pycache__ -prune -exec rm -rf {} + ; find "$D" -name "*.pyc" -delete
(cd "$D" && find . -type f ! -name SHA256SUMS | sed 's#^\./##' | LC_ALL=C sort | xargs -d '\n' sha256sum > SHA256SUMS)
echo "archivos: $(wc -l < "$D/SHA256SUMS")"
