# E4: revisión adversarial y preparación para congelar (2026-10-29)

**Carpeta:** `revision_adversarial_E4_2026-10-29/`. Las rutas son relativas a ella, salvo que se indique otra cosa.

**Quién revisó:** el mismo agente que escribió el v0. No es una revisión independiente.

**Verificación inicial:**
- El paquete v0 validó 39/39 contra `MANIFEST_EJECUTIVA.sha256`, sin archivos nuevos.
- Hashes del v0:
  - `PRERREGISTRO_E4.md`: `f28f336f…`
  - `nucleo.py`: `1d83a1e4…`
  - `evaluar.py`: `1e8e8429…`
  - `recolector.py`: `f0544f63…`
  - `guarda_rutas.py`: `c6a25efb…`
- Git: rama `claude/algo-trading-simulation-platform-ngf7xo`, `72ffae5`, sin cambios.
- Series reales intactas (`registro/aislamiento_y_entorno.txt`).

**Qué no se hizo:**
- No se descargó ningún dato de precios.
- No se congeló, ancló ni selló nada.
- No se creó ninguna credencial, rama ni servicio.
- No se usó el sellado de R1 y R2 que autorizaste «si hace falta»: E4 no lo necesita, porque su código no toca las series y la guarda las rechaza. Además, tu §4 pedía no sellar todavía.

## 1. Defectos que pueden invalidar E4

### Demostrados en el v0, con su evidencia

| # | Defecto | Evidencia | Qué cambiaría |
|---|---|---|---|
| D1 | **La prueba rechaza de más.** El t de Newey-West con 5 rezagos y el corte 1,96 da un α real de 0,028 con datos gaussianos iid y de 0,029–0,032 con colas pesadas y autocorrelación, contra 0,025 nominal | `e4_v1/registro/alfa_preciso.json` (100 000 simulaciones por caso) | Entre 13 % y 30 % más falsos positivos; un resultado al borde sería RESPALDADA indebidamente |
| D2 | **El evaluador no verifica el código congelado.** Solo compara el hash del prerregistro; el núcleo y las reglas podían cambiar después sin que se detectara | v0 `evaluar.py` líneas 51–53 | La clasificación podría alterarse sin rastro |
| D3 | **T0 y el horizonte son argumentos libres** (`--t0`, `--dias`): la ventana se podía elegir después de ver | v0 `evaluar.py` líneas 42–44 y 59; la prueba v0 corrió con 253 días | Selección retrospectiva de la ventana |
| D4 | **Los datos no quedan atados.** El registro guarda solo conteos, el evaluador no verifica los ZIP y anclar el `REGISTRO` no fija su contenido | v0 `recolector.py` líneas 99–109; v0 `evaluar.py` líneas 74–78 | Datos alterables después de recolectar |
| D5 | **Un error de red se registraba como «ausente».** Un fallo pasajero parecía un par que no operó y cambiaba el universo y las salidas | v0 `recolector.py` línea 93 (`except Exception` → ausente) | Sesgo silencioso en universo y salidas |
| D6 | **Estables sin excluir.** BFUSD, RLUSD, USDE y XUSD (y RWUSD y USDEB, sin identificar) tienen velas en octubre de 2026 y no están en la lista fija. Con su volumen entrarían al top 100. Tampoco se excluían WBTC y WBETH, que duplican a BTC y ETH | `fuente/simbolos_spot_daily_klines.json` y el listado de octubre: solo nombres y fechas, sin precios | Diluye el IC; una lista fija no cubre estables nuevas |
| D7 | **Un cambio de formato mata la evaluación.** Un encabezado provocaba `SystemExit` y, con D-7, NO EVALUABLE. No se comprobaba que la vela fuera del día del archivo. Spot usa marcas en µs desde 2025-01-01 | v0 `evaluar.py` líneas 30–37; README de binance-public-data | E4 perdido por formato al final del período |
| D8 | **La clase REFUTADA dice «económicamente relevante» con un umbral (IC 0,01) que no se deriva de nada.** El IC de equilibrio económico depende de la dispersión transversal de los retornos y de la rotación, y ninguna de las dos está medida: no se puede fijar sin mirar datos, y no se inventó | v0 prerregistro §6 frente a §7 | Lectura engañosa de un resultado nulo |
| D9 | **Faltan dos criterios de invalidación de P19:** «concentrado en nombres ilíquidos» y «explicado por pocos días extremos» | P19 (`PROPUESTAS_TECNICAS.md`, líneas 308–327) frente al v0 §6–§8 | Un RESPALDADA frágil pasaría como sólido |
| D10 | **La potencia declarada (0,41–0,97) supone un desvío del IC ≤ 0,20 que no está medido ni es una cota.** Con 0,25, la potencia para IC 0,02 en 365 días es 0,27–0,32 | `e4_v1/registro/potencia_disenos.txt` | Alta probabilidad de INSUFICIENTE después de un año |

### Riesgo de diseño, no defecto: el retraso de un día del v0

El v0 mide la reversión de rezago 2: se salta el día t entero. P19 admite datos diarios u horarios, así que esto no contradice a P19. Pero es otro efecto, presumiblemente más débil [Hip]. Un INSUFICIENTE no diría nada sobre la reversión de rezago 1, que es la hipótesis económica de P19. Es tu Decisión 1.

## 2. Correcciones imprescindibles (aplicadas en `e4_v1/`; el v0 quedó intacto)

| Defecto | Corrección | Prueba |
|---|---|---|
| D1 | Límites calibrados por simulación determinista para el t de Newey-West, con los n observados. α con gaussianas iid: 0,0256 | `alfa_preciso.json`; U6 |
| D2 | El evaluador verifica **todas** las líneas de `CONGELACION` antes de importar el núcleo, y rechaza cualquier `.py` sin congelar | U8 y punta a punta |
| D3 | T0 se lee de `INICIO_E4.json` (sha anclado, T0 = día siguiente al bloque) y las miradas son constantes del código. Fuera del modo sintético no se aceptan otras | Punta a punta: inicio no anclado y T0 corrido, rechazados |
| D4 | `MANIFIESTO.sha256` por día, encadenado en `REGISTRO.jsonl`. El evaluador verifica cada ZIP y rechaza los que no figuran en el manifiesto | Punta a punta: ZIP alterado y ZIP intruso, rechazados |
| D5 | Un archivo que no aparece en el listado S3 no se pide. Un error de red, tras 3 reintentos, deja el día con `errores > 0` y el recolector sale con código 2; el evaluador rechaza ese día hasta que se vuelve a recolectar | Punta a punta: código 2, día rechazado y luego aceptado |
| D6 | Filtro **objetivo** de paridad (30 cierres en [0,97; 1,03]) más los envoltorios WBTC, WBETH y BETH | U3 |
| D7 | Lector tolerante (encabezado, ms/µs) que exige la vela del día correcto. Un ilegible es un par-día faltante; si superan el 1 %, se aborta sin calcular. `--solo-validar` revisa el formato en cada lote | U2 (9 casos) y punta a punta |
| D8 | La clase pasa a llamarse REFUTADA_IC_MINIMO: umbral de información por convención. La relevancia económica la decide solo el §8 | Prerregistro v1 §6 |
| D9 | Tres señales de fragilidad (días extremos, 50 más líquidos, componente de mercado) que solo pueden rebajar RESPALDADA a RESPALDADA_NO_ROBUSTA, sin gastar α | Prerregistro v1 §7 |
| D10 | Dos miradas (365 y 730) con gasto de α de Lan-DeMets tipo O'Brien-Fleming. La potencia total es casi la de una mirada única a 730, sin perder la de cortar al año. Se declara condicionada a supuestos no medidos | U5 (2,963 y 1,969, los publicados), U6, U7 |

**Corrección menor, también aplicada:** el Spearman usaba orden arbitrario en los empates; ahora usa rangos promedio (U1).

**Resultado de las pruebas nuevas** (en `e4_v1/registro/`; solo se probó lo que cambió):
- **Unitarias:** U1–U8, todas OK.
- **Punta a punta**, en memoria con datos sintéticos de fechas ficticias, OK:
  - 11 551 ZIP recolectados y la cadena del registro íntegra;
  - 12 manipulaciones rechazadas antes de calcular;
  - la mirada 1 da CONTINUAR sin estadísticos;
  - la mirada 2 da RESPALDADA_INFORMACION con el efecto plantado (t = 3,92, límite 2,12 con n chico);
  - ninguna mirada se puede repetir.

### Por qué dos miradas (§3 de tu orden)

- Con el mismo número de días, una sola mirada al final es la prueba más potente. Mirar en el medio **no** aumenta la potencia.
- La potencia solo sube con más información. Aquí no se sabe cuánta hace falta, porque el desvío del IC no está medido.
- Dos miradas fijas en el calendario, con gasto de α prefijado, resuelven las dos cosas:
  - el α total queda en 0,025 por cola;
  - la potencia final es casi la de 730 días (por ejemplo, con sd 0,20 e IC 0,02: 0,76, contra 0,46 de una mirada a 365);
  - si el efecto es grande, se corta al año.
- **Cómo se cierra la puerta a mirar repetidamente:**
  - las fechas son fijas;
  - la mirada intermedia no muestra números;
  - el registro impide repetir;
  - todo queda sellado.
- **La alternativa honesta es una mirada única a 365 con límite 2,006.** Es más rápida, pero tiene menos potencia si el desvío del IC es alto.

## 3. Riesgos aceptables (no requieren más auditoría)

| Riesgo | Por qué se acepta | Mitigación ya incluida |
|---|---|---|
| α residual con autocorrelación y colas pesadas: 0,027 con AR 0,1 y 0,029 con AR 0,2, después de calibrar | Es chico, está medido y declarado | Se informa la autocorrelación del IC como diagnóstico |
| Salidas (deslistados, suspensiones): rinden 0 en la cartera y salen del IC | En el top 100 son pocas; la regla es fija y se cuenta | `salidas_totales` en el resultado |
| Renombres: el símbolo viejo sale y el nuevo entra a los 30 días | Pierde a lo sumo 30 días de un par; no inventa retornos | Regla declarada en §3 |
| Binance regenera archivos (velas de 2017 subidas en 2023) o retira datos (términos §5.3) | Vale nuestra copia con su manifiesto anclado | Recolección mensual y almacenamiento persistente |
| Componente beta × mercado | No invalida la información; cambia su lectura | Señal (c) de fragilidad |
| Comisión de 7,5 bps con descuento BNB; sin impacto de mercado; costos del benchmark sin cargar | Es secundario y conservador para la estrategia | Sensibilidades 7,5+10, 7,5+20 y 10+5 |
| Alguien que mire precios por fuera, por ejemplo en un sitio web | No sirve para calcular el IC del universo ni para cambiar un protocolo ya sellado | Congelación, sello y testigo |
| La revisión la hizo el mismo agente | Declarado | Paquete de revisión externa del ciclo anterior, con A9 y A10 actualizables al v1 |

## 4. Prerregistro corregido (no congelado)

`e4_v1/PRERREGISTRO_E4_v1.md`, con el código en `e4_v1/codigo/` (los hashes figuran en `MANIFEST_REVISION_E4.sha256`).

- Las únicas opciones abiertas están marcadas [DECISIÓN 1] y [DECISIÓN 2].
- Cambiar cualquiera de las dos es una constante del código más un párrafo.

## 5. Decisiones que tenés que tomar

1. **Aprobar el v1** con:
   - **Decisión 1:** retraso de 1 h (recomendado) o de 1 día;
   - **Decisión 2:** dos miradas, 365 y 730 (recomendado), o una sola a 365.
2. **Almacenamiento persistente y lugar de la recolección mensual.** Hoy no hay ninguna carpeta tuya disponible por Remote Control.
   - **A (recomendada):** una carpeta de tu computadora.
     - Tiene que ser la raíz de un repositorio git, por ejemplo `~/e4-datos`, con `git init` y `datos/` en `.gitignore`.
     - Se habilita en Claude → Settings → Claude Code → Remote Control.
   - **B:** un bucket tuyo con una credencial guardada como secreto del entorno.
   - **Tamaño:** a lo sumo unos 1,5 MB por día de contenido (770 pares USDT × ≈ 2 KB por par-día), sin contar la sobrecarga de archivos chicos. Conviene reservar unos 5 GB para 2 años.
3. **Ancla y testigo:**
   - autorizar la instalación de `opentimestamps-client==0.7.2` (wheel sha `84e604d7…`; la 0.8.0 salió hace 2 días y no la recomiendo) y la red a sus calendarios, que respondieron 200 hoy;
   - decir **a quién** se le manda el hash de la congelación antes de T0. Recomendado: el revisor externo.
4. **Licencia:** confirmar que E4 es investigación personal no comercial (CC BY-NC-SA 4.0). Los términos prohíben usar estos datos para trading en vivo.

## 6. Siguiente paso concreto: empezar a recolectar datos prospectivos

Nada de esto se ejecutó. Se corre recién cuando respondas las decisiones 1–4.

```bash
S=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad
E=$S/revision_adversarial_E4_2026-10-29/e4_v1
PY=$S/integracion_controlada_2026-10-25/venv/bin/python                    # Python 3.11.17, numpy 2.4.6
TSV=$S/ejecutiva_post_E3_2026-10-29/zona_aislada/PROTEGIDOS.tsv
DATOS=<carpeta_persistente>/e4_datos                                       # decisión 2

# 1) Congelar (después de tu aprobación del v1)
cd $E && sha256sum PRERREGISTRO_E4_v1.md codigo/*.py > CONGELACION_E4_v1.txt && sha256sum CONGELACION_E4_v1.txt

# 2) Cliente de sellado fijado, en un venv aparte (decisión 3)
python3 -m venv $E/../venv_ots
$E/../venv_ots/bin/pip download --no-deps --only-binary=:all: -d $E/../ruedas_ots opentimestamps-client==0.7.2 opentimestamps==0.4.5
sha256sum $E/../ruedas_ots/*.whl     # tienen que dar 84e604d7… (cliente) y a4912b3b… (biblioteca); si no, ABORTAR
$E/../venv_ots/bin/pip install $E/../ruedas_ots/*.whl                       # las dependencias quedan registradas con pip freeze

# 3) Sello y testigo
$E/../venv_ots/bin/ots stamp $E/CONGELACION_E4_v1.txt                       # crea CONGELACION_E4_v1.txt.ots
#    mandar al testigo el sha256 de CONGELACION_E4_v1.txt (paso 1) antes de T0

# 4) Unas horas después: confirmación en Bitcoin y T0
$E/../venv_ots/bin/ots upgrade $E/CONGELACION_E4_v1.txt.ots && $E/../venv_ots/bin/ots info $E/CONGELACION_E4_v1.txt.ots
#    la altura del bloque sale de ots info y su hora, de un nodo o de dos exploradores independientes
#    T0 = día UTC siguiente; escribir INICIO_E4.json {"congelacion_sha256", "ancla": {"tipo": "opentimestamps", "bloque_utc", "altura"}, "t0"}

# 5) Primera recolección: los 31 días previos a T0, en el almacenamiento persistente
$PY -I -B $E/codigo/recolector.py --fuente https://data.binance.vision --desde <T0-31> --hasta <T0-1> --destino $DATOS --protegidos $TSV
cp $DATOS/REGISTRO.jsonl $DATOS/REGISTRO_<fecha>.jsonl && $E/../venv_ots/bin/ots stamp $DATOS/REGISTRO_<fecha>.jsonl

# 6) Después, una vez por mes (programable como tarea): el mes anterior completo, la validación de formato (solo cuenta) y el sello
$PY -I -B $E/codigo/recolector.py --fuente https://data.binance.vision --desde <AAAA-MM-01> --hasta <AAAA-MM-último> --destino $DATOS --protegidos $TSV
$PY -I -B $E/codigo/evaluar.py --solo-validar --mirada 1 --datos $DATOS --congelacion $E/CONGELACION_E4_v1.txt \
     --inicio $E/INICIO_E4.json --inicio-sha256 <sha anclado> --salida $DATOS/no_se_usa --protegidos $TSV
```

**Dónde se corre:**
- En este contenedor, el recolector va dentro de `zona_aislada/ejecutar_aislado.sh`.
- En tu computadora no hace falta, porque las series de E3 no están ahí; la guarda sigue activa igual.

**Miradas:** T0 + 368 y T0 + 733, con `evaluar.py --mirada 1` y `--mirada 2`. Cada una se corre una sola vez.
