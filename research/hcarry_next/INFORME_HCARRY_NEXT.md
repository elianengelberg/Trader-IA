# H-CARRY Next — informe de la fase 1 (2026-10-16)

> **Advertencia principal.** Todos los resultados económicos de este informe son **SINTÉTICOS**. La política de red del entorno bloquea los datos de mercado: `data.binance.vision` y las API de todas las bolsas responden 403. Este informe **no contiene ninguna conclusión sobre la rentabilidad real** de la estrategia. Sí demuestra que la maquinaria funciona y está lista para correr con datos reales en cuanto se habilite el acceso.

## 1. Ubicación y ejecución

- Proyecto: `research/hcarry_next/`, fuera del control de versiones, sin commits ni pushes.
- Entorno aislado: `.venv` con pytest, hypothesis y ruff. El paquete no tiene dependencias de ejecución.
- Pruebas: `.venv/bin/python -B -m pytest -q` (67 pruebas, sin red, unos 10 s).
- CLI: `PYTHONPATH=src .venv/bin/python -B -m hcarry {estructura|descargar|validar|correr|protocolo}`.
- Datos reales: `experimentos/DATOS_REALES.md` explica qué dominio habilitar y los tres comandos.

## 2. Qué se recuperó, qué se reconstruyó y qué se mejoró

El detalle está en `PROVENANCE.md`.

- **Recuperado:** 9 archivos en solo lectura con sus hashes (`recuperado/`). Solo `prechequeo_exchangeinfo.py` está verificado contra un hash de referencia. **Ningún módulo de `src/` es código original.**
- **Reconstruido:** la contabilidad de dos cuentas, los costes, el funding, el reequilibrio, la liquidación del modelo, R0 y D1–D4. La reconstrucción **reproduce exactamente** las cifras documentadas de rev. 5:
  - equity final 10 014,94;
  - CAGR 0,2022473335;
  - caída 0,001245;
  - distancia a la liquidación 0,985675;
  - W = 10 000 − q·P − q·150;
  - la demostración del sesgo de las omisiones de funding (±22,41 USDT).
- **Nuevo o mejorado:**
  - motor generalizado (ρ, escala, retraso, pata adversa, impacto);
  - conciliación independiente en cada cierre;
  - vista sin look-ahead;
  - tres políticas alternativas;
  - métricas de capital comprometido;
  - laboratorio con prerregistro, test de uso único, bootstrap pareado, líneas base propias y mundos nulos;
  - cargador oficial de Binance con checksums;
  - generador sintético con la fórmula de funding de Binance;
  - análisis de la estructura de capital.

## 3. Pruebas

67 pruebas, todas pasan:

| Grupo | Qué comprueba |
|---|---|
| Contabilidad a mano y regresión rev. 5 (6) | Cifras exactas de rev. 5; funding negativo; D1 con entrada retrasada; E3; R0 |
| Liquidación, reequilibrio, costes y filtros (7) | Liquidación dentro de la barra y por salto, fondo de seguros, enfriamiento, banda, neutralidad, división S7, retraso, pata adversa, cancelación de órdenes pendientes |
| Sin look-ahead (16) | Alterar todo lo posterior a t (precios, prima y funding) no cambia ninguna decisión ni ningún equity anterior (5 políticas × 3 cortes); la prueba detecta un look-ahead deliberado |
| UmbralPrima (3) | Fórmula de funding de Binance, entradas y salidas según la prima de barras cerradas, prima oficial o aproximada |
| Datos (12) | Período reservado bloqueado en todas las entradas; omisiones de funding detectables (A2, A2b) e indetectables con sesgo en ambos sentidos; formato y checksums de data.binance.vision; horas rellenadas |
| Métricas y propiedades (12) | Percentiles, caída con el final, precedencia D1–D4, años; **60 configuraciones aleatorias** (4 políticas, costes ×0–4, impacto, retraso, pata adversa, capital de 10³ a 10⁸) que concilian, mantienen la neutralidad y no dejan saldos negativos |
| Laboratorio (9) | Registro reproducible, guarda del test, mundos nulos, bootstrap, aritmética de la estructura contrastada con el motor, protocolo y estrés |
| Material recuperado (2) | Hashes y solo lectura |

**Defectos encontrados y corregidos** por las propias pruebas y experimentos (ver `CHANGELOG.md`):
- el primer evento de funding sintético;
- un régimen bajista mal calibrado;
- un protocolo que atribuía al umbral la mejora del apalancamiento;
- `rho_vol` confundido con apalancamiento;
- la conciliación con capitales grandes;
- órdenes pendientes que se ejecutaban después de una liquidación.

## 4. Experimentos

Todos los experimentos son reproducibles. Cada ejecución queda en un `registro.jsonl` con la huella del código, el hash de la configuración, el id de los datos y la marca SINTÉTICO.

| Experimento | Configuración | Dónde |
|---|---|---|
| Ensayo v1 del protocolo (5 familias, 39 candidatos) | 12 mundos + 12 nulos; código `3e9073b5…` | `experimentos/sintetico_v1/` |
| **Ensayo v2 del protocolo** (7 familias, 63 candidatos, incluido `UmbralPrima`) | Variante base: 12 + 12 mundos. Variante «bajista suave»: 8 + 8 mundos. Código `a1aeb5a5…`, protocolo `10d33629…` | `experimentos/sintetico/`, resumen en `experimentos/sintetico/RESUMEN.md` |
| Estrés y capacidad v1 | 6 semillas; referencia, ρ = 0,5 y `UmbralFunding`; 9 escenarios, mundos con saltos, capital 10⁴–10⁸ | `experimentos/estres/resumen.md` |
| Estrés v2 | Lo anterior más `UmbralPrima` y la variante «bajista suave» | `experimentos/estres_v2/resumen.md` |
| Persistencia del funding | Correlación entre medias de bloques consecutivos (3, 7 y 30 días) en mundos y en sus nulos | `experimentos/persistencia_funding_sintetico.txt` |
| Aritmética de la estructura | ρ ∈ {1; 0,75; 0,5; 0,33}; amortización de la ida y vuelta | `python -m hcarry estructura` |

**Protocolo de cada mundo** (fijado antes de ver datos):
1. Desarrollo 2019-10 → 2022: se elige el mejor candidato de cada familia.
2. Validación 2023 → 2024-01: el candidato debe superar a su línea base propia.
3. Test 2024-02 → 2026-05, prerregistrado: candidatos y bases, cada uno con 4 estreses.
4. Decisión estricta frente a la base: P ≥ 0,9, sin liquidaciones, caída acotada, y debe seguir siendo mejor con costes ×2.

## 5. Comparación cuantitativa con la referencia (SINTÉTICA)

**5.1 Aritmética de la estructura** (vale con cualquier dato; `python -m hcarry estructura`):

| ρ (margen/nocional) | banda | nocional / equity | APR sobre nocional necesario para un 6 % sobre el equity | salto horario que liquida desde el borde inferior |
|---|---|---|---|---|
| 1 (rev. 5) | (0,5; 1,5) | 50 % | **12 %** | +48,5 % |
| 0,5 | (0,3; 0,75) | 66,7 % | 9 % | +28,7 % |
| 0,33 | (0,2; 0,5) | 75 % | 8 % | +18,8 % |

Una ida y vuelta cuesta 50 bps del nocional: se amortiza en 16,6 días con un funding del 11 % anual y en 36,5 días con uno del 5 %. **Con la estructura de rev. 5, superar D1 exige un funding medio neto ≥ 12 % anual sobre el nocional.** La aritmética está contrastada con el motor en `test_el_motor_cumple_la_aritmetica_de_la_estructura`.

**5.2 Ventana completa 2019-10 → 2026-05, 6 semillas sintéticas, medianas** (`experimentos/estres_v2/resumen.md`):

| Mundo | Política | CAGR base | Caída máx. | CAGR con costes ×2 | CAGR con pata adversa | CAGR con funding × 0,5 | Rotación anual |
|---|---|---|---|---|---|---|---|
| base | **referencia rev. 5** (ρ = 1) | 3,39 % | 13,9 % | 3,22 % | 3,03 % | 1,49 % | 1,3 |
| base | ρ = 0,5 | 3,48 % | 15,8 % | 3,19 % | 2,98 % | 1,55 % | 2,0 |
| base | `UmbralFunding` v21/e0,10/s0,03 | **8,57 %** | 0,7 % | 7,62 % | 7,14 % | 3,21 % | 7,0 |
| base | `UmbralPrima` v24/e0,05/s0 | 2,90 % | 11,9 % | **−5,62 %** | **−11,28 %** | −1,84 % | 65,5 |
| bajista suave | **referencia rev. 5** | 8,27 % | 3,2 % | 8,08 % | 7,97 % | 3,87 % | 1,3 |
| bajista suave | ρ = 0,5 | 9,39 % | 3,6 % | 9,17 % | 8,96 % | 4,47 % | 2,0 |
| bajista suave | `UmbralFunding` | 8,41 % | 1,5 % | **6,87 %** | **5,58 %** | 3,21 % | 9,5 |
| bajista suave | `UmbralPrima` | 3,75 % | 10,9 % | −4,98 % | −12,13 % | −1,54 % | 68 |

- Los retrasos de 1 h y 3 h y la comisión de liquidación del 0,5 % cambian poco: menos de 0,1 pp en la referencia.
- Omitir el 10 % de los eventos de funding resta 0,4–0,9 pp, en proporción al funding perdido.
- No hubo **ninguna liquidación** en ningún escenario, tampoco en mundos con saltos frecuentes.
- La capacidad no está limitada hasta 10⁸ USDT con el impacto supuesto (10 bps × √(nocional/volumen)), que no está calibrado.

**5.3 Período de test del protocolo** (2024-02 → 2026-05 sintético; `experimentos/sintetico/RESUMEN.md`):
- **Variante base:** la referencia rev. 5 obtiene un CAGR mediano del 5,77 % (de −6,4 % a 9,6 %), **por debajo del 6 % de D1** en la mediana. ρ = 0,5 obtiene el 7,12 %.
- **Variante bajista suave:** referencia 11,1 %; ρ = 0,5, 13,0 %.

**Lectura.**
1. El carry permanente de rev. 5 rinde aproximadamente APR/2 menos costes. Con funding medio cercano al interés de Binance (~11 % anual) queda **en el límite de D1**. Su riesgo principal no es la liquidación sino los episodios largos de funding negativo, que producen caídas del 14 % en el mundo base.
2. `UmbralFunding` gana mucho cuando esos episodios existen (+5 pp, caída del 0,7 %). Cuando no existen, no gana nada y pierde con costes altos: es una apuesta sobre la estructura del funding real, no una mejora universal.
3. Predecir el funding con la prima horaria (`UmbralPrima`) dispara la rotación y es la opción más frágil ante los costes. Necesitaría mucho suavizado: el protocolo elige siempre la ventana de 72 h.
4. ρ = 0,5 suma alrededor de 1 pp donde el funding medio es positivo y amplifica las caídas. Su coste real (margen por tramos, liquidación dentro de la hora) no está modelado.

**Rentabilidad teórica frente a potencialmente realizable.**
- Lo teórico es el funding bruto sobre el nocional.
- Lo modelado neto es la tabla 5.2, columna base.
- La cota «realizable» más prudente de este laboratorio es la columna de pata adversa o costes ×2. Para la referencia resta 0,2–0,4 pp; para las reglas activas, 1–3 pp, y para `UmbralPrima` es destructiva.

Nada de esto vale como estimación real hasta correr el protocolo con datos de Binance.

## 6. Limitaciones de los datos y de la evidencia

1. **No hay datos reales.** Todo lo cuantitativo depende del generador sintético. El generador da persistencia al funding por construcción, a través de régimenes y de una prima con reversión a la media. Por eso **cualquier ventaja de `UmbralFunding` en mundos sintéticos es un artefacto posible del generador.** Los mundos nulos solo prueban que, sin persistencia, el protocolo no la declara.
2. **Riesgo de liquidación real no modelado.** No se modelan los tramos de margen, el ADL, la liquidación parcial, el reequilibrio dentro de la hora ni las caídas del exchange. Las variantes apalancadas (ρ < 1) dependen de ello.
3. **Ejecución.** Solo hay estrés extremo (pata adversa al máximo o mínimo de la hora) y retraso. No se modelan ejecuciones parciales ni libro de órdenes.
4. **Filtros y API** recordados, no verificados (supuestos S1 y S8 de rev. 5).
5. **La reconstrucción no es el código congelado de rev. 5.** Su veredicto D1–D4 con datos reales no sustituye al de rev. 5.
6. **Una sola ventana de test por configuración.** Con datos reales, la evidencia fuera de muestra será de unos 28 meses: suficiente para descartar, escasa para confirmar.

## 7. Mejoras que demostraron valor y cuáles no

Todo lo de esta sección es **sintético**. Indica qué componentes tienen un mecanismo que el protocolo detecta, no si funcionan en el mercado real.

| Componente | Normales base (12) | Normales bajista suave (8) | **Mundos nulos (20)** | Lectura |
|---|---|---|---|---|
| `UmbralFunding` (frente a la referencia ρ = 1) | 5 | 2 | **0** | Mecanismo real en el generador: evita los episodios persistentes de funding negativo. La ventaja depende de que esos episodios existan y duren. |
| `UmbralFunding` apalancado (frente a ρ = 0,5) | 6 | 3 | **0** | Igual, con el apalancamiento aislado por la base propia. |
| `UmbralPrima` (frente a ρ = 1) | 3 | 0 | **0** | **Refutada como mejora sobre `UmbralFunding`**: reacciona antes, pero la prima horaria es ruidosa y entra y sale cerca del umbral. |
| `UmbralPrima` apalancado | 3 | 0 | **0** | Ídem. |
| Apalancamiento ρ = 0,5 (frente a ρ = 1) | 3 | 4 | 14 | Mecánico: amplifica cualquier funding medio positivo, persista o no. **No es una mejora validada**: su coste es riesgo de liquidación real no modelado (D-04). |
| `rho_vol` (frente a ρ = 0,5) | 1 | 0 | 2 | Sin señal: los aciertos no superan a los falsos positivos. Se descarta. |
| `escala_vol` (frente a ρ = 1) | 1 | 1 | 0 | Solo ayuda en el mundo con un bajista violento. Señal débil; se descarta como mejora general. |

Las cifras son el número de mundos en que el componente quedó DEMOSTRADO en test frente a su base.

**Falsos descubrimientos de las reglas de persistencia** (umbral y prima, cuatro familias):
- En 20 mundos nulos × 4 familias = 80 oportunidades, el protocolo no declaró ninguna mejora.
- Solo 5 llegaron a test; las demás no pasaron la validación.
- Por la regla del tres, la tasa de falsos descubrimientos por oportunidad es ≤ ~4 % (95 %), con este generador.
- Para `rho_vol` hubo 2 falsos positivos en 20 mundos nulos. Su regla de decisión no es lo bastante estricta para componentes que solo desplazan la exposición.

**Conclusión de esta sección.** Ninguna mejora ha demostrado valor económico real, porque no hay datos reales. En el laboratorio, la única familia con un mecanismo distinguible del ruido es la de reglas de salida basadas en la persistencia del funding (`UmbralFunding`). Su ventaja es condicional a la existencia de episodios largos de funding negativo, y eso está por comprobar en los datos reales.

## 8. Riesgos pendientes y próximo experimento

**Riesgos pendientes, por orden de importancia:**
1. **Sin datos reales no hay conclusión económica.** Es el bloqueo principal y depende de habilitar `data.binance.vision`.
2. **Dependencia del generador.** Las reglas de salida solo valen si en la realidad hay episodios largos de funding negativo; el generador los incluye por supuesto. Hay que medirlo antes de aceptar ninguna ventaja.
3. **Riesgo de liquidación real.** Tramos de margen, ADL, picos de mark dentro de la hora y retrasos de transferencia, todos sin modelar. Bloquea cualquier variante con ρ < 1.
4. **Ejecución.** Ejecuciones parciales, latencia entre patas dentro de la hora, fallos de la API o del exchange. Solo hay cotas extremas (pata adversa, retraso).
5. **Calendario de funding.** Con la política estricta, si el intervalo de BTCUSDT cambió en la historia (A2b), el panel real será bloqueante. Habrá que decidir explícitamente antes de mirar resultados.
6. **Contraparte, USDT y exchange.** Fuera del modelo.
7. **La reconstrucción no es el código congelado de rev. 5.**

**Próximo experimento recomendado, en este orden, sin mirar el test hasta el paso 3:**
1. **Habilitar `data.binance.vision`**, descargar con checksums y validar:
   - `python -m hcarry descargar` y `python -m hcarry validar`;
   - publicar el informe de incidencias **antes** de cualquier simulación.
2. **Diagnóstico de persistencia solo en desarrollo**: `python -B experimentos/persistencia_funding.py datos/binance_vision`.
   - Si la correlación entre semanas consecutivas es baja (< 0,2) o el funding casi nunca es negativo varios días seguidos, se espera que `UmbralFunding` no aporte nada.
   - El protocolo se corre igual; esta es la predicción que queda por escrito para refutarla.
3. **Protocolo completo una sola vez**: `python -m hcarry protocolo --binance-vision datos/binance_vision --salida experimentos/real`.
   - El test es la ventana prerregistrada de rev. 5. La referencia y las bases se evalúan siempre, también bajo estrés.
4. **Si alguna regla de salida queda DEMOSTRADA con datos reales**, no pasar a operar. Antes hay que:
   - modelar los tramos de margen y la liquidación dentro de la hora;
   - hacer una prueba prospectiva en papel de al menos 3 meses, sin órdenes reales y prerregistrada;
   - usar el período reservado, solo con autorización, como confirmación adicional.
5. **Si nada queda demostrado**, el resultado útil es descartar el carry en esta forma (capital 1x, costes minoristas). La aritmética de la sección 5 dice qué haría falta para que fuera viable: funding medio ≥ 12 % anual sobre el nocional con ρ = 1.

## 9. Cambios efectuados en el entorno aislado

- **Creado:** `research/hcarry_next/`, con código, pruebas, documentos, experimentos sintéticos y `.venv` local. El material recuperado está copiado en solo lectura.
- **No se modificó** ningún archivo versionado del repositorio, la rama activa, la producción, el VPS, ninguna base de datos ni ningún `.env`. No se usaron credenciales y no hubo commits ni pushes.
- **Red:** solo PyPI, para instalar pytest, hypothesis y ruff en el `.venv`. Hubo un intento de descarga de `data.binance.vision`, denegado por la política (403) y no reintentado por otras vías.
