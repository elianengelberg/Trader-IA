# Datos históricos que faltan para evaluar H-CARRY

**Estado (2026-10-16, 19:54 UTC): no hay ningún dato histórico.**
- Desde este entorno, `data.binance.vision` responde `CONNECT tunnel failed, response 403`.
- En Google Drive no hay ninguna copia reciente.
- La evaluación prerregistrada (`PRERREGISTRO_VALIDACION_HISTORICA.md`, hash `90642cd1…`) **no se ejecutó**. No se ejecutará hasta que estos archivos lleguen y pasen todos los controles de calidad (C1–C6).

No se rellena ningún hueco con datos sintéticos ni de otra fuente. Si falta un mes, la conclusión es EVIDENCIA INSUFICIENTE y el informe dirá exactamente qué falta.

## 1. Especificación

| Requisito | Valor exacto |
|---|---|
| Fuente | `https://data.binance.vision/data/…`: archivos públicos **oficiales** de Binance, **mensuales** |
| Activo | **BTCUSDT** |
| Pata larga | **Spot** BTCUSDT de binance.com (no Binance.US) |
| Pata corta | Contrato **perpetuo USDⓈ-M BTCUSDT** (`futures/um`). **No** COIN-M (`futures/cm`, BTCUSD_PERP) ni trimestrales (BTCUSDT_AAMMDD) |
| Intervalo de las velas | **1 h** (`1h`) |
| Funding | Historial de liquidaciones del perpetuo USDⓈ-M BTCUSDT, cada 8 h (00:00, 08:00 y 16:00 UTC) |
| Período | **2019-10 a 2026-05, ambos incluidos: 80 meses** |
| Excluido | **2026-06 en adelante.** El período reservado (2026-06-01 → 2026-10-13) lo rechaza el código. No lo incluyas. |
| Integridad | Cada `.zip` junto a su `.CHECKSUM` oficial (`<sha256>  <nombre>.zip`), **sin modificar** |
| Tamaño aproximado | Unos 800 archivos; estimo menos de 20 MB en total. No pude verificarlo. |

**Por qué empieza en 2019-10:** el perpetuo BTCUSDT de Binance empezó a cotizar en septiembre de 2019. Desde aquí no puedo comprobar desde qué mes publica archivos cada serie. Si alguna no tiene archivos de los primeros meses (404), el prerregistro ya lo prevé: el análisis empieza en el **primer mes común** de las cuatro series obligatorias. Pero **después** de ese mes no puede faltar ninguno (filtro C2).

**Divisiones prerregistradas** (no cambian):
- desarrollo: 2019-10 → 2022-12;
- validación: 2023-01 → 2024-01;
- test: 2024-02 → 2026-05.

## 2. Series y archivos

| Serie | ¿Obligatoria? | Ruta bajo `data/` (AAAA-MM = mes) | Archivos | Formato del CSV interno | Para qué se usa |
|---|---|---|---|---|---|
| Spot, velas 1 h | **Sí** | `spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-AAAA-MM.zip` | 80 zip + 80 `.CHECKSUM` | 12 columnas, sin cabecera. Marcas en ms; en µs desde 2025-01 | Precio de la pata spot (S) |
| Perpetuo, velas 1 h | **Sí** | `futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-AAAA-MM.zip` | 80 + 80 | 12 columnas, con cabecera, ms | Precio de la pata corta (F) y base F/S |
| Precio mark, 1 h | **Sí** | `futures/um/monthly/markPriceKlines/BTCUSDT/1h/BTCUSDT-1h-AAAA-MM.zip` | 80 + 80 | Igual que el perpetuo | Margen, precio de liquidación, coherencia M/F |
| Funding | **Sí** | `futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-AAAA-MM.zip` | 80 + 80 | `calc_time, funding_interval_hours, last_funding_rate`, con cabecera | Cobros y pagos de funding (la fuente del carry) |
| Índice de prima, 1 h | Opcional | `futures/um/monthly/premiumIndexKlines/BTCUSDT/1h/BTCUSDT-1h-AAAA-MM.zip` | 80 + 80 | Igual que el perpetuo | Control adicional de coherencia del funding. Ninguna de las dos políticas lo usa |

Las 12 columnas de las velas son: `open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore`.

**Lista exacta de URLs:**
- `ARCHIVOS_REQUERIDOS.txt`: 640 URLs (4 series × 80 meses × zip + `.CHECKSUM`).
- `ARCHIVOS_OPCIONALES.txt`: 160 URLs (índice de prima).

Primera y última de cada serie:
```
https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2019-10.zip            … 2026-05.zip
https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2019-10.zip      … 2026-05.zip
https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/1h/BTCUSDT-1h-2019-10.zip … 2026-05.zip
https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2019-10.zip … 2026-05.zip
https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1h/BTCUSDT-1h-2019-10.zip … 2026-05.zip
```

**Volumen esperado con la ventana completa:**
- 58 440 velas horarias por serie: 720, 744, 672 o 696 por mes;
- unos 7 305 eventos de funding (3 por día).

## 3. Reglas para que la copia sea aceptable

1. **No descomprimas, renombres ni recomprimas** los `.zip` internos. El SHA-256 debe coincidir con el `.CHECKSUM` oficial.
2. **Conservá cada `.CHECKSUM` junto a su zip** y la estructura de carpetas oficial desde `data/` (por ejemplo `data/spot/monthly/klines/BTCUSDT/1h/…`). `importar` reconoce cada serie por su ruta.
3. **No mezcles** otras fuentes, otros símbolos ni otros intervalos, ni conviertas a CSV.
4. Si un archivo da **404**, no lo sustituyas por archivos diarios ni por otra fuente. Mandame el registro de la descarga, que deja anotados los ausentes.
5. Si podés, **comprobá al azar 3 o 4 hashes** contra la web. Así se descarta una copia manipulada a la vez en datos y checksums.

## 4. Cómo conseguirlos fuera de este entorno

**Opción A: con el código del proyecto** (Python ≥ 3.11, sin dependencias externas). Verifica cada checksum y anota los 404 en el manifiesto:
```
git clone -b claude/algo-trading-simulation-platform-ngf7xo https://github.com/elianengelberg/Trader-IA.git
cd Trader-IA/research/hcarry_next
PYTHONPATH=src python3 -m hcarry descargar --destino binance_vision --desde 2019-10 --hasta 2026-06
```
`--hasta` es exclusivo: baja de 2019-10 a 2026-05.

**Opción B: solo con `wget`**, desde `research/hcarry_next/experimentos/historico/`:
```
cat ARCHIVOS_REQUERIDOS.txt ARCHIVOS_OPCIONALES.txt | wget -x -nH -i - -o descarga.log
find data -name '*.CHECKSUM' -execdir sha256sum -c {} \; | grep -c ': OK'    # macOS: shasum -a 256 -c
```
- Si todo está publicado, debería dar 400 líneas `OK` (320 sin las opcionales).
- Los 404 quedan en `descarga.log`.

**Cómo hacérmelos llegar** (por orden de fiabilidad):
1. **Habilitar `data.binance.vision`** en la configuración de red del entorno (*Network access → Allowed domains*). Lo descargo y verifico yo, contra el emisor. Es la mejor opción.
2. **Una rama del repositorio**:
   - subí la carpeta (`binance_vision/` o `data/`), con `descarga.log` si usaste la opción B, a una rama nueva, por ejemplo `datos/binance-vision-btcusdt`;
   - desde aquí accedo a GitHub y vuelvo a verificar todo con `importar`;
   - son datos públicos de Binance, pero si el repositorio es público quedarán públicos.
3. **Google Drive o adjunto:** sirve solo si el archivo llega entero a este entorno. La herramienta de Drive que tengo devuelve el contenido en base64 dentro de la conversación, así que no es fiable para un paquete de varios MB. Prefiero las opciones 1 o 2.

## 5. Qué hago cuando lleguen (sin cambiar nada del prerregistro)

1. `importar` (opción 2) o `descargar` (opción 1): SHA-256 de cada archivo frente a su `.CHECKSUM` oficial, y procedencia `historico_oficial` sin marca sintética.
2. `calidad`, con los filtros C1–C6 fijados de antemano:
   - checksums;
   - cobertura sin meses ausentes desde el primer mes común;
   - ≤ 0,5 % de horas rellenadas y rachas ≤ 24 h;
   - funding: intervalos de 8 h alineados a la hora (±60 s), sin huecos, desórdenes ni tasas imposibles (|tasa| > 5 %);
   - coherencia entre spot, perpetuo y mark (mediana de |F/S − 1| ≤ 0,2 %, p99 de |M/F − 1| ≤ 1 %, OHLC válido);
   - nada del período reservado.
3. **Si algún control falla:** no se simula nada. Informo EVIDENCIA INSUFICIENTE con la lista exacta de lo que falla o falta.
4. **Si todos pasan:** `python -m hcarry historico` corre el diagnóstico (solo en desarrollo), el desarrollo y la validación. Después prerregistra el test con el hash de los datos y lo ejecuta **una vez**, con costes base y las 8 sensibilidades. La conclusión sale de los criterios escritos y se informa sea cual sea: ventaja respaldada, hipótesis no respaldada o evidencia insuficiente.
