#!/usr/bin/env bash
# Prueba adversarial de la etapa 13 (paquete intacto). Cada escenario usa una copia NUEVA de la extracción del paquete
# y borra al terminar todo lo que creó (copia, temporales y el archivo movido fuera de la copia).
# Uso: probar_etapa13.sh <paquete extraído (referencia, no se modifica)> <script de la etapa 13> <dir de trabajo>
set -u
REF=$1; ETAPA=$2; D=$3
correr() {  # nombre, esperado (DETECTA/NO_DETECTA), comando que altera la copia
  local nombre=$1 esperado=$2 cmd=$3 c="$D/caso_$1"
  rm -rf "$c"; cp -a "$REF" "$c"; chmod -R u+w "$c"
  (cd "$c" && eval "$cmd")
  local prev evid salida r obtenido
  prev=$(mktemp -d -p "$D"); evid=$(mktemp -d -p "$D")
  salida=$(cd "$c" && PREV="$prev" EVID="$evid" bash -c "set -u; $(cat "$ETAPA"); echo INTACTO=\$INTACTO" 2>&1)
  r=$(echo "$salida" | grep -o 'INTACTO=[01]' | tail -1)
  [ "$r" = "INTACTO=1" ] && obtenido=DETECTA || obtenido=NO_DETECTA
  printf '%-36s esperado %-10s obtenido %-10s %s\n' "$nombre" "$esperado" "$obtenido" \
    "$([ $obtenido = $esperado ] && echo coincide || echo '<< DIFERENCIA')"
  rm -rf "$c" "$prev" "$evid" "$D/uso_unico_fuera.py"
}
correr sin_cambios NO_DETECTA ':'
correr byte_en_uso_unico DETECTA 'printf " " >> codigo/verificacion/uso_unico.py'
correr pyc_nuevo DETECTA 'mkdir -p codigo/verificacion/__pycache__ && echo x > codigo/verificacion/__pycache__/u.pyc'
correr archivo_borrado DETECTA 'rm pruebas/conftest.py'
correr archivo_renombrado DETECTA 'mv README.md LEEME.md'
correr oculto_nuevo DETECTA 'mkdir -p .pytest_cache && echo x > .pytest_cache/v'
correr enlace_simbolico_nuevo DETECTA 'ln -s uso_unico.py codigo/verificacion/enlace.py'
correr directorio_vacio_nuevo DETECTA 'mkdir -p codigo/verificacion/__pycache__'
correr archivo_reemplazado_por_enlace DETECTA 'mv codigo/verificacion/uso_unico.py ../uso_unico_fuera.py && ln -s "$PWD/../uso_unico_fuera.py" codigo/verificacion/uso_unico.py'
correr permisos_cambiados NO_DETECTA 'chmod +x README.md'
correr nuevo_en_evidencia NO_DETECTA 'echo x > evidencia/agregado.txt'
correr reescritura_coherente_del_manifiesto NO_DETECTA 'printf " " >> codigo/verificacion/uso_unico.py && h=$(sha256sum codigo/verificacion/uso_unico.py | cut -c1-64) && sed -i "s#^[0-9a-f]*  codigo/verificacion/uso_unico.py\$#$h  codigo/verificacion/uso_unico.py#" SHA256SUMS.txt'
