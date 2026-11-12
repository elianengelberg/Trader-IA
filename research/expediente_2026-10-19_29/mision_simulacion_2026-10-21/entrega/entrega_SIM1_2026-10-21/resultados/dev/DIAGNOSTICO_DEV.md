# Diagnóstico de DEV (escrito ANTES de correr OOS-ETH)

Fuente: `resultado_dev.json` y `tablas_dev.md`. Corrida: 2026-10-21, de 20:41:51Z a ≈ 21:58Z.

## 1. Validez técnica: todo bien
- Invariancia de prefijo con datos reales (DEV-ETH, S1 al 70 %): idéntica.
- Determinismo entre procesos (P3 en DEV-ETH, dos veces): idéntico.
- M1 respeta su umbral: todas sus operaciones tienen confianza ≥ q.
- 0 operaciones cortas.
- Round trip máximo: 44 velas (el criterio era 2000).
- 0 barras con posición sin nivel de stop; 0 salidas terminadas con posición restante.
- 35 restos de entrada cancelados al salir: es D3 funcionando.
- Las órdenes rechazadas y los stops sin colocar vienen del rechazo simulado del 1 % y quedan dentro del límite del 3 %.
- Hashes del código idénticos a los congelados a las 20:41:41Z.

**No hay ningún defecto técnico que corregir.** No se toca el motor ni el código antes de OOS.

## 2. Resultado económico: las cuatro configuraciones pierden después de costos, en los dos activos
| | BTC 2017-08→2026-05 | ETH 2017-08→2022-12 |
|---|---|---|
| P3 breakout | −0,288 % [−0,49; −0,09], n = 227 | −0,677 % [−0,95; −0,42], n = 165 |
| P1 trend_following | −0,223 % [−0,34; −0,11], n = 807 | −0,296 % [−0,46; −0,15], n = 496 |
| P2 mean_reversion | −0,529 % [−0,72; −0,33], n = 172 | −0,311 % [−0,74; +0,13], n = 100 |
| S1 fusión | −0,287 % [−0,38; −0,19], n = 1018 | −0,262 % [−0,42; −0,12], n = 615 |

Media neta por operación, % del nocional, con su IC90.

- **El tramo BTC 2017-08 → 2019-09, nunca usado antes, también es negativo:** P3 −0,57 %, P1 −0,15 %, P2 −0,68 %, S1 −0,25 %. Replica E1 hacia atrás en el tiempo.
- **Causa: no hay señal bruta.** Sin costos (S4), la media bruta es ≈ 0 o negativa:
  - BTC: P1 +0,011 %, P3 −0,047 %, S1 −0,043 %, P2 −0,293 %;
  - ETH: S1 +0,006 %, P1 −0,046 %, P2 −0,065 %, P3 −0,468 %.
  - El costo de 0,21–0,27 % por round trip (0,20 % de comisión más el deslizamiento) convierte ese cero en una pérdida.
- **Contra el azar:** las entradas del bot no superan entradas aleatorias con las mismas duraciones (p_nulo de 0,37 a 0,98). En ETH, P3 es peor que el azar (exceso −0,38 %, p_nulo 0,975).
- **Condición de mercado:** pierden en las tres (alcista, lateral y bajista), siempre peor en la bajista.
  - Única celda positiva con n ≥ 20: P2 alcista en ETH, +0,45 % con n = 21. Es una lectura aislada de más de 30 celdas: no se interpreta.
- **Sensibilidades:**
  - comisión ×2 resta ≈ 0,2 % por operación;
  - los gobernadores (S6) casi no cambian nada (las posiciones son ≈ 1 % del capital);
  - con +1 vela de latencia (S3), P2 pierde mucho menos en ETH (−0,05 % contra −0,31 %). Es el mismo patrón exploratorio que E1 vio en BTC (E1-MR-retraso: la entrada de reversión «agarra cuchillos que caen»). Se registra como observación; no se prueba aquí, porque no estaba prerregistrado.
- **Capital:** con ≈ 1 % del capital por posición y del 1 al 10 % del tiempo en mercado, la cuenta de 100 000 pierde entre 0,3 % y 2,6 % en 8,8 años (BTC).
  - Comprar y mantener: BTC +1805 % (máxima caída −84 %); ETH +327 % (−94 %).
  - Las estrategias no compiten con eso: casi todo el capital queda en efectivo.

## 3. Mejora M1 (alta confianza de breakout): NO promovida
- BTC: +0,20 % (n = 88; IC90 −0,06 / +0,47; p_nulo 0,012). Es el activo donde nació la idea; está sesgado.
- ETH: **−0,50 %** (n = 65; IC90 −0,87 / −0,12).
- IC90 combinado: −0,33 / +0,14.
- Falla la regla prerregistrada: media > 0 en ambos activos y límite inferior combinado > 0.
- **Conclusión:** la ordenación por confianza que se vio en BTC (ρ +0,22 en E1; +0,275 aquí) no se traslada a ETH como ventaja económica:
  - el ρ en ETH es +0,12;
  - el tercio alto pierde.
  - Es lo que el sesgo del ganador hacía esperar.
  - El ρ en ETH sigue siendo positivo, pero sin valor económico.

## 4. Qué se espera de OOS (escrito antes de leerlo)
- Con el bruto ≈ 0 en DEV y un costo de ≈ 0,24 % por round trip, lo esperable en OOS-ETH es una media neta ≈ −0,2 a −0,7 % por operación en las cuatro configuraciones.
- Veredictos esperados: EN CONTRA o NO CONCLUYENTE.
- Un resultado favorable sería sorprendente y exigiría primero revisar que no haya un error.
- OOS se corre igual, una vez, con las cuatro configuraciones base y sus sensibilidades, tal como se prerregistró. Así se mide la generalización fuera de muestra y se completa la evaluación.

## 5. Causa: técnica o económica
- **Económica.** El motor reproduce E1 exactamente, pasa la invariancia de prefijo y el determinismo, y no tiene piernas trabadas.
- Las reglas de entrada del bot (tendencia, reversión y ruptura a 1 h) **no tienen ventaja bruta medible** en BTC ni en ETH, en ningún período.
- Ninguna corrección de infraestructura puede crear esa ventaja. Presentar esto como un problema técnico sería disfrazar una hipótesis fallida.
