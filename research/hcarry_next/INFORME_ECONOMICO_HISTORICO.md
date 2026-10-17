# H-CARRY: informe económico con datos históricos oficiales (2026-10-16)

**Alcance:**
- BTCUSDT: spot de Binance y perpetuo USDⓈ-M, 2020-01 → 2026-05.
- Datos: data.binance.vision verificados (`experimentos/historico/INFORME_DATOS.md`).
- Motor reconstruido de H-CARRY Next, con huella `8a7cb042…`.

**Categorías:**
- §1–§3: **histórico verificado** con el protocolo prerregistrado.
- §4–§6: **exploratorio posterior al test**; ya no es evidencia independiente.
- No hay resultados prospectivos ni operaciones reales.

## 1. Conclusión prerregistrada (test de uso único, ejecutado el 2026-10-16 a las 20:47 UTC)

| Pregunta | Conclusión | Motivo |
|---|---|---|
| **P1.** ¿UmbralFunding mejora a rev. 5? | **HIPÓTESIS NO RESPALDADA** | En test, umbral − rev. 5 = **−264 USDT**; P(diferencia > 0) = **0,00**. También pierde en validación (−135; P = 0,0005) y en desarrollo (−544; P = 0,001). |
| **P2.** ¿El carry de rev. 5 tiene ventaja neta? | **EVIDENCIA INSUFICIENTE** | CAGR neto en test de **3,76 %**: positivo, pero por debajo del comparador del 5 % fijado de antemano. Con costes ×2, 3,55 %. |

- **Registro:** `experimentos/historico/resultados/historico/datos_8bdabde706bf/` y el cerrojo `TEST_CONSUMIDO.json`.
- **Huellas:** prerregistro `90642cd1…`, código `8a7cb042…`, datos `8bdabde7…`.
- **Predicción escrita antes del test (adenda 3):** «P1 = no respaldada». Se cumplió.
- **D1–D4 de rev. 5** (reconstrucción, regla R0) en test: **DESCARTADA** (D1: rentabilidad insuficiente).

## 2. Resultados por división (costes base: spot 10 + 5 bps, perpetuo 5 + 5 bps; capital de 10 000 USDT; ρ = 1)

| División | Política | CAGR neto | PnL | Caída máx. (duración) | Vol. anual | Funding cobrado / pagado | Costes | Tiempo en mercado | Operaciones | Liquidaciones |
|---|---|---|---|---|---|---|---|---|---|---|
| Desarrollo 2020–22 | rev. 5 | **9,48 %** | 3 125 | 2,15 % (123 d) | 1,03 % | 3 573 / 293 | 113 | 100 % | 24 | 0 |
| | umbral | 7,95 % | 2 581 | 1,77 % (354 d) | 1,09 % | 3 024 / 59 | 354 | 55 % | 37 | 0 |
| Validación 2023-01 → 2024-01 | rev. 5 | **4,04 %** | 439 | 1,12 % (14 d) | 0,35 % | 490 / 12 | 39 | 100 % | 5 | 0 |
| | umbral | 2,80 % | 304 | 1,40 % (122 d) | 0,45 % | 387 / 3 | 84 | 60 % | 8 | 0 |
| **Test 2024-02 → 2026-05** | **rev. 5** | **3,76 %** | 899 | 0,25 % (118 d) | 0,37 % | 1 022 / 73 | 45 | 100 % | 7 | 0 |
| | **umbral** | **2,68 %** | 635 | 0,31 % (232 d) | 0,39 % | 726 / 5 | 87 | 46 % | 8 | 0 |

- **Descomposición de rev. 5 en test:** funding neto +949, costes −45, patas de precio −4. **El 100 % del retorno es funding;** la cobertura spot/perpetuo funcionó, con un PnL de precio casi nulo.
- **rev. 5 por año** (toda la muestra; exploratorio):

| 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (ene–may) |
|---|---|---|---|---|---|---|
| 8,96 % | **18,1 %** | 2,11 % | 4,30 % | 6,44 % | 2,52 % | **0,02 %** |

- **Concentración:** el 10 % de los mejores días aporta el 41–58 % del PnL de rev. 5 y el 62–73 % del de umbral.
- **Sharpe y Sortino** (8–30) **no son informativos.** La volatilidad diaria del carry cubierto es mínima y su riesgo real es de cola (exchange, ADL, liquidación dentro de la hora), algo que la serie diaria no recoge.

## 3. Sensibilidad en test (los 8 escenarios prerregistrados)

| Escenario | rev. 5 | umbral | umbral − rev. 5 (USDT) |
|---|---|---|---|
| Costes ×0,5 | 3,86 % | 2,86 % | −243 |
| Costes ×2 | 3,55 % | 2,30 % | −302 |
| Costes ×3 | 3,36 % | 1,94 % | −343 |
| Retraso 1 h | 3,77 % | 2,68 % | −264 |
| Retraso 3 h | 3,77 % | 2,69 % | −263 |
| Pata del perpetuo adversa | 3,34 % | 2,38 % | −231 |
| Funding ×0,75 | 2,66 % | 1,15 % | −361 |
| Nocional mínimo del perpetuo 5 USDT | 3,76 % | 2,68 % | −264 |

- **Bootstrap pareado** (bloques de 30 días, 2 000 remuestreos), umbral − rev. 5 en test: **−1,05 pp/año**, IC90 [−1,47; −0,65].
- **Ningún escenario invierte el signo.** El supuesto que más pesa en P2 es el nivel de funding, no los costes ni la ejecución.

## 4. Por qué UmbralFunding no aporta (desarrollo antes del test; validación y test después)
- **Persistencia, solo en desarrollo:** la correlación de medias de 7 días consecutivos es **0,72** y la ACF a 21 eventos, 0,43. La predicción prerregistrada (< 0,2 → no aporta) **no** se activó. Aun así, umbral perdió: la persistencia es **necesaria pero no suficiente**.
- **Atribución en desarrollo (−544 USDT):** −516 de funding positivo perdido estando fuera, +234 de funding negativo evitado y −241 de costes extra.
- **Techo de cualquier regla de salida** (oráculo con conocimiento perfecto, coste de ida y vuelta de 50 bps del nocional):

| División | Costes base | Costes ×0,5 | Costes ×2 |
|---|---|---|---|
| Desarrollo | 0,17 pp/año | 0,27 | 0,09 |
| Validación | **0,00** | 0,00 | 0,00 |
| Test | **0,00** | 0,03 | 0,00 |

- **Razón económica:** los episodios negativos son cortos. En desarrollo, la mediana es de 8 h y solo 3 superaron los 3 días. Salir y volver a entrar cuesta más que el funding negativo que se evita.

**La línea «reglas de salida por funding» (UmbralFunding, sus variantes y UmbralPrima) queda DESCARTADA.** Ninguna variante puede superar un techo de 0–0,17 pp/año.

## 5. Por qué el carry de rev. 5 ya no compensa (exploratorio posterior al test)
- **Aritmética de la estructura:** con ρ = 1, el nocional medio es 0,51–0,63 veces el capital, y el retorno es aproximadamente el funding × 0,55 menos 0,2–0,4 pp de costes. Para batir el 5 % hace falta un funding de **≥ 9,2 % anual** sobre el nocional. En test se cobró un **7,2 %**.
- **El funding se comprimió en todo el mercado** (APR anual sobre el nocional):

| | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|---|
| BTC | 17,2 % | 30,6 % | 4,2 % | 7,9 % | 11,9 % | 5,1 % | 0,9 % |
| ETH | 27,4 % | 37,5 % | 0,8 % | 8,3 % | 13,0 % | 4,9 % | 0,4 % |
| SOL | — | 28,6 % | −38,0 % | 1,3 % | 13,6 % | 0,4 % | −3,2 % |

  \*2026: enero–mayo, anualizado.
- **En BTC cambió la composición del funding.** Los eventos en la tasa base (0,01 % cada 8 h, unos 10,95 % anuales) pasaron del 50 % en 2020 al 17 % en 2025 y al 2 % en 2026. En 2025, ningún evento superó la base.
- **Regímenes ex ante, solo en desarrollo:** con el BTC subiendo > 10 % en 30 días, el funding de los 7 días siguientes promedió un 32 % anual; con caídas > 10 %, un 3 %. El funding previo de 7 días predice el siguiente (correlación de 0,71). La volatilidad y el volumen no aportan (|corr| < 0,05). **La ventaja del carry existe en mercados alcistas con apalancamiento demandado y desaparece fuera de ellos.**

## 6. Coste de oportunidad: el efectivo remunerado (exploratorio; supone que el USDT ocioso rinde la letra a 3 meses)

| División (T-bill medio) | rev. 5 | umbral | Solo efectivo | Techo oráculo carry ↔ efectivo |
|---|---|---|---|---|
| Desarrollo (0,8 %) | **9,48 %** | 8,66 % | 0,80 % | 9,95 % |
| Validación (5,1 %) | 4,04 % | 4,89 % | **5,07 %** | 5,63 % |
| Test (4,3 %) | 3,76 % | **4,86 %** | 4,21 % | 5,36 % |

- **El prerregistro fijó el efectivo a 0 % en P1 y un comparador del 5 % en P2.** Ese marco castiga por construcción a las políticas que salen del mercado. Con efectivo remunerado, umbral supera a rev. 5 en validación y test, pero **apenas iguala al efectivo** y no lo hace en desarrollo.
- **Tope de la alternancia carry ↔ efectivo:** ni con conocimiento perfecto mejora a la mejor opción fija en más de **0,4–1,0 pp/año**. Con un recorte de 1 pp en el rendimiento del efectivo, las diferencias realizables quedan dentro del ruido de una sola ventana.
- **Esto no cambia P1 tal como se prerregistró,** pero sí su lectura: la señal de UmbralFunding no tiene valor contra el carry permanente y tiene poco contra el efectivo.

## 7. Riesgos no capturados por las cifras
- **Contraparte:** todo el capital está en un único exchange; un fallo o congelación de retiros es una pérdida de cola que el backtest no contiene.
- **Liquidación real:** tramos de margen, ADL y liquidación dentro de la hora no están modelados. Con ρ = 1, la distancia mínima a la liquidación fue del 42–48 % y no hubo ningún evento.
- **Ejecución:** la pata adversa extrema resta 0,4 pp en test y 2,8 pp en desarrollo. No hay libro de órdenes ni ejecuciones parciales.
- **Costes del efectivo y de las transferencias** entre cuentas: supuestos, no calibrados.

## 8. Revisión crítica

| Pregunta | Respuesta |
|---|---|
| ¿Qué se probaba? | P1 (umbral > rev. 5) y P2 (rev. 5 > 5 % neto). |
| ¿Explicación alternativa? | Para P1: el marco de efectivo a 0 % (§6). Comprobado: con efectivo remunerado umbral mejora, pero no supera de forma material al efectivo. Para P2: un período de test atípicamente malo. En contra: la compresión es gradual (2022–2026) y abarca todo el mercado (§5). |
| ¿Qué podría estar mal? | Las decisiones del pipeline (velas irregulares y diarios) solo afectan horas de desarrollo y validación. Los costes son conservadores, pero ×0,5 no cambia nada. El motor es una reconstrucción; la conciliación independiente pasa en todas las ejecuciones. |
| ¿Qué contradice la lectura favorable? | rev. 5 rindió 0,02 % en 2026 y un 3,76 % frente al 4,3 % del T-bill en test. |
| ¿Qué haría abandonar la hipótesis? | Para P1, ya ocurrió. Para el carry en general: que el funding siga por debajo de unos 9–12 % anual. |
| ¿Experimento siguiente más informativo? | Ninguno histórico: las ventanas están consumidas. Solo seguimiento prospectivo del régimen de funding (`RECOMENDACION` en `ESTADO_EJECUTIVO_HISTORICO.md`). |
