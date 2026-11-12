# Borrador de protocolo H-E1-BC: confianza de breakout, prueba confirmatoria (NO EJECUTAR)

**Estado:** borrador para revisar. No se descargaron datos ni se ejecutó nada. Se convierte en prerregistro solo con tu autorización, fijando su SHA-256 antes de descargar.

## 1. Origen y por qué es solo exploratoria
- **[TIA] La observación:** en E1 (BTCUSDT 1 h, 2019-10 → 2026-05), la correlación de Spearman entre la confianza de entrada y el retorno neto por operación fue +0,22 (IC90 bootstrap mensual 0,11 / 0,32; n = 185) en `breakout`.
  - En `trend_following` fue −0,02, en `mean_reversion` −0,08 y en la fusión −0,02.
  - Por banda: 0,55–0,65 rinde −0,67 % (n = 72); 0,65–0,75, +0,20 % (n = 36); ≥ 0,75, +0,06 % (n = 77).
- **Sesgo de selección:**
  - fue 1 de 4 lecturas secundarias sin ajustar; con 4 miradas al 90 %, P(al menos un falso positivo) ≈ 1 − 0,9⁴ ≈ 34 %;
  - el tamaño observado está inflado por el sesgo del ganador;
  - BTC queda **excluido** de la confirmación, porque es el dato del que salió la idea.

## 2. Hipótesis (única)
**H-BC:** en la estrategia `breakout` del bot (v1.1.0, **sin cambios**), ejecutada con el mismo instrumento que E1 (`MotorE1`, con D1–D3 corregidos; solo largos; 1 h; costos de E1), la confianza de entrada se relaciona **positivamente** con el retorno neto por operación, en activos no usados en E1.

## 3. Universo y datos (fijados antes de descargar)
- **Activos:** ETHUSDT y SOLUSDT spot. No se agregan ni se quitan después.
- **Fuente:** data.binance.vision, klines mensuales de 1 h, cada archivo verificado contra su `.CHECKSUM`.
- **Período:**
  - ETH: 2019-10-01 → 2026-05-31;
  - SOL: desde su primer mes completo en spot (≈ 2020-09) → 2026-05-31.
  - Se excluye el período reservado de 2026-06 en adelante.
- **Tratamiento de datos:** el mismo que E1 (sin relleno; horas en conflicto entre archivos, como faltantes).

## 4. Métricas e inferencia
- **Primaria:**
  - ρ de Spearman entre la confianza de entrada y el retorno neto (% del nocional) por round trip, con los dos activos **combinados**;
  - p unilateral = fracción de ρ\* ≤ 0 en un bootstrap por bloques de mes calendario (10 000 réplicas; los meses se remuestrean conjuntamente para ambos activos).
  - Usar una sola prueba primaria evita la multiplicidad.
- **Consistencia, obligatoria:** ρ > 0 por separado en ETH y en SOL (solo el signo).
- **Económica (para hablar de ventaja, no de relación):**
  - se toma el tercio superior de confianza, con terciles definidos **dentro de cada activo** sobre sus propias operaciones, una regla fija sin umbral tomado de BTC;
  - debe tener una media neta por operación > 0 con el límite inferior del IC90 > 0 (bootstrap mensual);
  - y debe superar al nulo de entrada aleatoria emparejada de E1 (mismas duraciones, estratificado por trimestre, 2 000 réplicas) con p_nulo ≤ 0,05;
  - además, la media del tercio superior con comisión ×2 debe ser > 0.
- **Costos:** los de E1 (10 bps por lado, deslizamiento base de 2 bps más el componente de rango, impacto, ejecución en la apertura siguiente y stops al peor precio).

## 5. Decisión
1. Menos de 60 operaciones combinadas: **INSUFICIENTE (muestra)**.
2. Límite superior del IC90 de ρ < 0: **EN CONTRA** (la confianza no ordena, o lo hace al revés).
3. p ≤ 0,05 y ρ > 0 en cada activo: **RELACIÓN CONFIRMADA**.
   - Si además pasa la prueba económica: **VENTAJA NETA DEL TERCIO DE ALTA CONFIANZA RESPALDADA** (todavía histórica: requeriría una validación prospectiva antes de cualquier capital).
4. Cualquier otro caso: **NO CONFIRMADA**.

## 6. Control del sesgo de selección y de las pruebas múltiples
- Una sola estrategia (breakout), un solo marco (1 h), reglas y parámetros **sin cambios**, y **ningún umbral elegido**: se usan terciles internos.
- Una prueba primaria (ρ combinado). La consistencia por activo y la prueba económica son condiciones adicionales, no pruebas alternativas: solo pueden **endurecer** la conclusión.
- Si H-BC entra en la ronda E2 junto con otras hipótesis confirmatorias, se aplica **Holm** sobre la ronda (hasta 3 hipótesis).
- Se prohíbe:
  - repetir la prueba con otro marco o activo;
  - cambiar los terciles;
  - filtrar por régimen después de mirar;
  - reportar solo el activo favorable.
- Se informa todo, también si falla, y queda en el registro de hipótesis.

## 7. Potencia orientativa [Hip]
Aproximación: z ≈ atanh(ρ)·√(n − 3), con n ≈ 300 operaciones combinadas (supuesto: unas 150 por activo; el número real se conoce solo al correr).

| ρ verdadero | z | Potencia (α = 0,05 unilateral) |
|---|---|---|
| 0,22 (el de BTC, probablemente inflado) | ≈ 3,9 | ≈ 0,99 |
| 0,10 | ≈ 1,7 | ≈ 0,5 |
| 0,05 | ≈ 0,9 | ≈ 0,2 |

Un «no confirmada» con un ρ verdadero chico es esperable. La prueba económica es más exigente que la relación.

## 8. Validez (antes de interpretar; si falla, se detiene)
- Verificación de checksums.
- Invariancia de prefijo con datos reales.
- 0 cortos.
- 0 piernas huérfanas.
- Ningún round trip de más de 2 000 barras.
- Contadores de D3 informados.

## 9. Autorización necesaria y costo
- **Descarga:** ETHUSDT y SOLUSDT spot klines 1h mensuales con `.CHECKSUM`, de data.binance.vision.
  - Son unos 80 + 70 archivos (≈ 4 MB por activo, según el tamaño de los de BTC).
- **Cómputo:** unas 6 corridas de ≈ 5 minutos (base y comisión ×2 por activo, más la invariancia de prefijo), más el nulo. En total, unos 20 minutos.
