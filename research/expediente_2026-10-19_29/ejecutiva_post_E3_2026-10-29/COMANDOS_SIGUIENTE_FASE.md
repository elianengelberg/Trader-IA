# Comandos exactos de la fase siguiente (NINGUNO fue ejecutado: todos requieren tu autorización)

Variables comunes:

```bash
S=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad
N=$S/ejecutiva_post_E3_2026-10-29
E=$N/e4_xsrev_prospectivo
PY=$S/integracion_controlada_2026-10-25/venv/bin/python   # numpy 2.4.6
ZONA=$N/zona_aislada/ejecutar_aislado.sh                   # tapa las 18 rutas protegidas antes de ejecutar
```

**Aviso sobre el almacenamiento.**
- Este contenedor es efímero y su disco de sesión está casi lleno (394 MB libres).
- Los datos de E4 (≈ 90 MB/año) y su registro tienen que vivir en un lugar **persistente** que elijas vos: tu computadora vía Remote Control, o un almacenamiento propio.
- Binance Vision conserva los archivos diarios, así que la recolección puede hacerse por lotes (por ejemplo, mensual) sin perder el carácter prospectivo. Ese carácter lo da la fecha de congelación y anclaje del prerregistro, no la fecha de descarga.

## 0. Sellado de las copias reales (opcional, recomendado)

Está en `AISLAMIENTO_COPIAS_REALES.md` §3, con la verificación de hashes antes y después y la reversión.

## 1. Ancla externa (una vez)

Detalle en `ANCLA_EXTERNA_R2.md`.

```bash
# 1a (vos, en GitHub): crear la rama `registros` desde 72ffae5 y su ruleset (sin push forzado, sin borrado, historia lineal, solo vos)
# 1b (agente, con tu autorización): cliente OpenTimestamps fijado por versión, en un venv aparte
python3 -m venv $N/venv_ots && $N/venv_ots/bin/pip install 'opentimestamps-client==<VERSION>'   # <VERSION>: a fijar consultando PyPI al autorizar (no se consultó); registrar el sha256 de la rueda instalada
```

## 2. Revisión y congelación del prerregistro de E4

Primero lo revisás vos. Después:

```bash
cd $E && { sha256sum PRERREGISTRO_E4.md; sha256sum codigo/*.py; } > CONGELACION_E4.txt && sha256sum CONGELACION_E4.txt
$N/venv_ots/bin/ots stamp CONGELACION_E4.txt              # crea CONGELACION_E4.txt.ots (red a los calendarios)
# push a `registros` de anclas/E4/ con CONGELACION_E4.txt y su .ots: un commit (requiere tu autorización de push)
# T0 = primer día UTC completo posterior a la confirmación del push
```

## 3. Recolección: mensual, por lotes, en almacenamiento persistente

Ejemplo para el mes M; con `D` y `T0` reales:

```bash
DATOS=<carpeta_persistente_nueva>/e4_datos               # la guarda rechaza cualquier ruta protegida
for D in $(seq 0 30 | xargs -I{} date -u -d "<primer_dia_del_mes> +{} days" +%F); do
  $ZONA $PY -I -B $E/codigo/recolector.py --fuente https://data.binance.vision --dia $D \
       --destino $DATOS --protegidos $N/zona_aislada/PROTEGIDOS.tsv
done
sha256sum $DATOS/REGISTRO.jsonl                          # se ancla en `registros` (fija qué datos existían antes de evaluar)
```

El recolector:
- **no abre** los ZIP;
- verifica cada `.CHECKSUM` oficial;
- no reescribe nada ya guardado;
- registra cada corrida en una cadena de hashes.

## 4. Evaluación única

No antes de T0 + 368 días:

```bash
$ZONA $PY -I -B $E/codigo/evaluar.py --datos $DATOS --t0 <T0> --dias 365 \
     --prerregistro $E/PRERREGISTRO_E4.md --congelacion $E/CONGELACION_E4.txt \
     --salida <carpeta_nueva_resultado> --protegidos $N/zona_aislada/PROTEGIDOS.tsv
```

El evaluador se niega a correr:
- antes de tiempo;
- dos veces;
- con un prerregistro alterado;
- en modo real sobre datos sintéticos.

Todo esto está probado en `e4_xsrev_prospectivo/registro/prueba_punta_a_punta.json`.

## 5. Lo que se puede correr ya, sin autorización y sin datos reales

Son pruebas con datos sintéticos. Se repiten igual:

```bash
cd $E/codigo && $PY -I -B pruebas_sinteticas.py /ruta/salida.json
$PY -I -B prueba_punta_a_punta.py /ruta/vacia /ruta/PROTEGIDOS.tsv /ruta/salida.json
/usr/bin/python3 -I -B potencia_E4.py
```

**Límite de espacio:** la prueba de punta a punta usa ≈ 120 MB transitorios y los borra al terminar.
