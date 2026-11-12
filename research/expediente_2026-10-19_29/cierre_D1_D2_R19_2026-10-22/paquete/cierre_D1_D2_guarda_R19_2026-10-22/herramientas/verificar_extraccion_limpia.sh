#!/usr/bin/env bash
# Verifica una entrega desde una extracción limpia y corre su reproducir.sh con un entorno mínimo (solo variables de red).
# Uso: verificar_extraccion_limpia.sh <dir_entrega> <nombre_sin_.zip> <dir_nuevo> <modo> <código E1> <registro_salida>
set -uo pipefail
E="$1"; N="$2"; D="$3"; MODO="$4"; E1="$5"; OUT="$6"
[[ -e "$D" ]] && { echo "$D ya existe"; exit 1; }
mkdir -p "$D/extraido" "$D/home"
{
echo "== $(date -u +%FT%TZ) · verificación de $N desde una extracción limpia"
(cd "$E" && sha256sum -c "$N.zip.sha256")
echo "-- extracción en directorio vacío ($(ls -A "$D/extraido" | wc -l) entradas antes)"
unzip -q "$E/$N.zip" -d "$D/extraido"; echo "extraídas: $(find "$D/extraido/$N" -type f | wc -l)"
(cd "$D/extraido/$N" && sha256sum -c --quiet SHA256SUMS && echo "SHA256SUMS: $(wc -l < SHA256SUMS) de $(wc -l < SHA256SUMS) verifican")
diff <(cd "$D/extraido/$N" && find . -type f ! -name SHA256SUMS | sed 's#^\./##' | LC_ALL=C sort) <(awk '{print $2}' "$D/extraido/$N/SHA256SUMS" | LC_ALL=C sort) && echo "sin archivos de más ni de menos"
VARS=$(env | grep -E '^(HTTPS?_PROXY|https?_proxy|NO_PROXY|no_proxy|PIP_CONFIG_FILE|PIP_CERT|SSL_CERT_FILE|REQUESTS_CA_BUNDLE)=' | sed 's/=.*//' | tr '\n' ' ')
echo "-- variables pasadas a reproducir.sh (entorno mínimo; solo red): $VARS"
echo "-- carga al inicio: $(cat /proc/loadavg)"
echo "-- reproducir.sh $MODO, ejecutado DESDE LA EXTRACCIÓN ($D/extraido/$N), trabajo en $D/trabajo, con env -i (PATH, HOME nuevo, LANG y solo variables de red)"
ARGS=(); for v in $VARS; do ARGS+=("$v=${!v}"); done
env -i PATH=/usr/bin:/bin HOME="$D/home" LANG=C.UTF-8 "${ARGS[@]}" bash "$D/extraido/$N/reproducir.sh" /home/user/Trader-IA "$D/trabajo" "$MODO" "$E1" 2>&1
echo "rc reproducir.sh = $? · fin $(date -u +%FT%TZ) · carga al final: $(cat /proc/loadavg)"
} > "$OUT" 2>&1
