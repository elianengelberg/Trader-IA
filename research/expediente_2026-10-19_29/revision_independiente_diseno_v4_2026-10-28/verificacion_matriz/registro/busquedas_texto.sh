#!/bin/bash
# Búsquedas de texto sobre las fuentes (solo lectura). Desde el scratchpad.
cd /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad
E3=experimentos/E3_seleccion_posicion_2026-10-19; PROT=$E3/ejecucion_E3/protocolo; E3R=experimentos/E3R_desbloqueo_2026-10-26
PY=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/venv/bin/python
echo '## 1. reglas de precedencia/prevalencia en PROT (md y txt)'
(cd $PROT && grep -n -i -E "preceden|prevalec|jerarqu|prioridad|rige|rigen|si hay conflicto|contradic" *.md *.txt | cut -c1-200)
echo '## 2. términos de reintento / ejecución única en v3, protocolo, Adenda R y plan'
grep -n -i -E "reintent|una sola ejecuci|ejecuci[oó]n [uú]nica|Sin repeticiones|una\*\* ejecuci" $E3/PROTOCOLO_E3_v3_PROPUESTO.md $PROT/*.md $E3R/ADENDA_R_auditoria_de_supervivencia_interna.md $E3R/PLAN_EJECUCION_UNICA_E3R.md | cut -c1-230
echo '## 3. CIERRE §4 remite al §8 del informe de ejecución: opciones y recomendación'
sed -n 225,237p $E3/ejecucion_E3/INFORME_EJECUCION_E3.md | cut -c1-330
echo '## 4. PLAN_EJECUCION_UNICA_E3R: recomendación B y observación sobre BKRW'
grep -n -E "Por qué recomiendo B|Observación sin cambios|BKRW es un estable" $E3R/PLAN_EJECUCION_UNICA_E3R.md | cut -c1-300
echo '## 5. Informe de reparación: R2 abandonada, C6 (solo ventana A), BKRW descartado'
grep -n -E "R2 queda abandonada|C6 · Solo la ventana A|1 descartado" reparacion_E3H1H2_2026-10-26/INFORME_REPARACION_E3H1H2.md | cut -c1-260
echo '## 6. Remociones archivadas del 2022-11-28 (GTO, BTCST, SRM, TRIBE) y KEY 2023-02-10 en el texto archivado'
cd $E3/ejecucion_E3 && $PY -B -I - <<'PYEOF'
import json, re
from pathlib import Path
for f in sorted(Path("datos_anuncios/commoncrawl/paginas").glob("url_https___www.binance.com_en_support_announcement_notice-of-removal-*.json")):
    t=json.load(open(f)).get("texto","")
    m=re.search(r"TRIBE\s*/\s*USDT",t)
    if m and "2022-11-28" in t:
        i=m.start(); print(f.name[:80]); print("  ", t[max(0,i-330):i+40].replace("\n"," ")); break
for f in Path("datos_anuncios/commoncrawl/paginas").glob("*.json"):
    t=json.load(open(f)).get("texto","")
    m=re.search(r"\bKEY\s*/\s*USDT",t)
    if m and "2023-02-10" in t:
        i=m.start(); print(f.name[:80]); print("  ", t[max(0,i-170):i+60].replace("\n"," ")); break
PYEOF
