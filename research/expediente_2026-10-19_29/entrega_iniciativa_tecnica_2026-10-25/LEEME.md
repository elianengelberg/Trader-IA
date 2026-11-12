# Entrega · ciclo de iniciativa técnica · 2026-10-25

**NO AUTORIZADO PARA OPERAR CON DINERO REAL.** Nada de esto se integró al repositorio. No hubo commits, push, PR ni conexión a exchanges.

## Por dónde empezar

| Archivo | Para qué |
|---|---|
| `INFORME_CICLO.md` | El informe de cierre, en los 9 puntos pedidos |
| `PROPUESTAS_TECNICAS.md` | El registro P01–P25: problema, evidencia, alternativas, decisión, validación y estado |
| `parches/CADENA_TI.txt` | Los parches 16–22: sha256, árbol antes y después, archivos y líneas |
| `reproducir_TI.sh` | Reconstruye el árbol final T22 desde el repositorio de origen, solo con este paquete |
| `VERIFICACION_FINAL.txt` | Estado del repositorio protegido, procesos residuales y limpieza del paquete |
| `MANIFEST.sha256` | sha256 de todos los archivos del paquete |

## Contenido

- `parches/base_01_15/`: los 13 parches de la cadena 01–15. Son **idénticos** byte a byte a los de la entrega anterior; el número inicial da el orden de aplicación.
- `parches/ciclo_TI/`: los parches de este ciclo.
  - 16: controles de emergencia;
  - 17: compuerta de evidencia;
  - 18: métricas;
  - 19: persistencia y alertas;
  - 20: pruebas de detección;
  - 21: *watchdog*;
  - 22: documentación del kill switch.
- `registro/`: el árbol esperado después de cada paso (`T07`…`T22`).
- `logs/sin_y_con_correccion/`: cada defecto, con su prueba corrida sin el arreglo (falla) y con él (pasa). Además, cada mutante contra la prueba que lo cubre.
- `logs/experimentos/`: kill switch y cierre rechazado (antes y después), falsos positivos y razón de costos de la regla de EV, contaminación sintética, y mutación (T15, T21 y lote 2).
- `logs/ci_local/`: los dos jobs de CI en T21: resumen, ruff, compuerta, `junit.xml` y procedencia. Las corridas interrumpidas (árboles que cambiaron después) se conservan solo con su resumen.
- `logs/simulacion/`: la simulación integral sobre T21 (semillas 7 y 8) y la re-corrida de T15 que explica la diferencia de E12 (P23). Incluye los JSON y los veredictos; los registros completos de *logging* no se incluyen.
- `logs/arbol_candidato/`: armado del candidato en un clon nuevo, con ruff y las pruebas de cada parche.
- `herramientas/`: los scripts de los experimentos, tal como se corrieron. Tienen rutas absolutas del entorno de trabajo; para reconstruir el candidato en otro lado se usa `reproducir_TI.sh`, que no depende de ellas.

## Reproducir

```bash
bash reproducir_TI.sh /ruta/al/repositorio /ruta/nueva/clon [/ruta/a/python_con_dependencias]
```

El script clona el repositorio de origen (solo lectura), aplica 01–15 y 16–22, compara cada árbol intermedio, corre ruff y las pruebas de cada parche del ciclo (si le pasás un intérprete), y comprueba que el `.git/index` del origen no cambie.
