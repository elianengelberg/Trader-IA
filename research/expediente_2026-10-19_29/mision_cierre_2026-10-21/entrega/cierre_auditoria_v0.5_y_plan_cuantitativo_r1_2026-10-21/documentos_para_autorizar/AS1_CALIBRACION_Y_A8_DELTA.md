# A-S1 (calibración) y A8 / D-S4 (δ)

## Parte 1. A-S1: calibración sintética de la prueba primaria

**Qué autorizarías.** Una sola ejecución de:
```
python3 -B protocolo_cuantitativo/calibracion/calibracion_mec.py --ejecutar --autorizacion "<tu referencia>" --salida <archivo>
```
- Parámetros congelados en `calibracion/parametros_calibracion.json`, SHA-256
  `28764d31b62028f2dd095c35449cd43fccb4c970ae6e00fdf118c744c1efc425`. Son los del MEC v0.2 §5:
  - procesos C1–C6;
  - n ∈ {1612, 366, 731, 1096};
  - 2000 réplicas y B = 1999;
  - semilla 20261103;
  - bandas [1,80 %, 3,20 %] al 2,5 % y [4,03 %, 5,97 %] al 5 %.
- **Solo datos sintéticos.** No toca T, ni el repositorio, ni datos de mercado.
- **Costo medido** con `--plan` (`evidencia/F4_calibracion_plan.txt`): unos 0,1 s por réplica.
  - ≈ 1,3 h de CPU para la prueba primaria;
  - ≈ 3,9 h si también se calibra la regla de respaldo.
- **Hoy no se ejecutó.**
  - El script se niega sin `--autorizacion` (probado: `test_calibracion_bloqueada_sin_autorizacion_y_humo`).
  - Solo se corrió una prueba de humo: 2 réplicas, sin informar ninguna tasa.

**Decisiones técnicas tomadas ANTES de cualquier resultado** (categoría B, `02_EXPEDIENTE_DECISIONES.md`). Son las
recomendaciones del expediente, adoptadas para hipótesis **futuras**, no para T:

| ID | Decisión |
|---|---|
| D-S1 | Prueba primaria: bootstrap-t por bloques circulares, centrado bajo H₀, con ℓ = 20 y B = 9999 |
| D-S2 | Multiplicidad: Bonferroni, α_familia/m por hipótesis, con la familia declarada de antemano |
| D-S3 | Regla de respaldo: p = máx(p_ℓ20, p_ℓ40, p_NW). Se usa solo si la calibración muestra sobre-rechazo, y también debe calibrarse |

**Qué pasa según el resultado:**

| Resultado | Consecuencia |
|---|---|
| La prueba primaria cumple todas las bandas | Se usa tal cual |
| Falla en algún proceso pertinente, pero la regla de respaldo cumple | Se usa la regla de respaldo, declarada en cada prerregistro |
| Fallan las dos | **El método no está validado.** Ninguna evaluación confirmatoria puede usarlo. Se rediseña como versión nueva y se recalibra con semillas nuevas |

**Riesgo de sobreajuste y cómo se evita:**
- elegir ℓ, B, el método o la regla mirando las tasas de esta calibración sería **seleccionar sobre la propia
  calibración**;
- por eso todo queda fijado por hash antes de ejecutarla;
- cualquier cambio posterior es una versión nueva y se recalibra con otra semilla;
- nada se ajusta nunca con datos reales.

**Recomendación: autorizar A-S1.** Es la única forma de que el marco estadístico deje de ser «propuesto, no
validado», y no tiene riesgo para los datos ni para T.

## Parte 2. A8 / D-S4: δ, el efecto mínimo económicamente relevante
**Qué es δ:** el exceso neto anual frente al benchmark de exposición equivalente por debajo del cual una ventaja **no
vale la pena**. Tiene tres usos:
1. habilita la categoría EFECTO_RELEVANTE_DESCARTADO (IC90 superior < δ);
2. fija n_max y la futilidad de la fase prospectiva;
3. define la potencia.

**Sin δ** el sistema ya se protege (probado):
- la fase prospectiva no puede congelarse (error del prerregistro);
- una mirada prospectiva falla;
- un resultado histórico «no respaldado» solo puede ser INSUFICIENTE o EN_CONTRA, nunca «efecto descartado».

**No lo elijo:** es una decisión económica (tu costo de oportunidad y tu tolerancia al riesgo), y elegirlo para
desbloquear algo sería exactamente lo que no hay que hacer.

**Criterios para fijarlo, todos económicos y ANTES de mirar datos nuevos:**
1. **Costo de oportunidad y prima por riesgo de modelo:** ¿cuánto exceso anual neto exigirías para tolerar el riesgo de
   que la regla deje de funcionar sin aviso?
2. **Costos fijos del programa:** δ ≥ (costo anual de operarlo, en tiempo e infraestructura) / capital previsto, más un
   margen.
3. **Incertidumbre de costos:** los costos de ejecución son supuestos. δ debería superar la pérdida de exceso del
   escenario de costos ×2.
4. **Detectabilidad.** No sirve para elegir δ, pero dice si el programa es viable. Con un desvío anual del exceso TE,
   confirmar δ en H años exige δ ≥ 2,80·TE/√H. Ver la tabla siguiente.

**Años de datos para potencia del 80 % con α = 0,025.**
- Una sola mirada. Con 5 miradas O'Brien–Fleming hay que multiplicar por R ≈ 1,025.
- Cálculo: `pec.potencia.anos_necesarios`; reproducido en `evidencia/F5_criba_candidatas.txt`.

| δ \ TE | 10 % | 15 % | 20 % | 30 % |
|---|---|---|---|---|
| 3 % | 87 | 196 | 349 | 785 |
| 5 % | 31 | 71 | 126 | 283 |
| 7 % | 16 | 36 | 64 | 144 |
| 10 % | 7,8 | 17,7 | 31,4 | 70,6 |
| 15 % | 3,5 | 7,8 | 14,0 | 31,4 |
| 20 % | 2,0 | 4,4 | 7,8 | 17,7 |

**Lectura:** con el TE de T (≈ 20 %) ningún δ menor que ≈ 15 % se confirma en menos de 14 años. Un programa
prospectivo útil necesita hipótesis con un TE bajo para el exceso esperado, es decir, una **razón de información alta**
(05_PLAN_CUANTITATIVO.md §5). No se resuelve eligiendo un δ grande.

**Recomendación de procedimiento:**
- fijá **un δ único para el programa**, con el criterio 1 o 2;
- registralo con fecha;
- desde ese momento entra congelado en cada prerregistro.

Si preferís un δ por hipótesis, debe fijarse antes de su prerregistro y nunca después de ver datos.
