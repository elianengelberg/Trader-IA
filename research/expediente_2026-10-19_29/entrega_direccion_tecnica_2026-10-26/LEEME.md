# Entrega · misión de dirección técnica y cuantitativa · 2026-10-26

**NO AUTORIZADO PARA OPERAR CON DINERO REAL.**
- Nada de esto se integró al repositorio.
- No hubo commits, push, PR ni conexión a exchanges o a Testnet.
- La ejecución confirmatoria de E3 **no** se corrió: espera tu autorización.

## Por dónde empezar

| Archivo | Para qué |
|---|---|
| `INFORME_DIRECCION_TECNICA.md` | El informe, en los 10 puntos pedidos, más el contraste de los antecedentes y la autocrítica |
| `E3R/PLAN_EJECUCION_UNICA_E3R.md` | El experimento recomendado: qué decide cada resultado, el diseño, las dos ventanas posibles y la **autorización exacta** |
| `PROPUESTAS_TECNICAS.md` | El registro P01–P35. Las P01–P25 vienen del ciclo 1, con los cambios de estado marcados; las P26–P35 son de este ciclo |
| `parches/CADENA_DT.txt` | Los parches 23–25: sha256, árbol antes y después, archivos y líneas |
| `reproducir_DT.sh` | Reconstruye el árbol final T25 desde el repositorio de origen, solo con este paquete |
| `VERIFICACION_FINAL.txt` | Repositorio protegido, E3 congelado intacto, CI local, procesos residuales y limpieza del paquete |
| `MANIFEST.sha256` | sha256 de todos los archivos del paquete |

## Contenido

- **`parches/`:**
  - `base_01_15/` y `ciclo_TI/` (16–22): idénticos byte a byte a la entrega del 2026-10-25;
  - `ciclo_DT/` (23–25): este ciclo.
- **`registro/`:** el árbol esperado después de cada paso (`T07`…`T25`).
- **`E3R/`:** el desbloqueo de E3-H1.
  - Adendas R, R1′ y R2, con su hora de congelación.
  - Scripts y resultados de P0. Solo leen vectores de estado y listas estructurales: **ningún retorno**.
  - El orquestador congelado (`ejecutar_E3R.py`, `3b64a04d…`), con sus pruebas y resultados sintéticos.
  - El orquestador busca el código congelado de E3 en `../E3_seleccion_posicion_2026-10-19/ejecucion_E3`. Fuera del entorno original, el modo real recibe esa ruta como argumento.
- **`evidencia/`:**
  - `sin_y_con_correccion/`: cada defecto (P26, P27, P28), con su prueba corrida sin el arreglo (falla) y con él (pasa);
  - `sondas/`: tenencia ajena y polvo;
  - `arbol_candidato/`: armado de la cadena 01–25 en un clon nuevo;
  - `ci_local/`: los dos jobs de la CI sobre T25 (python y PostgreSQL).
    - El encabezado del job PG muestra otro árbol (`c00a8318…`) porque cuenta el directorio `ci-evidence/` que dejó el job python en el mismo clon.
    - La procedencia de la compuerta registra `working tree 11f9ccca…` = T25.
- **`herramientas/`:** los scripts de esta misión, tal como se corrieron (con rutas absolutas del entorno de trabajo).

## Reproducir

```bash
bash reproducir_DT.sh /ruta/al/repositorio /ruta/nueva/clon [/ruta/a/python_con_dependencias]
```

- **Sin el tercer argumento:** verifica que cada parche aplique y que cada árbol intermedio coincida con `registro/`.
- **Con el tercer argumento:** corre además ruff y las pruebas de cada parche de los ciclos (16–25).
- **No escribe en el repositorio de origen:** compara el sha256 de su `.git/index` antes y después.
