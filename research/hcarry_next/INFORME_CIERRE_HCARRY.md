# Cierre de H-CARRY (congelado el 2026-10-17)

**Estado: línea de investigación EVALUADA y CERRADA.** No es una estrategia con rentabilidad demostrada.
- La rev. 5 queda como **baseline histórico**.
- UmbralFunding queda como **hipótesis rechazada** en las condiciones probadas.
- El test prerregistrado está consumido (`TEST_CONSUMIDO.json`): no se vuelve a ejecutar para ajustar nada.

## 1. Qué es original y qué es reconstrucción (detalle en `PROVENANCE.md`)

| Clase | Qué contiene | Garantía |
|---|---|---|
| **Original recuperado** | 9 archivos de rev. 5 en `recuperado/`, más el ZIP de recuperación `5783517c…` | Bytes originales en solo lectura; `SHA256SUMS` verificado (9/9). Solo `prechequeo_exchangeinfo.py` tiene un hash de referencia externo. |
| **Reconstrucción** | Cuentas, costes, funding, reequilibrio, R0 y D1–D4 (`src/hcarry/model`, `metricas.py`) | Reproduce exactamente las cifras documentadas del ejemplo de rev. 5. **No es el código congelado de rev. 5**, que se perdió. |
| **Nuevo** | Motor generalizado, conciliación independiente, laboratorio con prerregistro y cerrojo, pipeline de datos oficiales y calidad, análisis | Desarrollado en H-CARRY Next; 81 pruebas |

## 2. Resultados que se conservan (no se modifican)

| Resultado | Categoría | Artefacto |
|---|---|---|
| P1 (UmbralFunding > rev. 5): **HIPÓTESIS NO RESPALDADA** | Histórico verificado, test de uso único | `experimentos/historico/resultados/historico/datos_8bdabde706bf/` |
| P2 (carry de rev. 5 > 5 % neto): **EVIDENCIA INSUFICIENTE**; 3,76 % en test | Ídem | Ídem |
| Diagnóstico de desarrollo y techo de las reglas de salida | Histórico; solo desarrollo, antes del test | `experimentos/historico/desarrollo/` |
| Compresión del funding, efectivo remunerado, ETH y SOL, causalidad | **Exploratorio posterior al test** | `post_test/`, `causal/`, `INFORME_CAUSAL_COSTOS_VS_SENAL.md` |
| Ensayos de la fase anterior | **Sintéticos**: no son evidencia | `experimentos/sintetico*`, `resultados/sintetico/`, `resultados/caracteristicas/` |

## 3. Qué aprendimos
1. **El carry de rev. 5 es, en esencia, funding × 0,53 del capital.**
   - El 100 % del retorno viene del funding; la cobertura funciona (patas netas ≈ 0) y los costes son pequeños (0,2–0,4 pp/año).
   - Su rentabilidad depende de una sola variable de mercado. Dos tercios del PnL llegaron en meses en que el BTC subía más de un 10 %.
2. **La ventaja frente al efectivo existió en 2020–2021 y desapareció desde 2023.**
   - Funding de BTC: 17 % → 4–12 % → 0,9 % (2026). ETH y SOL siguieron el mismo camino.
   - Al mismo tiempo, el rendimiento del efectivo subió del 0,8 % al 4–5 %.
3. **El funding se predice bien, pero predecirlo no basta.** La correlación semanal es 0,72–0,80. Aun así, salir del carry no aporta: el funding sigue siendo positivo en la zona de salida y cada ida y vuelta cuesta 50 bps del nocional. El techo con oráculo es de 0–0,17 pp/año.
4. **El marco de comparación importa.** Con el efectivo al 0 %, cualquier política que sale del mercado queda castigada por construcción. P2 usaba en cambio un 5 %. La incoherencia está documentada (M-1).
5. **Proceso:** los datos reales encontraron 4 defectos del pipeline que los ensayos sintéticos no habían detectado. El cerrojo del test por manifiesto era eludible y se corrigió antes de usarlo.

## 4. Condiciones económicas que limitan la estrategia
- **Funding mínimo:** ≈ 9,3 % anual sobre el nocional para superar el 5 % con la estructura ρ = 1. En 2025 fue del 5,1 % y en 2026, del 0,9 %.
- **Estructura:** ≈ 47 % del capital queda como garantía de futuros sin rendimiento. Usar el spot como colateral elevaría el nocional, pero también el riesgo de funding y de liquidación, en la misma proporción.
- **Coste de oportunidad:** el efectivo accesible rinde ≈ 4–5 % (DeFi o T-bill, con riesgos distintos). El carry solo lo supera en regímenes alcistas con fuerte demanda de apalancamiento.
- **Riesgos de cola no modelados:** contraparte (un solo exchange), ADL, liquidación dentro de la hora y despegue de la stablecoin.

## 5. Qué NO se puede generalizar
- Ni a otros exchanges, ni a COIN-M, ni a perpetuos de altcoins: sus funding, liquidez y riesgos son distintos.
- Ni a otras estructuras de capital (colateral spot, portfolio margin) o a otros costes (VIP, maker): no se modelaron, salvo como sensibilidad lineal.
- Ni al futuro: si vuelve un régimen como el de 2021, la conclusión cambia. Hay una sola ventana de test y un solo ciclo completo de mercado.
- La rentabilidad de 2020–2022 (9,5 %) es dentro de muestra para el diagnóstico, no una estimación esperada.

## 6. Reproducibilidad y preservación (verificado el 2026-10-17)
- **Replicación determinista del test** con el código actual (`9d11ecbe…`): idéntica. `causal_costos_vs_senal.py` reproduce exactamente el PnL archivado.
- **Integridad del registro:** `TEST_CONSUMIDO.json`, `resultado.json`, `registro.jsonl`, `PRERREGISTRO.json` y el manifiesto `8bdabde7…` coinciden byte a byte con el ZIP del test.
- **ZIP preservados** en `research/entregas_hcarry/`, con `SHA256SUMS` y `SHA256SUMS_2026-10-17`:
  - `hcarry_next_snapshot1.zip` y `hcarry_next_snapshot2.zip` (intermedios);
  - `hcarry_next_final.zip` (fase 1, `41e357bd…`);
  - `hcarry_next_validacion_historica.zip` (commiteado en `c91dff4`, `dc38cb3d…`);
  - `hcarry_test_historico_2026-10-16.zip` (`729fe86b…`);
  - `hcarry_next_historico_2026-10-16.zip` (`63354870…`).
- **Sin commit:** los ZIP nuevos y los cambios desde `c91dff4` están solo en el árbol de trabajo hasta que autorices un commit.
- **Comandos:** `REPRODUCIR.md`.

## 7. Documentos de H-CARRY (no se borran ni se sobrescriben)
- **Estado y recomendación:** `ESTADO_EJECUTIVO_HISTORICO.md`.
- **Economía e informes:** `INFORME_ECONOMICO_HISTORICO.md`, `INFORME_CAUSAL_COSTOS_VS_SENAL.md`, `DIAGNOSTICO_SENAL_EJECUCION_CAPITAL.md`.
- **Datos:** `experimentos/historico/INFORME_DATOS.md`.
- **Registros:** `experimentos/historico/REGISTRO_EXPERIMENTOS.md`, `REGISTRO_DEFECTOS.md`.
- **Prerregistro y adendas:** `experimentos/historico/PRERREGISTRO_VALIDACION_HISTORICA.md`.
- **Fases anteriores:** `INFORME_HCARRY_NEXT.md`, `INFORME_VALIDACION_HISTORICA.md` (anterior a los datos), `PROVENANCE.md`, `DECISIONS.md`, `CHANGELOG.md`.
