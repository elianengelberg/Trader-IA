# 01 — Nota previa a la ejecución de A-S1

Escrita y fijada por SHA-256 **antes de calcular ninguna réplica con la semilla congelada** (20261103). Todo lo que
aquí se decide queda fijado sin conocer ninguna tasa de rechazo.

## 1. Qué se ejecuta
**Código:** el del paquete r1 (`a8056ced…`), extraído de nuevo en `codigo_r1/`.
- `sha256sum -c`: 80 archivos OK.
- `calibracion_mec.py`: `80d35957…`.
- Parámetros: `28764d31b62028f2dd095c35449cd43fccb4c970ae6e00fdf118c744c1efc425`, sin cambios. Son 6 procesos (C1–C6),
  n ∈ {1612, 366, 731, 1096}, 2000 réplicas, B = 1999 y semilla 20261103.
- `pec/inferencia.py`: `99d0d3e6…`.
- `pec/sintetico.py`: `7b15c677…`.

**Modo de ejecución.** El script congelado es secuencial: unas 5 h en un solo núcleo. La máquina tiene 4 núcleos y el
contenedor es efímero. Por eso se usa `orquestador/orquestar_calibracion.py` (`3d48c386…`):
- no reimplementa nada: llama a la función `_replica` del script congelado, con los mismos argumentos que usa su
  `main()`;
- reparte las réplicas en 4 procesos;
- al terminar ejecuta **el propio `main()` congelado**, con `--ejecutar --autorizacion … --salida …`. Ese `main()`
  agrega, aplica el criterio y escribe el resultado;
- es reanudable por celda (las réplicas son deterministas) y nunca sobrescribe la salida.

**Equivalencia comprobada antes, sin usar la semilla congelada:**
- **Secuencial frente a paralelo:** 96 réplicas (semilla 1, B = 199) idénticas (`registro/equivalencia_previa.json`).
- **De extremo a extremo, en una copia de prueba con parámetros reducidos** (20 réplicas, B = 99, semilla 1, n ∈ {80, 160}):
  - la salida del orquestador es **idéntica byte a byte** a la del script original ejecutado de forma secuencial
    (`911beb8f…`);
  - también es idéntica tras borrar una celda y reanudar;
  - el orquestador se niega a sobrescribir la salida.
- **Prueba negativa del verificador:** un valor p alterado se detecta.

**Una sola ejecución.** Si el contenedor interrumpe la corrida, se **reanuda** desde las celdas guardadas, no se repite:
las réplicas son deterministas, así que reanudar no permite elegir resultados.

## 2. Criterio vinculante (el congelado, sin cambios)
Es el del MEC v0.2 §5, el del script y el de A-S1.
- **Comprobación:** para cada regla, proceso (los 6, todos pertinentes: el MEC §5 los define como el conjunto de
  calibración) y tamaño, la tasa de rechazo al 2,5 % debe ser ≤ 3,20 % y al 5 % ≤ 5,97 %. Son **48 comprobaciones por
  regla**.
- **Rechazo:** se rechaza cuando p ≤ α.
- **Réplicas degeneradas:** cuentan como no rechazo (p = 1), como hace el script, y se informan.
- **Sub-rechazo:** se acepta y se informa.

**Decisión** (tabla de A-S1):
1. Si la primaria cumple las 48 comprobaciones, se usa tal cual.
2. Si no, pero la regla de respaldo cumple las 48, se usa la regla de respaldo.
3. Si ninguna cumple, **el método no está validado**.

## 3. Limitación conocida del criterio, declarada ANTES de ver resultados
`orquestador/multiplicidad_previa.py` (`8a615b7c…`) hace un cálculo exacto, sin réplicas, que está en
`registro/multiplicidad_previa.json`. Supone una prueba con tamaño **exactamente** nominal y celdas independientes:
- cada celda incumple por puro error de Monte Carlo con probabilidad 3,94 %;
- con 24 celdas por regla, **una regla perfecta incumple el criterio congelado con probabilidad ≈ 61,9 %**.

Es un defecto de diseño del MEC v0.2 §5. Lo escribió el mismo autor que esta nota, en una sesión anterior, y no lo
detectó. Consecuencias:
- **No cambia el criterio vinculante.** Cambiarlo es una decisión metodológica del propietario y, según A-S1, cualquier
  cambio es una versión nueva que se recalibra con otra semilla.
- La regla de respaldo usa el mismo bootstrap-t ℓ = 20 con la misma semilla como uno de sus tres componentes. Por eso
  rechaza un subconjunto de lo que rechaza la primaria. Esto se verifica réplica a réplica.

**Lectura descriptiva NO vinculante**, fijada ahora en `orquestador/verificar_calibracion.py` (`0b0c4ac7…`). Por cada
comprobación se calcula:
- la prueba binomial exacta de sobre-rechazo, P(Bin(2000, α) ≥ k);
- Holm al 5 % dentro de las 48 comprobaciones de cada regla;
- el intervalo de Wilson al 95 %.

Su único uso es mostrar al propietario si un incumplimiento es compatible con ruido de Monte Carlo. No cambia la
decisión.

## 4. Verificación posterior (fijada ahora)
`verificar_calibracion.py`:
- recuenta desde los valores p crudos y lo compara con la salida del `main()` congelado;
- comprueba que p_respaldo ≥ p_primaria y que las réplicas degeneradas coinciden;
- recalcula en un proceso nuevo 2 réplicas por celda, elegidas con `random.Random(20261021)` (96 réplicas), y exige
  igualdad exacta;
- comprueba la huella de los parámetros y de la salida.

## 5. Qué NO se hace
- **No se informa la potencia** (MEC §5): requiere δ, y A8 sigue pendiente.
- No se cambia ningún parámetro, umbral ni regla después de esta nota.
- No se usan datos reales.
- No se toca el repositorio ni el paquete r1: la salida va a un paquete nuevo.

## 6. Observaciones menores halladas al preparar
Son solo documentales y no afectan al cálculo:
- **N-6:** el docstring de `sintetico.proceso` aún dice «centradas exactamente (media muestral 0)». El código, corregido
  en N-3, **no** centra la serie, y su comentario lo explica.
- **N-7:** A-S1 estimaba ≈ 1,3 h / 3,9 h (≈ 0,1 s por réplica). `F4` midió 0,157 s por réplica con n máximo: 2,09 h /
  6,27 h como cota superior en un solo núcleo.
