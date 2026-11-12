#!/usr/bin/env bash
# Registro 99 (solo lectura): estado final del repositorio protegido, congelados, entregas previas y procesos residuales,
# con los mismos comandos que el registro inicial A2, comparado contra él.
# Uso: registro_final.sh <scratchpad> <dir_mision> <extraccion_paquete_410ae629>
S="$1"; F="$2"; X="$3"; R=/home/user/Trader-IA
bash "$X/herramientas/estado_repo.sh" "$R" "Estado FINAL del repositorio protegido (misión integral de cierre)"
echo "-- comparación con el estado inicial de ESTA misión (registro A2, líneas 2–14):"
diff <(sed -n '2,14p' "$F/registro/A2_git_congelados_entregas.txt") <(bash "$X/herramientas/estado_repo.sh" "$R" x | sed -n '2,14p') && echo "IDÉNTICO al inicio de la misión"
echo "-- congelados:"; bash "$X/herramientas/congelados.sh" "$R" "$S"; echo "rc congelados=$?"
echo "-- entregas previas (mismos archivos y comandos que A2):"
E=$S/decision_final_D1_D3_2026-10-22/entrega
diff <(sed -n '/^-- entregas previas:/,/^entregas v3r1/p' "$F/registro/A2_git_congelados_entregas.txt" | sed '1d;$d') \
     <( (cd "$E" && sha256sum *.zip *.sha256 *.txt); sha256sum "$S"/cierre_revision_D1_D3_2026-10-22/paquete/*.zip "$S"/cierre_D1_D2_R19_2026-10-22/paquete/*.zip "$S"/cierre_D1_D2_R19_2026-10-22/fase1/entrega/* ) \
  && echo "entregas previas (v3, v3r2, revisión, paquete 410ae629, v3r3 y sus verificaciones): IDÉNTICAS al inicio"
echo "-- árboles congelados de R19 (misión anterior):"; cat "$F/registro/B4_arboles_despues_R19.txt" | tail -4
echo "-- modificaciones en el repositorio protegido: $(git -C "$R" status --porcelain -uall | wc -l) (rastreados o no rastreados); ignorados (informativo): $(git -C "$R" status --porcelain --ignored | grep -c '^!!')"
echo "-- procesos residuales: postgres $(pgrep -c postgres || true) · quemadores/pytest/python de la misión $(pgrep -fc 'quemador|r19_experimento|robustez_guarda|pytest' || true)"
echo "-- enlaces de socket temporales /tmp/tia_r24_*: $(ls -d /tmp/tia_r24_* 2>/dev/null | wc -l)"
echo "-- cluster PostgreSQL del sistema: $(pg_lsclusters 2>/dev/null | tail -n +2 | tr -s ' ')"
echo "-- refs remotas y ramas: sin push ni ramas nuevas si 'refs' arriba es idéntico (una sola rama local y su remota en 72ffae5)"
