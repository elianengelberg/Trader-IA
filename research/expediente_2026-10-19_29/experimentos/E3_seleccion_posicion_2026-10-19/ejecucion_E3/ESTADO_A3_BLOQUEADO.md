# E3 · A3 (anuncios oficiales y supervivencia): BLOQUEADO

**Fecha:** 2026-10-20, a partir de las 01:44 UTC.

## Fuentes evaluadas
| Fuente | Resultado | Decisión |
|---|---|---|
| binance.com: categorías Delisting (161), Listing (48) y News (49) | robots.txt permite `/` a cualquier agente y prohíbe `/bapi/` y `/api/`. Las **condiciones de uso no se pudieron leer**: `/en/terms` devuelve HTTP 202 sin contenido (desafío anti-bots). Una referencia de terceros indica que las de Binance.US prohíben el scraping automatizado | **No** se automatiza (v3 §9, nota N8: «si no lo permiten, la compilación es manual») |
| Internet Archive (web.archive.org: CDX y capturas) | **Bloqueado por la política de red del entorno.** La conexión se corta a los 7–9 s en cada intento (`ws_closed_mid_exchange`, registrado por el proxy). La herramienta de lectura web tampoco puede acceder («unable to fetch from web.archive.org»). Solo responde `archive.org/wayback/available` (metadatos); la captura más cercana de la lista 161 es un HTTP 202, el desafío anti-bots | No disponible |
| Canal oficial de Telegram «Binance Announcements» (t.me/s/binance_announcements) | Accesible: ≈ 9066 publicaciones. **Las condiciones de Telegram prohíben expresamente el scraping de datos** («Telegram additionally prohibits data scraping…») | **No** se usa |
| Fuentes no oficiales (agregadores, datasets de terceros) | Fuera de la v3 (§2.3: «anuncios oficiales») | **No** se usan |

## Consecuencia según la v3 (sin interpretaciones nuevas)
- **V-S1 y las categorías A–E** (§2.3) no se pueden calcular.
- **El inicio de la ventana H** (§4.11) depende de las condiciones (ii) última falla, (iii) primer año con anuncios en el archivo y (iv) salidas sin anuncio ≤ 10 %, y las tres requieren anuncios. Sin ellas **no se puede fijar**.
- **Sin mapeo de renombres y redenominaciones** (§2.2.4 y Adenda 1), los cortes de ticker no se pueden resolver.
- **La validez de supervivencia** (§10.2) no se puede establecer, así que **la ejecución confirmatoria NO se realiza**. No se fuerza una ejecución aparentemente válida, y el único uso confirmatorio de los datos queda intacto.

## Qué hace falta para desbloquear (decisión del usuario)
1. **Opción recomendada:** habilitar `web.archive.org` en el acceso a red del entorno («Network access»; agregar el dominio permitido o ampliar el nivel). Después se compilan los anuncios con capturas archivadas (CDX más las páginas), con la URL original, la URL archivada y la fecha de captura de cada caso, y se ejecuta el resto del flujo sin cambios.
2. **Alternativa:** que el usuario confirme que las condiciones de uso de Binance permiten leer de forma automatizada los anuncios públicos, o que provea la compilación hecha a mano. Cualquiera de las dos queda documentada como adenda.
3. **Si la compilación archivada no cubre los primeros años**, aplican las reglas de inicio (iii)–(iv) y la de ≥ 156 semanas, sin cambios.
