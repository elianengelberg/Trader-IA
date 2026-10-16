# Fuentes de datos para la validación histórica: evaluación (2026-10-16)

**Necesidad:** BTCUSDT en spot, perpetuo USDⓈ-M, precio mark y funding, en barras de 1 h, de 2019-10 a 2026-05. Debe tener procedencia verificable, idealmente con checksum del emisor.

## Accesibilidad desde este entorno

Probé solo la conectividad a la raíz de cada servicio, sin pedir datos. La política de red responde 403 a todo lo que no sea gestores de paquetes y GitHub.

| Fuente | Datos que ofrecería | Legitimidad y procedencia | Accesible aquí |
|---|---|---|---|
| **data.binance.vision** (archivos mensuales) | Todo lo necesario, con `.CHECKSUM` SHA-256 por archivo | Oficial de Binance; **la mejor opción** | **No** (403) |
| data-api.binance.vision / api.binance.com / fapi.binance.com | API REST oficial | Oficial | No (403) |
| Bucket S3 que hay detrás de data.binance.vision | El mismo contenido | Sería **eludir** la denegación del dominio | **No se usa ni se prueba** |
| Tardis.dev (api y datasets) | Datos de mercado detallados; histórico completo de pago, con clave | Proveedor comercial reconocido | No (403); además requiere clave |
| Coin Metrics Community API | Algunos datos de mercado de acceso libre (cobertura de funding sin verificar) | Proveedor reconocido | No (403) |
| CoinGlass, CoinGecko, Kaiko, Amberdata | Funding agregado o precios; casi todos con clave | Comerciales | No (403) |
| Otras bolsas (Bybit, OKX, BitMEX, Deribit, KuCoin, Gate, Bitget, MEXC, Bitfinex, dYdX, Hyperliquid) | Su propio funding y sus precios | Oficiales de cada bolsa, pero **otro instrumento**: no es la estrategia de rev. 5 | No (403) |
| CryptoDataDownload, Kaggle, Hugging Face, Zenodo, Figshare | CSV de terceros | Procedencia no verificable frente a Binance | No (403) |
| Repositorios de terceros en GitHub | CSV de terceros | Procedencia no verificable; fuera del alcance de esta sesión | Técnicamente sí, pero **descartado** |
| Yahoo Finance | Solo precio spot | Sin funding ni perpetuo | No (403) |

## Vías legítimas que quedan, todas con una acción tuya

1. **Habilitar `data.binance.vision`** en la configuración de red del entorno (Allowed domains). Es la vía recomendada: después basta con `python -m hcarry descargar …` (ver `DATOS_REALES.md`).
2. **Descargar en tu máquina y aportar la copia.**
   - En una máquina con acceso a Binance, desde el ZIP de H-CARRY Next:
     `PYTHONPATH=src python3 -m hcarry descargar --destino binance_vision --desde 2019-10 --hasta 2026-06`
     Solo usa la biblioteca estándar. Baja cada zip con su `.CHECKSUM` oficial y los verifica.
   - Subí la carpeta a una rama nueva del repositorio. Google Drive no es fiable para varios MB: la herramienta devuelve el contenido en base64 dentro de la conversación.
   - Aquí la importo con `python -m hcarry importar`, que vuelve a verificar cada archivo contra su `.CHECKSUM` oficial.
3. **Un proveedor con clave** (por ejemplo Tardis.dev): requiere credenciales y habilitar su dominio. Lo descarto mientras haya una fuente oficial y gratuita.

**Riesgo de la vía 2:** los `.CHECKSUM` viajan con la copia. Una copia manipulada a la vez en datos y checksums no se detectaría. Si querés más garantía, comprobá en tu máquina algunos hashes al azar contra data.binance.vision, o habilitá la vía 1.

**Decisión:** no se usa ninguna fuente que no sea data.binance.vision (o una copia suya verificable). Mezclar instrumentos o fuentes sin checksum cambiaría la pregunta y debilitaría la procedencia.
