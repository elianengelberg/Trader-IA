#!/bin/bash
# Verificación de citas y números de línea de MATRIZ_METODOLOGICA.md (solo lectura de texto). Se ejecuta desde el scratchpad.
cd /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad
E3=experimentos/E3_seleccion_posicion_2026-10-19; PROT=$E3/ejecucion_E3/protocolo; E3R=experimentos/E3R_desbloqueo_2026-10-26
V3=$E3/PROTOCOLO_E3_v3_PROPUESTO.md; CI=$E3/CIERRE_E3.md; NO=$PROT/NOTAS_IMPLEMENTACION_v3.md; A1=$PROT/ADENDA_1_reutilizacion_de_tickers.md
A3=$PROT/ADENDA_3_reglas_conciliacion.md; AR=$E3R/ADENDA_R_auditoria_de_supervivencia_interna.md; CR=$E3R/CORRECCION_R1prima_alcance_por_clase.md
IR=reparacion_E3H1H2_2026-10-26/INFORME_REPARACION_E3H1H2.md
g(){ printf '%-9s ' "$1"; grep -n -F -m1 -- "$3" "$2" | cut -c1-150 || echo "(sin coincidencia)"; }
echo "== sha256 (16) de las fuentes"; for f in $V3 $CI $NO $A1 $A3 $AR $CR; do printf '%s  %s\n' "$(sha256sum $f | cut -c1-16)" "$(basename $f)"; done
echo "== v3"
g v3 $V3 "Si hay conflicto, prevalece este documento"; g v3 $V3 "requieren una adenda y tu autorización"; g v3 $V3 "- **Lista fija:**"; g v3 $V3 "BIDR, IDRT, BVND"
g v3 $V3 "**Tokens apalancados:**"; g v3 $V3 "todas las exclusiones o remociones que afectan"; g v3 $V3 "3. **Listado vigente:**"; g v3 $V3 "si vuelve a cotizar"
g v3 $V3 "4. **Renombres:**"; g v3 $V3 "5. **Par USDT removido"; g v3 $V3 "1 ejecución confirmatoria"; g v3 $V3 "Cualquier otra ejecución es exploratoria"
g v3 $V3 "no cambia ninguna clasificación"; g v3 $V3 "| E | Ambiguo"; g v3 $V3 "### 4.11"; g v3 $V3 "- **Inicio de H:**"; g v3 $V3 "- **INVÁLIDO** si más del 20 %"
g v3 $V3 "### 7.1 Supuestos"; g v3 $V3 "### 7.2 Cifras"; g v3 $V3 "**Cota conjunta:**"; g v3 $V3 "nunca** confirmación independiente"
printf 'BKRW en v3: '; grep -c BKRW $V3
echo "== CIERRE"; g CIERRE $CI "No se relajó la regla (iv)"; g CIERRE $CI "**E3 no continúa.**"; g CIERRE $CI "Haría falta una lista completa"; g CIERRE $CI "La última fecha efectiva archivada es el 2024-11-06"
echo "== NOTAS"; g NOTAS $NO "Si una nota contradijera la v3"; g NOTAS $NO "**N5.**"
echo "== ADENDA_3"; g A3 $A3 "**no cambia** categorías"; g A3 $A3 "5. **Fecha efectiva E** (N5):"; g A3 $A3 "la primera fecha del título"; g A3 $A3 "(a) **E corregida**"
g A3 $A3 "se usa la lectura corregida y se informa"; g A3 $A3 "**V-S3** (semilla"; g A3 $A3 "1. **Primera pasada:**"; g A3 $A3 "**Se revisan todos los casos de cada lista, sin seleccionar.**"; g A3 $A3 "Su resultado es el definitivo"
g A3 $A3 "# Adenda 3: reglas fijas"
echo "== ADENDA_1"; g A1 $A1 "1. **Renombre con cambio de símbolo**"; g A1 $A1 "3. **Si no hay anuncio**"
echo "== ADENDA_R"; g AR $AR "en Common Crawl no hay ninguno"; g AR $AR "228 dejan de tener archivos"; g AR $AR "**ninguna** quedó en la categoría D"; g AR $AR "las 4 en la categoría T"
g AR $AR "**R1 · Alcance"; g AR $AR "**Fundamento:**"; g AR $AR "- (ii′)"; g AR $AR "- (iv′)"; g AR $AR "- (iii) **no se aplica**"; g AR $AR "Al escribir esta adenda conozco"; g AR $AR "242 de 279"
g AR $AR "se recomienda autorizar **una**"
echo "== CORRECCION_R1prima"; g CR $CR "congelada **después** de calcular P0"; g CR $CR "casi duplica la información"; g CR $CR "sienta el precedente de corregir"; g CR $CR "El defecto es mío"
echo "== INFORME_REPARACION"; g IR $IR "toma la fecha del **título**, que es la de publicación"; g IR $IR "El código congelado no tiene mecanismo para agregarlos"; g IR $IR "Se revisaron todas las páginas de exclusión con fecha ≥ 2023-04-28"
g IR $IR "Una falla en alcance con E ≥ 2023-05-29 invalida A"; g IR $IR "Con una salida más sin evidencia en 2023"; g IR $IR "R2 queda abandonada"; g IR $IR "Se releyeron los **55 eventos**"
