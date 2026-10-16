# Solicitud de autorización: comprobación previa del exchangeInfo actual (H-CARRY rev. 5)

Fecha: 2026-10-16. Estado: **NO EJECUTADA**. Esta solicitud es independiente de la autorización del experimento histórico y no la sustituye.

## 1. Objeto

Antes de congelar el plan, comprobar una sola cosa: si los metadatos **vigentes** de BTCUSDT, en spot y en el perpetuo USDⓈ-M:
- caben en la lista cerrada de filtros del plan (si no, M1);
- dan una retícula de órdenes no vacía (si no, Q1).

El objetivo es no gastar el único experimento en un SIN VEREDICTO por metadatos.

## 2. Alcance exacto

| # | Petición | Parámetros | Contenido |
|---|---|---|---|
| 1 | `GET https://api.binance.com/api/v3/exchangeInfo` | `symbol=BTCUSDT` | Metadatos de BTCUSDT spot |
| 2 | `GET https://fapi.binance.com/fapi/v1/exchangeInfo` | ninguno, igual que en el plan | Metadatos de **todos** los símbolos de futuros USDⓈ-M. El código solo lee BTCUSDT. |

- Son las mismas dos peticiones que ya forman parte del plan (`exchangeinfo-spot` y `exchangeinfo-perp` en `plan_protocolo_rev5.json`).
- Endpoints públicos: sin claves, sin cuenta y sin credenciales.
- **Excluido:** velas, funding, operaciones, libro de órdenes, precios, cualquier dato histórico o de mercado, cualquier otro endpoint o símbolo, y repetir las peticiones.

**Advertencia sobre el período reservado.**
- Los metadatos son los vigentes el día de la consulta, posterior al período reservado (2026-06-01 a 2026-10-13).
- No contienen precios, volúmenes ni tasas de funding.
- Sí contienen parámetros de reglas (pasos, mínimos, límites porcentuales de precio) y, en la respuesta de futuros, la lista de símbolos con sus fechas de alta. Eso es información **de metadatos** posterior al 2026-06-01, ajena a los rendimientos de BTCUSDT.
- La descarga del experimento ya incluye estas mismas peticiones. Aun así, el responsable debe decidir si lo considera aceptable.

## 3. Herramienta y procedimiento

- **Herramienta:** `h_carry/prechequeo_exchangeinfo.py`, SHA-256 `17a336c14ec1a21c244ed5fe645decedfe8320fd02a4bdec65efec760d086562`. No forma parte del experimento ni de `HC.MODULOS`, y no cambia el plan ni el código.
- **Sin `--autorizacion`** termina con código 2 y no hace ninguna petición. Lo comprueba `test_x3`, también por la CLI.
- **Uso** en la máquina autorizada, desde la raíz de `g4_validacion`, con una carpeta de salida **nueva y fuera del repositorio**:

  ```
  python -I -B h_carry/prechequeo_exchangeinfo.py --autorizacion <REFERENCIA> --salida <CARPETA_NUEVA>
  ```

- **Transporte:** `hc_transporte_http` (urllib, HTTPS GET, 30 s), el mismo del experimento.
- **Salida:**
  - `datos/<sha256>.json`: las dos respuestas crudas;
  - `resumen.json`: peticiones, hashes, incidencias, `apto`, tipos de filtro clasificados como aplicado, no aplicable (S6) o DESCONOCIDO, y los parámetros leídos (paso, mínimos, máximos, nocionales).
- **Código de salida:** 0 si es apto y 1 si hay M1, Q1 o P1.
- **Probada solo con datos sintéticos:** `test_x1` (exactamente las 2 llamadas y los archivos por su hash), `test_x2` (filtro desconocido → M1; mínimo no múltiplo del paso → Q1) y `test_x3`.

## 4. Qué se hace con el resultado

| Resultado | Acción |
|---|---|
| Apto, sin incidencias | Se anota el hash de las dos respuestas. El plan no cambia. |
| M1 (tipo o campo fuera de la lista cerrada) o Q1 | **No** se toca nada automáticamente. Cualquier cambio de la lista cerrada o de la lectura se decide y documenta **antes** de congelar. Cambia el código y el `plan_sha256`, y exige regenerar el inventario y repetir la revisión de ese cambio. |
| P1 (respuesta sin la forma esperada) | Se informa. No se reintenta sin otra autorización. |

**Qué NO aporta:** nada sobre el resultado económico ni sobre los filtros que regían en 2024–2026 (S8). Un «apto» de hoy no garantiza que la descarga del experimento, hecha más tarde, vea los mismos metadatos. El experimento vuelve a pedirlos y los valida.

## 5. Texto de autorización propuesto (para el responsable)

> Autorizo ejecutar una sola vez `h_carry/prechequeo_exchangeinfo.py` (SHA-256 `17a336c1…6562`), en la máquina `<máquina>`, con la referencia `<REFERENCIA>` y la salida en `<CARPETA_NUEVA>`, fuera del repositorio. Alcance: exclusivamente las dos peticiones GET públicas de exchangeInfo de la §2. Quedan excluidos cualquier otro endpoint, los datos de mercado o de funding y cualquier repetición. Esta autorización no autoriza la descarga ni la evaluación del experimento.

Hasta recibir ese texto, o uno equivalente, no se ejecuta.
