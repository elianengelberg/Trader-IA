# 03 — Calibración del diseño secuencial completo (SEC-1.0): error global de las 5 miradas

**Veredicto vinculante: APTO.** En las **18 celdas** H₀ (C1–C6 × n_max ∈ {1096, 1461, 1826}), la cota superior exacta de
Clopper–Pearson del error global, con confianza conjunta del 95 % (Bonferroni), es **≤ 2,70 %**. El umbral prerregistrado
era 3,0 %.

**El procedimiento** es el de PEC-1.1:
- regla p = máx(p_ℓ20, p_ℓ40, p_NW);
- B = 9999, con la misma semilla en las 5 miradas;
- fronteras Lan–DeMets tipo O'Brien–Fleming, α = 0,025.

Con ese procedimiento, **el error global de las cinco miradas está controlado** en esos procesos y tamaños.

Solo datos sintéticos. **No dice nada sobre la rentabilidad** de ninguna estrategia.

## 1. Qué se ejecutó
- **Especificación:** `codigo/f3/especificacion_CONFIRMATORIA.json`, `b4064e8c…`.
- **Nota previa:** `registro/F3_NOTA_PREVIA_SECUENCIAL.md`, `8a65f0ec…`.
- **Simulador:** `daa34125…`. **Análisis:** `d7afe09a…`.
- **Fijados por SHA-256 a las 17:19:23 UTC** (`registro/f3_huellas_previas.txt`).
  - Todos se volvieron a comprobar OK después de ejecutar.
  - El orden temporal consta solo en registros locales, sin ancla externa.
- **Una sola ejecución:** de 17:19:30 a 18:57:07 UTC, 4 procesos, 24 celdas, **sin reanudaciones**
  (`f3_confirmatoria/ejecuciones.jsonl`).
  - Corrió en paralelo con la reejecución de A-S1. Eso solo afecta los tiempos, no los resultados, que son
    deterministas.
- **Semillas:** 20261105·10⁶ + r (H₀) y 20261106·10⁶ + r (H₁). Son disjuntas de las de A-S1 (20261103 + r) y de las de
  desarrollo (20261104·10⁶ + r).
- **Código r1 sin cambios:** `pec/inferencia.py` `99d0d3e6…`, `pec/sintetico.py` `7b15c677…`, `pec/secuencial.py`
  `90f3a4c2…`. Comprobados contra `SHA256SUMS.txt` de r1 antes de importarlos.
- **Fase de desarrollo:** semilla 20261104, 100 trayectorias por celda. Solo se usó para el código y el costo; su
  veredicto (R = 100) no tiene significado y no se usó.

## 2. Resultado H₀ (vinculante)
Columnas por mirada: 1 / 2 / 3 / 4 / 5. El gasto teórico × 36 000 es 0,02 / 14,1 / 123,4 / 302,5 / 460,0.

| Proceso | n_max | Confirmadas de 36 000 | α̂ global | Cota sup. CP (99,72 %) | ≤ 3 % | Por mirada |
|---|---|---|---|---|---|---|
| C1 | 1096 | 835 | 2,319 % | 2,548 % | sí | 0 / 9 / 97 / 299 / 430 |
| C1 | 1461 | 864 | 2,400 % | 2,632 % | sí | 0 / 5 / 102 / 300 / 457 |
| C1 | 1826 | 837 | 2,325 % | 2,554 % | sí | 0 / 7 / 103 / 300 / 427 |
| C2 | 1096 | 858 | 2,383 % | 2,615 % | sí | 0 / 5 / 99 / 298 / 456 |
| C2 | 1461 | 847 | 2,353 % | 2,583 % | sí | 0 / 6 / 103 / 296 / 442 |
| C2 | 1826 | 887 | 2,464 % | **2,699 %** | sí | 0 / 7 / 103 / 298 / 479 |
| C3 | 1096 | 846 | 2,350 % | 2,580 % | sí | 0 / 6 / 88 / 303 / 449 |
| C3 | 1461 | 878 | 2,439 % | 2,673 % | sí | 0 / 5 / 105 / 310 / 458 |
| C3 | 1826 | 868 | 2,411 % | 2,644 % | sí | 0 / 7 / 112 / 282 / 467 |
| C4 | 1096 | 264 | 0,733 % | 0,867 % | sí | 0 / 0 / 11 / 44 / 209 |
| C4 | 1461 | 324 | 0,900 % | 1,047 % | sí | 0 / 1 / 11 / 62 / 250 |
| C4 | 1826 | 349 | 0,969 % | 1,122 % | sí | 0 / 0 / 5 / 90 / 254 |
| C5 | 1096 | 809 | 2,247 % | 2,473 % | sí | 0 / 1 / 101 / 267 / 440 |
| C5 | 1461 | 803 | 2,231 % | 2,455 % | sí | 0 / 5 / 94 / 259 / 445 |
| C5 | 1826 | 868 | 2,411 % | 2,644 % | sí | 0 / 3 / 105 / 299 / 461 |
| C6 | 1096 | 855 | 2,375 % | 2,606 % | sí | 0 / 4 / 112 / 301 / 438 |
| C6 | 1461 | 859 | 2,386 % | 2,618 % | sí | 0 / 4 / 112 / 313 / 430 |
| C6 | 1826 | 867 | 2,408 % | 2,641 % | sí | 0 / 4 / 108 / 329 / 426 |

## 3. Lectura descriptiva (no cambia el veredicto)
- **Sin sobre-rechazo:**
  - todas las estimaciones puntuales están **por debajo de 2,5 %**;
  - fuera de C4, el agregado es 12 781 de 540 000 = **2,37 %**;
  - 13 de 18 celdas cumplen el criterio estricto de Bradley [2,25 %; 2,75 %]. Las otras 5 caen **por debajo**: C4 (las
    3) y C5 con n_max 1096 y 1461, en 2,25 % y 2,23 %.
- **C4 (disperso por eventos) es muy conservador:** 0,7–1,0 %. Ya lo era en A-S1, y la secuencia lo acentúa. Para una
  hipótesis tipo H-REV-SHOCK eso significa **pérdida de potencia**, no riesgo de falsos positivos.
- **Las miradas 1 y 2 no gastan lo previsto:**
  - **la 1 no puede confirmar nunca:** con B = 9999, p ≥ 10⁻⁴ y la frontera es ≈ 5·10⁻⁷;
  - **la 2 confirma 0–9 veces frente a 14 teóricas:** su umbral, 3,9·10⁻⁴, está cerca de la resolución del bootstrap.
  - Las miradas 3 a 5 se ajustan al gasto teórico.
  - Es parte de por qué el error queda por debajo del nominal.
- **El supuesto de incrementos independientes del MEC §7.1 se cumple bien en C1, C2, C3 y C5.** Comparando la
  correlación de z_NW entre miradas con √(t_j/t_k), en las 2000 primeras trayectorias de cada celda, la desviación es
  ≤ 0,05.
  - En C6 (cambio de régimen) y C4 (disperso) es menor de lo teórico, hasta 0,12. El error queda controlado igual.
- **Verificación:** 234 trayectorias recalculadas con `inferencia.respaldo` **completo**, sin cortocircuito (3 al azar y
  hasta 10 confirmadas por celda). **Todas confirman en la misma mirada.** Los umbrales almacenados coinciden con los
  recalculados.

## 4. Potencia bajo H₁ (descriptiva; R = 500)
Son los puntos de diseño de la criba de r1: la potencia del 80 % con la prueba z y 5 miradas.

| Proceso | n_max | IR | Potencia simulada | Wilson 95 % | Prueba z (analítica) |
|---|---|---|---|---|---|
| C1 (t₃) | 1096 | 1,64 | 75,0 % | 71,0–78,6 % | 80,1 % |
| C1 (t₃) | 1826 | 1,27 | 76,0 % | 72,1–79,5 % | 80,1 % |
| C2 (GARCH) | 1096 | 1,64 | 79,8 % | 76,1–83,1 % | 80,1 % |
| C2 (GARCH) | 1826 | 1,27 | 79,6 % | 75,8–82,9 % | 80,1 % |
| C5 (intradía) | 1096 | 1,64 | 77,4 % | 73,5–80,8 % | 80,1 % |
| C5 (intradía) | 1826 | 1,27 | 75,8 % | 71,9–79,3 % | 80,1 % |

**Lectura:** la regla decisiva cuesta entre 0 y 5 puntos de potencia frente a la aritmética de la prueba z. Con el n_max
de la fórmula, la potencia real es ≈ 75–80 %, no 80 %. PEC-1.1 lo declara y **no ajusta** n_max: hacerlo cambiaría el
diseño después de ver esta simulación, y la diferencia es chica.

## 5. Qué controla y qué no
| Cubierto (calibrado) | No cubierto (declarado en PEC-1.1) |
|---|---|
| 5 miradas equiespaciadas; prefijos anidados; misma semilla | n_max < 1096 o > 1826: exige una calibración nueva |
| Regla máx con B = 9999 y fronteras OBF | Miradas desplazadas por datos faltantes: se omiten, lo que es conservador. La tolerancia del 10 % no está calibrada |
| Procesos C1–C6 con media 0 (H₀) | Procesos fuera de C1–C6, como colas más pesadas o regímenes más largos |
| Futilidad no vinculante: el error medido es una cota superior | Datos reales, costos reales y supervivencia |

**Respuesta a la pregunta 5:** **sí**, el diseño secuencial controla el error global dentro del umbral prerregistrado:
≤ 3,0 % demostrado y ≤ 2,5 % estimado en todas las celdas. Vale para esos procesos, para n_max entre 1096 y 1826 y para
el procedimiento exacto descrito.
