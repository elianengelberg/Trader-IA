# Matriz de validación coordinada: T, H-REV-SHOCK y H-EMA9-VWAP (2026-10-20)

**Advertencia de lectura:** las tres líneas **no son experimentos equivalentes**. Difieren en horizonte, datos, estado y nivel de evidencia. **No se comparan rentabilidades entre ellas.** Las cifras de T sirven solo para describir T.

## 1. Matriz

| | **T** (tendencia long/flat) | **H-REV-SHOCK** | **H-EMA9-VWAP** |
|---|---|---|---|
| **Protocolo** | Dos protocolos **originales verificados**. Fuera de muestra: `94a165560ba2…a72c3`, una sola ejecución. Papel: reglas `d2e4e1fb…`, v1 | **Original no recuperado** (`69758896…` no verificable). Existe solo la **propuesta nueva v0.1**, pendiente de aprobación | **Original «v1» no recuperado** (`3114b565…` no verificable). Existe solo la **propuesta nueva v0.1**, pendiente de aprobación |
| **Integridad de artefactos** | Prerregistro, script, código, manifiestos y resultado coinciden con sus hashes registrados. `evidencia_t_multi.py verificar` sin diferencias. Congelado **solo local** (`692f2b2` no publicado) | No hay artefactos originales. La propuesta tiene hash en `SHA256SUMS`; **no** está congelada como protocolo | Ídem |
| **Datos necesarios** | BTCUSDT y ETHUSDT spot 1d | BTCUSDT y ETHUSDT spot 1d | BTCUSDT y ETHUSDT spot 1h |
| **Disponibilidad** | Completos: 212 archivos, 0 días faltantes, checksums oficiales | **Disponibles** (los mismos archivos de T); sin descarga para D y E | **BTC disponible** (96 archivos; 38 de 58 440 horas faltan, 3 en conflicto). **ETH 1h no disponible:** hace falta autorización de descarga |
| **Período de evaluación** | Fuera de muestra 2022-01-01 → 2026-05-31 (ya usado). Papel desde 2026-10-18, cortes 2027-04-18, 2027-10-19 y 2028-10-18 | Propuesto: D ≈ 2017-10 → 2021-12; E 2022-01 → 2026-05 (uso único, contaminado); P prospectivo | Propuesto: D 2019-10 → 2021-12; E 2022-01 → 2026-05 (uso único, contaminado); P prospectivo |
| **Estado de ejecución** | Fuera de muestra **ejecutado** el 2026-10-17 → EVIDENCIA INSUFICIENTE. Papel **sin cortes** | **No ejecutado.** No hay código | **No ejecutado.** No hay código |
| **Evidencia disponible** | Exceso del conjunto +7,0 %/año, IC90 −8,8 / +22,9, P = 0,755: **ni confirma ni descarta** | **Ninguna** | **Ninguna** (E1-P1, otra estrategia horaria de tendencia, dio en contra: es contexto, no evidencia sobre esta) |
| **Evidencia inexistente** | Cortes del papel a 12 y 24 meses | Todo: protocolo aprobado, código, D, E y P | Todo, más los datos de ETH |
| **Incertidumbres** | Efecto real entre ≈ −9 % y +23 %/año; desarrollo probablemente inflado | Número de eventos desconocido, potencia desconocida | Frecuencia de operación y costo real desconocidos |
| **Riesgos de sesgo** | Quien diseñó conocía 2022–2026; dos activos correlacionados; benchmark elegido | Las definiciones de shock y de agotamiento son una entre muchas; contaminación de E; pocos eventos | Muchas variantes posibles (temporalidad, anclaje, horario); contaminación de E por E1 |
| **Próxima acción autorizada** | Ninguna hasta el 2027-04-18. Ese corte necesita **autorización para escribir** fuera o dentro del repositorio | **Revisión y aprobación** de la propuesta (A-RS-0). Nada más está autorizado | Revisión y aprobación (A-EV-0) y, por separado, autorización de descarga de ETH (A-EV-1) |

## 2. Revisión crítica

### 2.1 Supuestos débiles
- **T:**
  - «exceso frente a la estática con la misma exposición» supone que la estática es el contrafactual correcto. Con buy and hold, la conclusión de timing cambia;
  - los costos de 10 + 5 pb no se midieron.
- **H-REV-SHOCK:**
  - z ≤ −3 con σ de 60 días supone una volatilidad local estable. Tras un régimen tranquilo, un movimiento moderado parece un «shock»; tras uno agitado, ocurre lo contrario;
  - el «agotamiento» con dos condiciones de velas es una heurística, no un mecanismo identificado.
- **H-EMA9-VWAP:**
  - el VWAP de sesión UTC es una convención en un mercado 24/7. La sesión no tiene apertura ni cierre económicos, así que el «anclaje» es arbitrario;
  - la EMA(9) a 1 h equivale a unas 9 horas de memoria. Que esa escala tenga información es una suposición.

### 2.2 Posibles errores de implementación a prevenir
- **Marcas de tiempo:** en Binance spot están en **µs desde 2025** y en ms antes. T y E1 ya lo manejan; cualquier implementación nueva tiene que probarlo.
- **VWAP:** se calcula con QV/V de la propia vela, no con el precio típico. Hay que confundir las columnas 5 y 7 a propósito para comprobar que la prueba lo detecta.
- **Vecindad de los huecos:**
  - la EMA tras un hueco y el bloqueo de 9 barras;
  - la sesión incompleta;
  - las 3 horas con conflicto entre mensual y diario.
- **Fin de la ventana E:** qué hacer con una posición abierta al 2026-05-31 (valuarla al cierre o liquidarla con costo) **no está especificado** en las propuestas. Hay que fijarlo al aprobar [pendiente]. No se revisó cómo lo resuelve el código de T.

### 2.3 Alineación temporal
- **T y H-REV-SHOCK:** decisión con el cierre UTC y ejecución en la apertura siguiente.
  - **Riesgo:** en cripto, la «apertura» de las 00:00 UTC coincide con el cierre anterior, así que el retraso real es de **segundos**.
  - El supuesto de ejecutar exactamente en la apertura es optimista. Lo cubre el estrés de un día de retraso.
- **H-EMA9-VWAP:** decisión al cierre de la barra horaria y ejecución en la apertura de la siguiente.
  - Ese retraso es mínimo y el slippage en el cambio de hora puede ser mayor que 5 pb. Lo cubre el estrés con 15 pb y una barra extra.

### 2.4 Costos que podrían faltar
- **Comisión:** sin descuento en BNB (conservador). Para tamaños grandes faltaría el **impacto de mercado**.
- **Impuestos y retiros:** fuera de alcance.
- **Spread variable** en los eventos extremos, justo cuando H-REV-SHOCK opera: puede ser mucho mayor que 5 pb. **El estrés ×3 puede quedarse corto en caídas fuertes.**

### 2.5 Explicaciones alternativas de un resultado favorable
- **H-REV-SHOCK:**
  - deriva alcista de cripto (la mitiga el benchmark de exposición y el nulo emparejado);
  - pocos eventos agrupados (una caída grande puede dominar);
  - recuperaciones de 2020-03 o 2022, conocidas por quien diseña (contaminación).
- **H-EMA9-VWAP:**
  - estar invertido en sesiones alcistas (momentum diario, no intradía);
  - costos subestimados;
  - selección implícita de la temporalidad de 1 h porque los datos de BTC ya existían.
- **T:** un exceso de +7 % sin significación es compatible con el azar y con un efecto real menor que el de desarrollo.

### 2.6 Por qué los resultados podrían no generalizarse
- **Alcance:** un solo exchange, dos activos correlacionados y un período (2017–2026) con regímenes muy específicos (2020-03, 2021, 2022).
- **Microestructura:** las reglas intradía dependen de una microestructura que cambia (liquidez, horario de los participantes).
- **Los datos históricos están contaminados** por el conocimiento de quien diseña. **Solo la fase P es independiente.**

### 2.7 Revisión independiente por otro modelo
**No realizada.** No hay ningún revisor externo disponible ni autorizado en este entorno; no se finge.

## 3. Decisiones metodológicas que requieren tu aprobación
1. **Aprobar, modificar o rechazar** cada propuesta v0.1:
   - H-REV-SHOCK: D-RS-1…9;
   - H-EMA9-VWAP: D-EV-1…9;
   - marco común D-MEC-1…3: bloques de 20 días, Holm m = 2, criterios con nulo emparejado y mínimo de operaciones.
2. **Tratamiento de las posiciones abiertas al final de E** (valuación al cierre, sin costo de salida); hoy no está fijado en las propuestas.
3. **Compuertas de desarrollo** (D-RS-7, D-EV-7): si D con P < 0,10 detiene antes de E.
4. **Conteo de eventos F0 de H-REV-SHOCK**, solo frecuencias, antes de congelar.
5. **Ubicación de los registros del papel de T** antes del 2027-04-18.
6. **Publicar o no** los commits locales `f518ac1` y `692f2b2`. Sin publicar, el congelado de T fuera de muestra y de T-MULTI no es verificable desde fuera.

## 4. Acciones que siguen bloqueadas
| Acción | Motivo |
|---|---|
| Cualquier backtest o ejecución de las tres líneas | Lo prohíbe esta fase; además las propuestas no están aprobadas |
| Recuperar los originales de H-REV-SHOCK y H-EMA9-VWAP | No están en ninguna fuente accesible. Gmail requiere volver a autorizar el conector |
| Descargar ETHUSDT 1h | Sin autorización |
| Cortes del papel de T | No es su fecha; además escriben en el repositorio |
| Reproducir T fuera de muestra | Salvaguarda de uso único; no se elude |
| Verificar el origen del diagnóstico «308 faltantes» | La fuente es externa a la sesión |
