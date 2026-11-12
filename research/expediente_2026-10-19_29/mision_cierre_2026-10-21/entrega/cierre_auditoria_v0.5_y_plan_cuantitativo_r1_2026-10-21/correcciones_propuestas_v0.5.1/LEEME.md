# Correcciones propuestas para el arnés de verificación de v0.5 (v0.5.1, NO aplicadas)

**v0.5 no se reconstruyó ni se sobrescribe.** Su ZIP (`5bf9bc5d…`) y su evidencia quedan como están.

**Por qué no se reconstruye:** los dos defectos son del **arnés de pruebas**, no del código de P1, P2, P4 ni del
ejecutor. Ninguno altera un resultado.
- **D-1:** la ejecución real B de v0.5 no creó enlaces ni directorios inesperados (`evidencia/B8_*`).
- **D-2:** solo deja temporales fuera del paquete y del repositorio.

Las correcciones se aplican en la próxima versión del arnés que se apruebe.

| Parche | Defecto | Archivos | Prueba antes y después |
|---|---|---|---|
| `0001-etapa13-enlaces-y-directorios.patch` | **D-1:** la etapa 13 no detecta enlaces simbólicos nuevos, directorios vacíos nuevos ni un archivo reemplazado por un enlace | `ejecutar_todo.sh` (`original/` = v0.5, `corregido/`) | `probar_etapa13.sh`, 12 escenarios en copias nuevas: antes, 3 diferencias; después, 0. Sin falsos positivos sobre la ejecución real B; detecta el `__pycache__` real de la ejecución A (`evidencia/B4_*`) |
| `0002-temporales-de-pruebas-y-sondas.patch` | **D-2:** las sondas y el adaptador de pruebas dejan directorios temporales en TMPDIR | `pruebas/sondas_v0_4/ejecutar_sondas.sh`, `pruebas/comun/adaptador.py` | Con TMPDIR nuevos: sondas de 19 a 0 restos; P1 de 11 a 0. La salida 71 es idéntica (`evidencia/D2_*`) |

**Lo que NO corrige** (documentado en `01_RESULTADOS_AUDITORIA.md`):
- un `calculo_*` vacío puede quedar en TMPDIR si el padre y el hijo de P4 mueren a la vez, por ejemplo con SIGKILL al
  grupo: ningún proceso muerto puede limpiar;
- la etapa 13 no detecta, a propósito:
  - un cambio de permisos;
  - un archivo nuevo dentro de `evidencia/`;
  - una reescritura coherente del propio manifiesto, que solo detecta el SHA-256 del ZIP verificado contra una
    referencia externa.
