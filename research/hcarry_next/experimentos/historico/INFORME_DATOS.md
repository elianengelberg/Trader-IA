# Informe de datos: BTCUSDT histórico oficial (2026-10-16)

**Categoría: HISTÓRICO VERIFICADO.** Son datos oficiales de data.binance.vision. Cada archivo se comprobó contra su `.CHECKSUM` oficial.

## 1. Acceso
Probado el 2026-10-16 a las 20:32 UTC, después de que el usuario habilitara la red:
- **DNS:** lo resuelve el proxy del entorno; no hay resolución local.
- **Conexión:** CONNECT `data.binance.vision:443` responde `200 Connection Established`.
- **TLS:** versión 1.3, certificado `CN=*.binance.vision` emitido por Amazon RSA 2048 M01.
- **Archivo de prueba:** `BTCUSDT-fundingRate-2024-01.zip` se descargó entero y `sha256sum -c` dio OK.

**Procedencia frente a integridad:**
- El `.CHECKSUM` llega del mismo origen que el zip. Garantiza que el archivo no se corrompió, no quién lo emitió.
- La procedencia la respalda el dominio oficial, validado por TLS.
- No hay firma criptográfica del emisor. Es una limitación del emisor, no del pipeline.

## 2. Inventario (`datos/binance_vision/MANIFIESTO.json`, SHA-256 `8bdabde706bffadc…`)

| Serie | Mensuales | Diarios (completan huecos) | Primer mes | Último mes |
|---|---|---|---|---|
| Spot BTCUSDT 1 h | 80 | 16 | 2019-10 | 2026-05 |
| Perpetuo USDⓈ-M BTCUSDT 1 h | 77 | 0 | 2020-01 | 2026-05 |
| Mark del perpetuo 1 h | 77 | 8 | 2020-01 | 2026-05 |
| Funding del perpetuo | 77 | — (no hay diarios) | 2020-01 | 2026-05 |
| Índice de prima 1 h (opcional) | 77 | 0 | 2020-01 | 2026-05 |

- **Total:** 412 archivos (9,46 MB), cada uno con su `.CHECKSUM`.
- **Manifiesto original solo con mensuales:** conservado en `datos/MANIFIESTO_solo_mensual.json` (`7c08ac3d…`).
- **Registro de la descarga:** `datos/descarga.log`. La descarga es reanudable y separa el 404 (no publicado) del error de red (con reintentos) y del checksum distinto (aborta). Nunca sobrescribe un archivo válido.
- **No publicados (404), 12 archivos:** perpetuo, mark, funding y prima de 2019-10, 2019-11 y 2019-12. Binance no los publica, así que la serie de futuros empieza en 2020-01.
- **Período reservado** (2026-06-01 → 2026-10-13): **no se descargó ni se inspeccionó**. El código lo bloquea.

## 3. Calidad (`datos_oficiales/calidad.md`; filtros prerregistrados C1–C6)

| Filtro | Resultado | Detalle |
|---|---|---|
| C1 checksums | OK | 412/412 coinciden; procedencia `historico_oficial` |
| C2 cobertura | OK | Inicio común **2020-01**; 77 meses sin huecos en las 4 series requeridas |
| C3 horas | OK | 56 232 h; **39 rellenadas** (0,07 %); racha máxima de 6 h |
| C4 funding | OK | 7 029 liquidaciones, todas cada 8 h, alineadas a la hora; sin A2, A2b, A4, A7 ni A8 |
| C5 coherencia | OK | Mediana de \|F/S − 1\| = 0,046 %; p99 = 0,17 %; p99 de \|M/F − 1\| = 0,10 %; sin A6 ni P2 |
| C6 período | OK | 2020-01-01 → 2026-06-01 |

**Incidencias y cómo se trataron.** Todo se decidió antes de cualquier simulación (adenda 2 del prerregistro).
1. **Spot, 8 velas irregulares** por paradas del exchange: 2020-02-19 11:00 (35,5 min), 2020-03-04 09:00, 2020-12-21 14:00 (cierre *anterior* a la apertura), 2021-02-11 03:00, 2021-04-25 04:00, 2021-08-13 01:00, 2021-12-24 04:00 y 2023-03-24 12:00. **Se excluyeron:** su hora queda sin datos y cuenta en C3.
2. **Spot, 35 h sin vela** (paradas). El panel las marca como horas rellenadas planas, en las que el motor no decide. Los diarios oficiales no las tienen: son huecos reales.
3. **Mark, 192 h ausentes en los mensuales**, entre ellas 96 h seguidas del 2021-07-24 al 27, además del 2021-07-01, 2022-07-31, 2022-10-02 y 2023-02-24. Se completaron con los **8 diarios oficiales** de esos días, con checksum, **solo en las horas ausentes**.
4. **Formato:** desde 2025, el spot marca el cierre de vela como apertura + 1 h − **1 µs**. El lector esperaba −1 ms; corregido.
5. **Diario frente a mensual:** en las horas presentes en ambos, los precios coinciden siempre. La única diferencia es el **volumen** del spot del 2021-12-24 a las 03:00 (+1,85 % en el diario). Se conserva el mensual y queda anotado.

**Lectura estricta.** Con solo los mensuales, la muestra **no** habría sido apta: C3 falla por la racha de 96 h del mark. Las decisiones 3 y 5 son las que la hacen apta; no cambian ningún filtro ni ningún dato usado en el test.

## 4. Decisión
**Muestra ACEPTADA** para la evaluación prerregistrada: ventana 2020-01-01 → 2026-06-01, manifiesto `8bdabde7…`. El test se ejecutó una vez con ella (ver `INFORME_ECONOMICO_HISTORICO.md`).

## 5. Datos auxiliares (solo análisis exploratorio posterior al test)
- **Funding ETHUSDT y SOLUSDT** (`datos/otros_simbolos/`): 77 y 69 archivos verificados. SOL no publica los meses anteriores a 2020-09.
- **Letra del Tesoro a 3 meses** (FRED DTB3, `post_test/externos/`, SHA-256 `f9526199…`): aproxima el rendimiento del efectivo. No es un dato de Binance ni un rendimiento realizable sin fricción.
