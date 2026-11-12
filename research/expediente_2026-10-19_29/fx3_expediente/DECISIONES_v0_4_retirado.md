# Decisiones que siguen siendo tuyas (v0.4)

No decidí ninguna. El código las mantiene **explícitamente sin definir**:
- los registros están vacíos;
- los estados son NO_DEFINIDO o NO_DEFINIDA;
- no hay ningún valor por defecto que apruebe algo;
- ninguna función pública acepta inyectarlas.

Cada fila dice cómo se comporta hoy el código y qué cambia cuando decidas.

## A. Metodológicas
| ID | Decisión | Estado en el código hoy | Alternativas y consecuencias |
|---|---|---|---|
| A1 / A2 | Definición de R1 y R3 **para T** | `DEFINICIONES_APROBADAS = {}`. R1 y R3 solo pueden ser `NO_DEFINIDO`; una evaluación CUMPLE o NO_CUMPLE es un error | (a) dejarlas sin definir: no hay diagnóstico de robustez. (b) «> 0»: control de signo débil (P ≈ 0,50 sin ventaja). (c) «> δ»: depende de A8. (d) cota inferior del intervalo > 0: muy exigente. Cualquier definición es **post hoc** para 2022–2026, y la política lo marca |
| A3 | ¿R1 o R3 pueden vetar la candidatura? | No: la robustez es un diagnóstico; solo genera una advertencia | Con veto, un diagnóstico débil podría bloquear una ventaja |
| A4 / A7 | Uso de definiciones posteriores a la ventana | Se permiten y se marcan `post_hoc` (fecha de aprobación ≥ inicio de la ventana) | Prohibirlas convertiría la evaluación en un error de entrada |
| **A5** | **Qué es la «etapa siguiente» de T** | `ETAPAS_DEFINIDAS = {}`. Toda decisión dice «etapa NO_DEFINIDA»; nombrar una etapa es un error | Sin etapa, ninguna autorización puede ser coherente |
| A6 | Regla de combinación de R1 y R3 | «Todas» (de E3): ROBUSTA solo si ambas se cumplen | «Alguna» o ponderaciones (la mutación «alguna» está probada y el oráculo la detecta) |
| **A8** | **Efecto mínimo relevante δ, pérdida máxima tolerable y definición económica de robustez** | Ningún umbral económico en el código (prueba estática: las únicas constantes numéricas son 0, 12 y 64) | Condiciona A1, A2 y la duración del papel |
| A9 | ¿VERIFICADO alcanza, o se exige REPRODUCIDO? | Ambos cuentan como válidos (`VALIDA`) | Exigir REPRODUCIDO implica una reproducción independiente. Para el T histórico eso es recalcular, y **no se hace** |
| A10 | `reintentos_tras_inicio` y `verificar_determinismo` para usos reales de P4 | Por defecto 0 y falso (la reserva los fija) | Recomendación técnica: 0 y verdadero. Con 0, toda interrupción del cálculo va a revisión humana; verdadero duplica el costo |
| A11 | Reabrir hipótesis descartadas | No se tocó | — |
| **A12 (nueva)** | **¿Basta tu firma de los artefactos históricos de T como referencia independiente?** | Sin raíz aprobada, el resultado real es INCONCLUSO | Firmar dice «acepto estos artefactos» en la fecha de la firma; **no** prueba que no cambiaran antes. La cronología solo consta en commits locales sin publicar y en la transcripción local (`trazabilidad_T/`). Si no basta, T queda INCONCLUSO para siempre (no se repite) |

## B. Acciones operativas bloqueadas (no se ejecutaron)
| ID | Acción | Qué la desbloquea |
|---|---|---|
| B-1 | Commits, push, aplicar los parches de `parches/v0.4/` al repositorio, versionar `corte.py` | Tu autorización. Los parches aplican limpio en HEAD y en origin y su suite pasa en ambas copias (`evidencia/60_*`, `61_*`) |
| B-2 | Elegir o implementar el ancla externa; crear y custodiar claves; aprobar raíces en `RAICES_CONFIANZA`; publicar hashes o commits (`f518ac1`, `692f2b2`) | Tu autorización y una clave **fuera** de este equipo (`DISENO_ANCLA_EXTERNA.md`, `trazabilidad_T/INSTRUCCIONES_FIRMA.md`) |
| B-3 | Integrar P4 en `papel/corte.py` u otro ejecutor | Tu autorización, después de B-2 |
| B-4 | Leer los bytes de los datos reales (`--datos`) o reproducir `calidad_datos.json` | Tu autorización |
| B-5 | Calibración estadística pendiente (v0.2 del expediente) | Tu autorización |
| B-6 | Backtests, evaluaciones históricas, descargas, repetir T, dinero real, despliegues | Prohibidas |
| B-7 | Revisión por un tercero | Pendiente: todo lo hizo el mismo agente |
| B-8 | Conservar este paquete fuera del scratchpad efímero | Tuya: descargar el ZIP |
