# Cierre de E3

**Estado:** NO EVALUABLE con las fuentes disponibles bajo el protocolo congelado.
**Decisión:** del usuario, el 2026-10-20.

## 1. Qué significa este cierre
- **No se obtuvo evidencia de rentabilidad, ni positiva ni negativa.** No se calculó ningún retorno de estrategia, ningún IC de H1, ningún exceso de H2 o H3, ningún diagnóstico con carteras aleatorias reales ni ninguna métrica de desempeño con datos reales. E3-H1, E3-H2 y E3-H3 **no fueron probadas**. El cierre no las confirma ni las descarta.
- **El motivo es un bloqueo de datos, no un resultado estadístico.**
  - La regla de inicio §4.11 (iv) de la v3 exige que, en cada año de la ventana, las salidas de pares sin anuncio de exclusión sean ≤ 10 %.
  - Con la única fuente pública y permitida que estaba disponible, Common Crawl, esa proporción es del 38–100 % según el año, y del 100 % en 2025 y 2026. La última fecha efectiva archivada es el 2024-11-06.
  - Por eso la v3 declara la ventana histórica H **INVÁLIDA con Vision** (detalle en `ejecucion_E3/INFORME_EJECUCION_E3.md`).
- **El uso confirmatorio de la historia sigue intacto:** nadie miró los resultados.

## 2. Qué NO se hizo (por decisión expresa)
- No se relajó la regla (iv) ni se recortó la ventana histórica.
- No se compilaron anuncios a mano ni se buscaron más fuentes.
- No se modificaron la v3, las notas, las adendas, la enmienda, los datos, el código ni los resultados. Este documento y su manifiesto son archivos nuevos.
- No se tocó el repositorio principal: HEAD sigue en `692f2b2`, con las 8 entradas preexistentes intactas. No hubo commits, push ni despliegues, ni se usó dinero real.
- **E3 no continúa.** Reabrirlo o derivar experimentos nuevos de él requiere una autorización expresa.

## 3. Integridad al cerrar (verificada el 2026-10-20)
- Los 8 documentos de `SHA256SUMS` coinciden, v3 incluida (`279a865f…`).
- Coinciden también los registrados en `CONGELACION_ADENDA_3.txt`: Adenda 1, Enmienda 2, Adenda 3, notas, `universo.py`, `motor.py`, `inferencia.py`, `calidad.py`, `cc_indice.py`, `cc_clasificar.py`, `conciliacion.py` y exchangeInfo.
- **Dos diferencias, documentadas antes de usarse:**
  - `codigo/analisis_estructural.py`: corrección para semanas sin candidatos (entrada 6 de `REGISTRO_EJECUCIONES.jsonl`).
  - `codigo/cc_anuncios.py`: colisión de nombres de archivo (`protocolo/CORRECCION_1_cc_anuncios_nombres.txt`).
- Los hashes de todo el directorio al cierre están en `CIERRE_E3_MANIFIESTO.sha256`. Los datos crudos van como hash de conjunto: 26 105 zips de Vision y 8028 páginas archivadas.

## 4. Si algún día se reabre (solo con autorización expresa)
Haría falta una lista completa y verificable de las exclusiones y renombres de pares USDT de Binance entre 2020-05 y 2026-05. Las opciones posibles y sus limitaciones están en el §8 del informe de ejecución.
