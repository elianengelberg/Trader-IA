# Plantillas PEC-1.0: tarjeta de hipótesis (entrada) y prerregistro (congelado)

## A. Tarjeta de hipótesis (una página; se llena ANTES de mirar cualquier dato)
| Campo | Qué escribir | Regla |
|---|---|---|
| Identificador | `H-…` | Nuevo; si se parece a una del registro del programa, declarar la relación |
| Mecanismo económico | Quién pierde dinero frente a la estrategia y por qué lo acepta | Sin mecanismo plausible no hay tarjeta |
| Por qué no estaría arbitrada | Límite al arbitraje: capital, riesgo de cola, costo, regulación, atención | — |
| Familia y antecedentes | Familia del registro del programa; ¿reabre una descartada? | Reabrir exige D-G5 |
| Universo y frecuencia | Activos, mercado, exchange, frecuencia | Más de un activo obliga a declarar la supervivencia |
| IR neto plausible | Valor y **fundamento sin datos**: literatura citada, aritmética del mecanismo o costos | Es la entrada de la criba |
| Horizonte | Años disponibles para la confirmación prospectiva | — |
| **Criba** | `pec.potencia.criba_detectabilidad(IR, horizonte, R)` | NO_DETECTABLE: no se inicia, o se acepta «no concluyente» por escrito |
| Costo experimental | Datos (B-4), implementación, horas de cálculo, meses de fase prospectiva | — |
| Decisión | Iniciar el prerregistro / descartar / posponer | Registrada en el registro del programa |

## B. Prerregistro
- Es un documento JSON que valida `esquemas/prerregistro_v1.schema.json` **y** `pec.prerregistro.validar_semantica`.
- Ejemplo completo y sintético: `ejemplo_prerregistro_SINTETICO.json`.
- **Bloques obligatorios:**
  - hipótesis (mecanismo, H₀: μ ≤ 0, H₁: μ > 0);
  - familia;
  - universo (con supervivencia);
  - datos (fuente, licencia, manifiesto, UTC, faltantes, umbral, velas incompletas, duplicados);
  - reglas (señal, entrada, salida, gestión del riesgo y **una sola** configuración de parámetros);
  - ejecución (apertura siguiente, comisión, slippage, spread, latencia, funding, apalancamiento, margen de mantenimiento);
  - ventanas (desarrollo < validación < prueba final, o una fase prospectiva desde 2026-10-14 con sus miradas y n_max);
  - métrica primaria (exceso diario frente a la exposición equivalente);
  - al menos tres benchmarks;
  - prueba (bootstrap-t, ℓ, B, semilla, regla de respaldo, α);
  - multiplicidad (familia, Bonferroni);
  - potencia (δ, TE supuesto, IR plausible, horizonte, N_min ≥ 30, aceptación de «no concluyente»);
  - criterios (MEC §7);
  - robustez;
  - reproducción (REPRODUCIDO por otra persona, determinista, todas las reproducciones);
  - parada (cero variantes).
- **Congelar:**
  - `pec.prerregistro.congelar(doc, fecha_utc)` agrega el SHA-256 del contenido;
  - el hash se sella fuera (O5) y su cabeza se registra en O2 (cuando existan, R-5);
  - un cambio posterior es una hipótesis **nueva**.
