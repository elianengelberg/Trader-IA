# Resumen ejecutivo — cierre D1–D3 (v2)

**Veredicto técnico:** APTO PARA INTEGRACIÓN CONTROLADA.
- Es una revisión de ingeniería del motor de backtest, **no una validación de rentabilidad**.
- No autoriza a operar.

## Qué se cerró
1. **Trazabilidad (R4), prioritaria.**
   - El `run_id` de un backtest no incluía el motor ni los datos, y el guardado sobrescribía. Se demostró sobre el original: la base y el motor corregido daban el mismo id con resultados distintos.
   - Ahora cada resultado registra la versión del motor (1.1.0), una huella de su código, la de los datos y la de los instrumentos, y todas entran en el id.
   - El guardado rechaza reemplazar una fila de otra procedencia.
   - Las filas viejas quedan intactas, con motor «desconocido», sin inventarles versión.
   - Sin migración. Lo cubren 12 pruebas y 12 mutantes: 0 vivos, 1 equivalente justificado.
2. **D1–D3, pruebas definitivas.**
   - 8 pruebas. Fallan las 8 contra el motor original, por aserción, y pasan las 8 con el parche.
   - Se agregaron dos invariantes:
     - D2 sin recolocaciones innecesarias;
     - venue nunca del lado contrario.
   - Se agregó un escenario combinado: cierres rechazados dos veces, rechazos, parciales, entradas que expiran, stops por tiempo y reversiones.
   - Mutantes: 10, 0 vivos.
   - Aparecieron dos comportamientos que no son defectos y quedan documentados como riesgos R17 y R18:
     - un cierre que avanza por parciales;
     - una reversión rechazada que no se reintenta.
3. **Pruebas inestables, causa demostrada.**
   - **Reloj:** las dos pruebas fallan entre las 00:00 y las 05:55 UTC porque comparan el día del reloj de pared con el de una sesión simulada que va 5 h 55 m atrás.
   - **Persistencia de 10 s:** el bucle de fondo de la sesión gira en paralelo a la prueba (462.525 ciclos y 49.000 escrituras). No es el disco ni la máquina lenta.
   - **Corrección:** solo pruebas, opcional. No se relajó ninguna aserción ni se subió ningún tiempo límite.
4. **Paridad con E1, sin exagerar.**
   - El motor integrado, sin subclases, reproduce exactamente lo registrado por E1 en P1, P2, P3 y S1, en dos entornos:
     - los datos;
     - las operaciones, con marcas de tiempo y comisiones;
     - **las métricas de la curva y los contadores de decisiones**, que la entrega anterior no había comparado.
   - 0 diferencias no explicadas.
   - Lo que E1 no registró se informa como imposible de verificar.
5. **Reproducibilidad.**
   - Versiones fijadas (74 paquetes) y dos entornos con el mismo `pip freeze`.
   - Suites completas de la base y de la integración comparadas prueba a prueba.
   - Entrega nueva reproducida desde una extracción limpia.

## Qué no está verificado
- La CI de GitHub, que nunca corrió.
- El frontend, las migraciones y la sesión en vivo contra una venue real.
- La equivalencia del backtest con `tia.runtime.live`, que no tiene prueba específica.

## Qué te toca decidir
Autorizar, o no, crear la rama, aplicar los parches 01+02 (y 03 si querés) en tres commits, hacer push y abrir el PR en borrador. Se detalla en `PLAN_INTEGRACION_Y_REVERSION.md`.
