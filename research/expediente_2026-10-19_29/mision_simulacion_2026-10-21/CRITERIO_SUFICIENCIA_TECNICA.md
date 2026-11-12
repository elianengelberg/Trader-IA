# Criterio de suficiencia técnica (MS-2)

Fijado **antes** de simular con datos nuevos. Si todo se cumple, se deja de perfeccionar y se simula. Si algo falla, se corrige primero.

No es «perfecto»: es lo necesario para que un resultado, favorable o no, no pueda deberse a un error de cálculo conocido.

| # | Requisito | Evidencia | Estado |
|---|---|---|---|
| C1 | D1–D3 corregidos en `tia/backtest/engine.py` (y en `paper.py` el auxiliar `resting_orders`), con una prueba por defecto que **falla con el motor original y pasa con el corregido** | `evidencia/S1b_regresion_v2_contra_motor_original.txt` (4 fallan, cada una por su defecto); `S1b_regresion_v2_motor_corregido.txt` (4 pasan) | **Cumple** |
| C2 | Sin regresiones: la suite de CI completa, igual que en la línea base | Línea base HEAD 72ffae5: 1956 pasan (`S0_linea_base_HEAD.txt`). Corregido: 1960 pasan, las 1956 más las 4 nuevas (`S1_suite_corregida.txt`). ruff limpio (`S1_ruff.txt`). mypy: los mismos 14 errores de tipado preexistentes, ninguno nuevo (`S1_mypy_motor.txt`) | **Cumple** |
| C3 | Paridad: el motor corregido del paquete reproduce **exactamente** las operaciones registradas de E1, con los mismos datos verificados, configuración y escenario | `S2_paridad_e1_principales.json`: P1 629/629, P2 139/139, P3 185/185 y S1 795/795, con JSON idéntico byte a byte. 0 salidas terminadas con posición restante; 0 barras sin stop | **Cumple** |
| C4 | Sin look-ahead: invariancia de prefijo y perturbación del futuro, con el motor corregido (datos sintéticos de E1) | `S2_verificacion_sintetica_motor_corregido.json`: V2 y V3 idénticos en las 4 configuraciones (P1, P2, P3, S1), con más de 100 decisiones antes del corte | **Cumple** |
| C5 | Robustez de órdenes: rechazos (V1) y parciales al 90 % (V6) sin piernas trabadas ni sin stop | V1 (rechazo 1 %): máx. 1 barra seguida sin stop activo; 0 barras con el stop a otro nivel. V6 (parciales 90 %, 8000 velas): round trip máx. de 45 y 68 barras, entradas hasta el final, 0 salidas terminadas con posición restante. Con el motor original, V6 daba 2 round trips de ≈ 7700 barras (E1) | **Cumple** |
| C6 | Determinismo: la misma corrida en dos procesos da la misma huella | DET: misma huella entre procesos (`2ec41ec6…`). La repetición de P3 en DEV-ETH real se verifica en la validez de SIM-1 | **Cumple** (sintético) |
| C7 | Datos auténticos con procedencia: checksums oficiales y calidad sin incoherencias | `registro/verificacion_checksum.txt`: 132/132. `resultados/calidad_datos.json`: 0 OHLC incoherentes, 0 precios ≤ 0; huecos y conflictos enumerados | **Cumple** |
| C8 | Falla segura: ante un estado dudoso, detenerse o advertir; nunca informar como si nada | Ver la lista de abajo | **Cumple** |

## C8 en concreto
- **Datos:** `leer_velas` se detiene si un ZIP no coincide con su `.CHECKSUM`. No rellena horas; los conflictos pasan a faltantes.
- **Motor:**
  - advierte si quedan posiciones abiertas al final;
  - advierte de las barras con posición sin nivel de stop (advertencia nueva, con `bars_with_leg_and_no_stop`);
  - `is_reliable()` es falso si hay advertencias o pocas operaciones;
  - los contadores `order_hygiene` registran cada intervención de D3.
- **Script `sim1.py`:**
  - se niega a escribir en un directorio con contenido;
  - si la validez falla, se detiene **antes** de analizar;
  - la lectura de OOS queda protegida por un candado de creación exclusiva: una segunda lectura lanza `FileExistsError`. Esto se probó en el ensayo sintético.

## Fuera del alcance (declarado, no «perfeccionado»)
- **Funding:** las estrategias operan **spot**, sin apalancamiento ni perpetuos, así que no hay funding que modelar. Si alguna vez se operan perpetuos, hace falta el modelo de funding de H-CARRY.
- **Diferencial:** se modela como 2 bps de deslizamiento base por pata, más el componente de rango de la vela, más un impacto de 0,35. No hay libro de órdenes histórico.
- **Latencia:** ejecución a la apertura siguiente; S3 agrega una vela más.
- **Filtros de ETHUSDT:** inferidos y supuestos (ver el prerregistro §3). La API de Binance no es accesible desde aquí (`registro/INCIDENTE_01_*`).
- El motor procesa **un símbolo por corrida**. La cartera multiactivo no se simula como una cuenta conjunta.

## Veredicto
**Suficiente** para simular: C1–C8 se cumplen.
- El ensayo funcional de `sim1.py` con datos sintéticos (`ensayo_sintetico/`) recorrió DEV, la regla de M1, la decisión OOS y el candado sin errores.
- Desde aquí no se agrega infraestructura salvo que DEV muestre un defecto concreto.
