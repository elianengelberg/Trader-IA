# Errata de este ensayo (SINTÉTICO)

El campo `via` de este ensayo dice «copia aportada por el usuario». **Es falso:** los 400 archivos los fabriqué en este entorno con `hcarry fabricar-sintetico --semilla 101`; el usuario no aportó ningún dato.

El error estaba en `importar`, que escribía siempre ese texto. Corregido el 2026-10-16: el texto ahora describe la importación sin atribuirla a nadie, y una prueba lo cubre (`test_importar_verifica_los_checksums_y_declara_la_via`).

Lo demás no cambia: la procedencia (`sintetico`), las cifras y la conclusión (EVIDENCIA INSUFICIENTE). Repetí el ensayo con el código corregido en `../datos_9992d8439a4d/` y los resultados coinciden exactamente (dif. de PnL en test −211,27; P = 0,0225). Conservo esta carpeta tal como se generó para no ocultar el fallo.
