# Cambios — H-CARRY Next

## 0.1.0 (2026-10-16): reconstrucción, laboratorio y ensayo sintético

Huellas de los experimentos registrados:
- ensayo v1 (`experimentos/sintetico_v1/`, 39 candidatos) y estrés: código `3e9073b5…677675b`, protocolo `7623b538…72959a8`;
- ensayo v2 (`experimentos/sintetico/`, 63 candidatos con `UmbralPrima`, variantes base y bajista suave): código `a1aeb5a5f4536414857736f13ff778e6d04b81079c5d80430c9b6b1dfd1b3479`, protocolo `10d33629cca50e5c19d173609d1ffca3e7739e863f4f30447459938b63a3de69`.

Todo el trabajo está en `research/hcarry_next/`, fuera del control de versiones. **No hubo commits, pushes ni despliegues.** No se cambió la rama activa, no se tocó producción ni ningún servicio y no hay modo live.

**Recuperación**
- `recuperado/`: los 9 archivos del ZIP de recuperación (`5783517c…`), en solo lectura con `SHA256SUMS`. Solo `prechequeo_exchangeinfo.py` está verificado contra un hash de referencia.

**Reconstrucción** (equivalencia comprobada contra las cifras documentadas de rev. 5)
- Cuentas, costes, funding, reequilibrio, liquidación del modelo, R0 y D1–D4.
- Reproduce exactamente el ejemplo de la plantilla rev. 5:
  - final 10 014,94;
  - CAGR 0,2022473335;
  - caída 0,001245;
  - distancia a la liquidación 0,985675.

**Mejoras** (ver `PROVENANCE.md` §3)
- Motor generalizado (ρ, escala, retraso, pata adversa, impacto) y conciliación independiente.
- Políticas alternativas y vista sin look-ahead.
- Métricas de capital comprometido.
- Laboratorio con prerregistro y test de uso único, bootstrap pareado y protocolo con líneas base propias y mundos nulos.
- Cargador de data.binance.vision y generador sintético.

**Defectos encontrados y corregidos durante el desarrollo**
- El generador sintético no emitía el evento de funding de la primera hora. El validador lo detectó (A2 «principio»).
- El régimen bajista sintético cobraba funding positivo casi siempre por la cota del interés. Se recalibró.
- El protocolo comparaba todo con la referencia ρ = 1 y atribuía al umbral mejoras del apalancamiento. Ahora cada candidato tiene su línea base propia.
- `rho_vol` podía bajar ρ por debajo de su base, lo que confundía apalancamiento con adaptación. Ahora ρ ≥ base.
- La conciliación acumulaba cantidades en coma flotante y fallaba con capitales de 10⁷–10⁸. Ahora cuenta lotes enteros, y la prueba de propiedades cubre esos capitales.
- Con estrés de retraso, una orden decidida antes de una liquidación se ejecutaba después; podía reabrir la posición durante el enfriamiento con un tamaño obsoleto. Ahora la liquidación cancela las órdenes pendientes. Hay una prueba de regresión que falla sin la corrección.

**Ampliación posterior (misma fecha)**
- `UmbralPrima`: alternativa a `UmbralFunding` que predice el funding con la fórmula de Binance a partir de la prima de las barras cerradas. Incluye el campo `Barra.prima`, la lectura opcional de `premiumIndexKlines` con control A4, la prueba de look-ahead endurecida (también altera la prima futura y detecta una trampa deliberada) y dos familias nuevas en el protocolo.
- Variante del generador «bajista suave» para medir la sensibilidad de las conclusiones al supuesto sobre el funding en mercados bajistas.

**Bloqueos**
- La red deniega `data.binance.vision` y todas las bolsas (403). No hay resultados con datos reales.

## 0.2.0 (2026-10-16): preparación de la validación histórica

Huellas:
- código: `2e35b68ff663b93698a3b38f78c17321e85bfe4af9885bfd5c5403c006220b00`;
- prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd`.

**Pipeline de datos verificable**
- `descargar` reanudable, con reintentos ante fallos de red. Los meses no publicados (404) quedan anotados como ausentes. Guarda los `.CHECKSUM` oficiales junto a cada zip.
- `importar`: copias aportadas por el usuario, verificadas contra sus `.CHECKSUM` oficiales.
- `calidad`: informe y filtros C1–C6 prerregistrados.
- `fabricar-sintetico`: archivos en formato oficial con marca SINTÉTICO.
- Regla de inicio común de las series, fijada de antemano.

**Evaluador prerregistrado** (`hcarry.lab.historico`, `python -m hcarry historico`): rev. 5 frente a UmbralFunding, con sensibilidad, bootstrap y conclusión automática. Separa las categorías por procedencia.

**Defectos corregidos** (todos impedían una evaluación válida):
- cualquier carpeta con formato oficial se etiquetaba como «binance_vision»: un ensayo sintético podía pasar por histórico;
- el panel no verificaba los archivos contra el manifiesto;
- un mes no publicado abortaba toda la descarga, y los `.CHECKSUM` oficiales no se guardaban;
- `cargar_datos` registraba todo lo leído con el cargador oficial como «datos reales»;
- `importar` habría etiquetado archivos fabricados como históricos (ahora lo impide la marca SINTÉTICO);
- un `.CHECKSUM` mal formado se reintentaba como si fuera un error de red.

Pruebas: 78, todas pasan.

**Fuentes:** `data.binance.vision` sigue denegado (403). Las otras 21 fuentes probadas también lo están. Ver `experimentos/historico/FUENTES_ALTERNATIVAS.md`.

## 0.2.1 (2026-10-16): ensayo, características de la regla e informe de la validación histórica

Huella del código: `68ddc304dc0cb06b05a7ccf113e98ad9d4b3b249847200dda9d6caba53568dd2`. El prerregistro no cambió (`90642cd1…`).

- **Defecto corregido:** `importar` atribuía al usuario los archivos fabricados (`via`). Prueba actualizada. El ensayo afectado se conserva con `ERRATA.md` y se repitió con resultados idénticos (D-16).
- **Lint:** sin efecto en cálculos. Verificado: el ensayo sintético se reproduce bit a bit con la huella del prerregistro (`2e35b68f…`).
- **Características operativas de la regla prerregistrada:** 40 mundos sintéticos por el pipeline real (`experimentos/historico/caracteristicas_regla.py`, `resumir_caracteristicas.py`). Resultados: 0/20 falsos positivos en mundos nulos; 6/12 detecciones en el mundo base.
- **`INFORME_VALIDACION_HISTORICA.md`:** P1 y P2 = EVIDENCIA INSUFICIENTE, porque no hay datos históricos (`data.binance.vision` sigue en 403).
