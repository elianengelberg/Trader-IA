# Prerregistro T-MULTI: la regla T, sin cambios, en 12 ETF no cripto (2026-10-17, antes de acceder a cualquier dato)

**Pregunta:** ¿el timing de T tiene una ventaja **transferible** entre mercados, o solo aparece en algún activo?

**Categoría del resultado:** histórico con **procedencia limitada** (proveedores no oficiales, contrastados entre sí). No es prospectivo. No modifica la regla T (`73b22f3e…`), el experimento en papel ni sus fechas.

**Congelado:** este archivo y `experimentos/t_multi.py` se commitean **localmente** (sin push) antes de la primera descarga. La evidencia temporal está en §9.

## 1. Regla (sin cambios)
- **T es un único ensamble**, fijado en `FAMILIAS_ESTRATEGIA.md`: «ensamble fijo y estándar (1, 3 y 6 meses)», implementado en cripto como {30, 90, 180} días corridos.
  - **No son tres variantes:** no hay comparación de horizontes ni posibilidad de elegir el mejor.
  - Se conserva el **horizonte en días corridos**: en cada sesión d, la exposición objetivo es la fracción de h ∈ {30, 90, 180} con cierre_d > cierre de la última sesión ≤ fecha(d) − h días. Sin historia suficiente, no hay señal.
  - El adaptador debe reproducir `tendencia.senal.tsmom` **exactamente** con BTCUSDT y ETHUSDT (autoprueba obligatoria antes de descargar).
- Exposición 0, ⅓, ⅔ o 1. Decisión con el cierre de d; ejecución en la apertura de la sesión siguiente con `tendencia.backtest.simular` congelado. Solo se opera cuando cambia el objetivo. Sin apalancamiento ni cortos. Efectivo al 0 %.
- **Costes:** 5 bps por lado sobre el valor operado (comisión, medio spread y slippage; conservador para estos ETF).

## 2. Universo, fechas y calendario (fijos)
| Clase | ETF |
|---|---|
| Renta variable | SPY, IWM, EFA, EEM |
| Bonos | SHY, IEF, TLT, LQD |
| Materias primas | GLD, SLV, USO, DBC |

- **Criterio:** el ETF estadounidense más antiguo y líquido de cada exposición amplia, emitido antes del 2007-12-31.
- **Fuera:** divisas (un long/flat no tiene un lado largo natural), cripto (ya probada), sectores, países, ETF apalancados o inversos.
- **No se agregan ni se quitan activos después de ver datos**, salvo por las puertas de calidad de §4, que se deciden sin calcular nada de T.
- **Datos:** 2011-01-03 → 2026-09-30, diarios.
- **Evaluación:** sesiones del [2013-01-02, 2026-10-01), ≈ 13,75 años. Es posterior a la publicación de Moskowitz, Ooi y Pedersen (2012).
- **Calendario de referencia:** las fechas presentes en al menos 10 de las 12 series. Se anualiza con 252 sesiones.

## 3. Datos: fuentes, ajustes y procedencia
- **Primaria: Yahoo Finance**, API pública de gráficos v8, sin clave: `query1` (o `query2` como respaldo del mismo proveedor).
  - Trae OHLC ajustado por splits, el cierre ajustado por splits y distribuciones (`adjclose`) y los eventos de dividendos, ganancias de capital y splits.
- **Contraste independiente: Nasdaq**, API pública, sin clave: precios diarios históricos y dividendos de cada ETF.
- **No hay fuente oficial con checksums.** Stooq y FRED no son alcanzables desde este entorno (comprobado solo en la raíz de cada sitio, sin pedir datos).
- **Rendimiento total:** factor_t = adjclose_t / close_t, aplicado a la apertura, el máximo, el mínimo y el cierre de la misma sesión. Los cocientes entre fechas solo dependen de las distribuciones intermedias, así que no hay mirada al futuro. La señal, la ejecución y el benchmark usan precios con rendimiento total.
- **Registro:** cada respuesta cruda se guarda en `datos_multi/` con su URL, su SHA-256, el estado HTTP y la cabecera `Date` del servidor. El resumen va en `datos_multi/MANIFIESTO.json`.
- **Agente:** `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36`.
- **Reintentos:** 4 por solicitud, con esperas de 5, 20 y 60 s, ante errores de red, 429 o 5xx. Se espera 2 s entre solicitudes.
- **Si Yahoo no entrega los 12 activos tras los reintentos, el experimento se detiene y se documenta el bloqueo.**

## 4. Puertas de calidad (por activo, antes de calcular nada de T)
1. **Sesión válida:** OHLC y `adjclose` presentes y > 0, con mínimo ≤ min(apertura, cierre)·(1 + 10⁻³) y máximo ≥ max(apertura, cierre)·(1 − 10⁻³). Una sesión inválida cuenta como faltante.
2. **Cobertura:** primera sesión válida ≤ 2011-01-04 y última = 2026-09-30. Como mucho 5 sesiones de referencia faltantes, y ninguna racha de más de 3.
3. **Ajuste:** el factor reconstruido con las distribuciones del proveedor (dividendos más ganancias de capital), ∏ (1 − D / cierre anterior) para las fechas ex posteriores, coincide con adjclose/close (normalizado a la última fecha) con un error máximo de 0,5 %. Una distribución con fecha ex en una sesión faltante se asigna a la siguiente sesión válida; las de monto nulo se ignoran. Para detectar errores de escala, cada distribución debe estar en (0 %, 15 %] del cierre anterior, y la suma de cada año natural, ≤ 20 %.
4. **Saltos:** un rendimiento ajustado de más del 35 % en una sesión debe estar confirmado por Nasdaq (con una diferencia de menos de 1 pp). Si no se confirma, el activo no pasa.
5. **Contraste con Nasdaq** (si Nasdaq entrega datos de ese activo):
   - En las fechas comunes, el cociente cierre Nasdaq / cierre Yahoo, normalizado por su mediana en cada tramo entre splits, queda dentro de ±0,5 % en ≥ 99 % de los días, y las fechas comunes son ≥ 90 % de las de Nasdaq en la ventana.
   - ≥ 95 % de los dividendos en efectivo de cada fuente, en el período cubierto por las dos, tienen pareja en la otra: fecha ex a ±3 días y monto dentro de max(2 %, 0,002 USD).
   - Si Nasdaq no entrega datos, el contraste queda «no disponible»: no bloquea, pero se informa.
- **Un activo que no pasa alguna puerta se excluye. Si se excluyen más de 2, o alguna clase queda con menos de 3 activos, el experimento no se ejecuta.** Con menos de 10 series legibles de Yahoo no hay calendario de referencia: es un bloqueo, sin diagnóstico por activo.
- **Correcciones de lectura:** si después del congelado aparece un error de *formato* de las respuestas, se corrige solo la lectura, sin tocar la regla, la métrica ni los criterios, y se documenta con su diff.

## 5. Métrica primaria
- Para cada activo i y cada sesión t de la ventana:
  - xᵢ,ₜ = rendimiento diario de T − rendimiento diario de la **estática** con la misma exposición media que T en la ventana (rebalanceo diario sin costes): la fórmula de `tendencia.papel._exceso`.
  - zᵢ,ₜ = (0,10 / σ̂ᵢ,ₜ₋₁) · xᵢ,ₜ, donde σ̂ es la volatilidad del rendimiento total diario de las 252 sesiones previas, anualizada con √252 (ex ante).
- **Xₜ** = promedio de las 3 clases de la media de zᵢ,ₜ sobre los activos de la clase que tienen dato ese día. Un día en que alguna clase no tiene ningún activo no entra.
- **E = 252 · media(Xₜ):** exceso de timing anual a 10 % de volatilidad, con el mismo peso por clase.

## 6. Incertidumbre, dependencia y correlación
- **Bootstrap circular por bloques de 60 sesiones** sobre Xₜ (5 000 remuestreos, semilla 20261017).
  - Remuestrea días completos, así que **conserva la correlación entre activos**. La correlación además se atenúa con el mismo peso por clase, y se informa el número efectivo de activos.
  - P_boot = fracción de remuestreos con media > 0. IC90 por percentiles 5–95.
- **Newey–West** con 60 retardos: P_nw = Φ(media / error); límite superior = media + 1,645 · error.
- **Para decidir:** P = min(P_boot, P_nw) y límite superior = max(los dos límites superiores).
- **Sensibilidad (descriptiva):** bloques de 20 y 120.

## 7. Decisión (una sola ejecución; en este orden)
1. **SIN VENTAJA RELEVANTE:** límite superior < **0,5 %/año** a 10 % de volatilidad, el efecto mínimo que valdría la pena. Rige aunque el efecto sea estadísticamente positivo: si es irrelevante, no se considera una ventaja.
2. **VENTAJA TRANSFERIBLE RESPALDADA:** P ≥ **0,95**, **y** E con costes ×2 > 0, **y** E > 0 al excluir cada una de las 3 clases por turno (la media de las otras dos), para que no la sostenga una sola clase.
3. **EVIDENCIA INSUFICIENTE:** cualquier otro caso.

**Potencia esperada** (supuestos de `REVISION_CRITICA_FUERA_DE_MUESTRA_T.md`):
- P(respaldada) ≈ 20–31 % si E = 0,5 %; 49–75 % si E = 1 %; 64–89 % si E = 1,24 % (el tamaño de cripto).
- P(sin ventaja) ≈ 20–31 % si E = 0.

**Consecuencias declaradas de antemano:**
- **Respaldada:** el timing de T se transfiere; T pasa a ser una candidata seria. El papel sigue igual.
- **Sin ventaja:** se despriorizan T y la familia de tendencia.
- **Insuficiente:** se deja de trabajar históricamente con T.

## 8. Benchmarks y análisis secundarios (descriptivos; no cambian la decisión)
- **Por activo:** T, la estática y buy and hold del mismo ETF (rendimiento total), además del efectivo, con CAGR, volatilidad, Sharpe, caída máxima, exposición, operaciones y costes, todo anualizado con 252.
- **Por clase y por activo:** E y P.
- **Estrés:** costes ×2 y ×3; retraso de 1 sesión. **Sin costes** (bruto), solo para separar señal de costes: al normalizar por volatilidad, el coste fijo de 5 bps pesa más en los activos de baja volatilidad (por ejemplo, SHY).
- **Otros:** número efectivo de activos y correlación media dentro y entre clases.
- Se informan **todos** los activos: no se destaca ninguno ni se repite el cálculo con otro universo o ventana.

## 9. Evidencia temporal y límites
- El commit local de congelado precede a la primera descarga. Las cabeceras `Date` de los servidores quedan registradas en el manifiesto.
- **El commit no está publicado:** su fecha la declara el autor, así que la precedencia no es verificable externamente hasta que se publique.
- **Conocimiento del diseñador:** conozco a grandes rasgos las tendencias de 2013–2026. La regla y el universo están fijados de forma mecánica, pero ese conocimiento no se puede borrar.
- **Ejecución:** el script se niega a evaluar si el resultado ya existe.
