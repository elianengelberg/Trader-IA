# Fase 3 — Nota previa a la calibración confirmatoria del diseño secuencial (SEC-1.0)

Escrita y fijada por SHA-256 **antes** de calcular ninguna trayectoria con las semillas confirmatorias (20261105 y
20261106). Datos **sintéticos**.

## 1. De dónde sale la autorización de esta corrida
Es el mensaje del propietario en el chat de la sesión, del 2026-10-21. Transcribo sus partes pertinentes; es una
transcripción, no una firma:
> «Fase 3: calibrar el diseño secuencial completo. Determiná el error global del procedimiento de cinco miradas […]
> Usá datos sintéticos identificados como tales. […] Si hace falta desarrollar el método de forma iterativa, reservá una
> calibración confirmatoria con especificación y semilla fijadas antes de ejecutarla. […] Si la misión no autoriza esta
> corrida adicional, no la ejecutes».

**Interpretación**, que el propietario puede corregir:
- el mensaje ordena determinar el error global con datos sintéticos y fija cómo hacerlo;
- ninguna restricción vigente prohíbe una simulación sintética: las prohibiciones son de datos de mercado, trading,
  commits, push, despliegue, paquetes históricos y firmas;
- por eso la corrida está autorizada.

**Lo que esta corrida no toca:** T, T-MULTI, el repositorio, r1, v0.5 y el ZIP A-S1.

## 2. Procedimiento calibrado (formalización)
- **Variable:** el exceso diario x_d del MEC §2. Media poblacional μ = E[x_d].
- **Hipótesis:**
  - **H₀:** μ ≤ 0. Se calibra en el borde μ = 0, con los procesos C1–C6 de `pec.sintetico.proceso` (r1, `7b15c677…`).
  - **H₁** (solo para la potencia, descriptiva): μ = μ_d > 0, sumado a cada día en C1, C2 y C5.
    - μ_d = IR · σ_d / √365,25, con σ_d = 1 %.
    - Esta equivalencia vale porque esos tres procesos no tienen autocorrelación, así que su varianza de largo plazo es
      la marginal.
- **Miradas:** K = 5, con n_k = round(k · n_max / 5).
  - Son **prefijos anidados de una misma serie**: la dependencia entre miradas es la real, no un supuesto.
  - La fracción de información es t_k = n_k / n_max.
- **Estadístico de cada mirada:** p_k = máx(p_ℓ20, p_ℓ40, p_NW, L = 20). Es la regla de respaldo de `pec.inferencia`
  (r1, `99d0d3e6…`), validada por A-S1.
  - B = 9999.
  - **La misma semilla de bootstrap en las 5 miradas**, como en un prerregistro real (una sola semilla congelada).
- **Fronteras:** c_k de `pec.secuencial.fronteras_obf` (r1, `90f3a4c2…`): Lan–DeMets tipo O'Brien–Fleming, α = 0,025
  unilateral, evaluadas en t_k.
- **Regla de parada y decisión:**
  - se **CONFIRMA** en la primera k con p_k ≤ a_k = 1 − Φ(c_k);
  - si no hay confirmación en k = 5, el resultado es NO CONFIRMADA;
  - una mirada degenerada (sin variabilidad) no decide.
  - Con B = 9999, p ≥ 10⁻⁴. Como a_1 ≈ 5·10⁻⁷, **la mirada 1 no puede confirmar nunca**. Es una propiedad del
    procedimiento real y se calibra tal cual.
- **Futilidad:** es no vinculante y solo detiene sin confirmar. **Se omite**, así que el error medido es una **cota
  superior** del de cualquier aplicación con futilidad.
- **Error global:** α_global = P(confirmar en alguna mirada | H₀).
- **Procesos dispersos:** C4 es el proceso por eventos (exposición de Markov dispersa, tipo H-REV-SHOCK). Muchas de sus
  miradas tempranas tienen pocos eventos. C5 es el intradía agregado (tipo H-EMA9-VWAP). C6 es el cambio de régimen,
  que cae solo en algunas miradas.

**Cortocircuito exacto.** máx(p) ≤ a si y solo si p_NW ≤ a, p_ℓ20 ≤ a y p_ℓ40 ≤ a. El bootstrap solo se calcula cuando
hace falta. Comprobado frente a `inferencia.respaldo` completo:
- 240 de 240 trayectorias de desarrollo idénticas, 147 de ellas con confirmación;
- se vuelve a comprobar después de ejecutar, con muestras de la corrida confirmatoria.

## 3. Celdas, réplicas e incertidumbre de Monte Carlo
- **H₀:** 6 procesos × n_max ∈ {1096, 1461, 1826} (3, 4 y 5 años) = **18 celdas**.
  - **R = 36 000** trayectorias por celda; semillas 20261105·10⁶ + r.
  - Error de Monte Carlo en α = 2,5 %: 0,082 puntos porcentuales.
- **H₁:** (n_max = 1096, IR = 1,64) y (n_max = 1826, IR = 1,27), en C1, C2 y C5.
  - Son los puntos de diseño de la criba de r1 (potencia analítica del 80 % con la prueba z).
  - R = 500; semillas 20261106·10⁶ + r. Error de Monte Carlo ≤ 2,3 puntos.

## 4. Criterio de aceptación (vinculante)
**APTO** si, en **cada una** de las 18 celdas H₀, la cota superior exacta de Clopper–Pearson unilateral de α_global, con
confianza 1 − 0,05/18 (Bonferroni, válido con cualquier dependencia entre celdas), es **≤ 3,0 %**. Si no, **NO APTO**,
y PEC-1.1 no puede declarar controlado el error global.

**Por qué 3,0 %:** es 1,2·α. Queda entre el criterio estricto (1,1·α) y el liberal (1,5·α) de Bradley (1978) y por debajo
del límite por mirada que A-S1 ya toleraba (3,2 %). Se **demuestra** con confianza conjunta, no se mira la estimación
puntual.

**Propiedades, calculadas antes** (`registro/f3_propiedades_del_criterio.json`):
- una celda cumple si α̂ ≤ 2,75 % (990 de 36 000);
- con un α_global verdadero de 2,5 %, cumple con probabilidad 0,9987, y las 18 con 0,977 (si fueran independientes);
- con 2,75 % cumple con 0,51, con 3,0 % con 0,0026 y con 3,5 % con ≈ 0.

Así se corrige el defecto de A-S1, cuyo criterio hacía fallar a una prueba perfecta con probabilidad ≈ 62 %. R se eligió
entre 30 000, 36 000 y 40 000 **solo** con estas propiedades y el costo, sin ver ninguna tasa.

**Lectura descriptiva, que no cambia el veredicto:**
- α̂ frente a 2,5 % y al criterio estricto de Bradley;
- confirmaciones por mirada frente al gasto teórico;
- correlación de z_NW entre miradas frente a √(t_j/t_k): contrasta el supuesto de incrementos independientes del
  MEC §7.1;
- potencia simulada frente a la analítica de la prueba z.

## 5. Verificación posterior (fijada ahora)
`analizar_secuencial.py` recalcula, **con `inferencia.respaldo` completo** (sin cortocircuito), por cada celda H₀, 3
trayectorias al azar y hasta 10 confirmadas, elegidas con la semilla 20261108. Exige la misma mirada de confirmación.

## 6. Fase de desarrollo (declarada)
- **Semilla:** 20261104, distinta de las confirmatorias.
- **Para qué sirvió:** probar el código, medir el costo y comprobar el cortocircuito.
  - Se corrieron 100 trayectorias por celda H₀ y 20 por celda H₁.
  - **No se leyó ninguna tasa de desarrollo para decidir nada.** El veredicto de desarrollo (con R = 100 no tiene
    significado) no se usa.
- **Cambios de código tras el desarrollo:**
  1. Guardar los z_NW de todas las miradas aun después de confirmar (para la correlación descriptiva).
  2. Que la verificación no recalcule todas las confirmadas (costo).
  - **Ninguno toca la regla de decisión.**

## 7. Alcance: qué NO calibra esta corrida
- **n_max fuera de [1096, 1826]:** PEC-1.1 lo prohíbe sin una calibración nueva.
- **Faltantes que desplacen las miradas más de lo previsto:** PEC-1.1 omite la mirada, lo que es conservador. La
  tolerancia del ±10 % no se calibra.
- **Futilidad vinculante:** no hace falta, porque solo puede bajar el error.
- **Datos reales, costos, supervivencia o rentabilidad.**
