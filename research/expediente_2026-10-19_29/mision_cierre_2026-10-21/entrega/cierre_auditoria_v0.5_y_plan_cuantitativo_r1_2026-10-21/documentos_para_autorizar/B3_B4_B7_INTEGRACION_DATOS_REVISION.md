# B-3 (integración real), B-4 (datos reales) y B-7 (revisión por un tercero)

## B-3. Integración en un ejecutor real: análisis, sin implementar
**Recomendación: no integrar en el papel de T** (`papel/corte.py`).
- Su protocolo está congelado (D-T2).
- Cambiar su ejecución sería una hipótesis nueva sobre T.

El ejecutor aislado debe usarse solo para los ejecutores **prospectivos de hipótesis nuevas**, desde su primer día.

**Precondiciones:**
- R-5: el ancla externa existe y su adaptador cumple el contrato C1–C8;
- A10: 0 reintentos, verificación de determinismo y un límite de tiempo explícito (adoptado en PEC-1.0);
- D-G4: la ubicación del registro de decisiones fuera del repositorio;
- para aceptar resultados, R-3 o la raíz de la hipótesis.

**Pasos** (cada uno reversible hasta el primer uso real):
1. el ejecutor nuevo llama a `ejecutar_encargo` con el ancla real, en un entorno de prueba, con un código sintético;
2. se ejecutan contra él las pruebas de contrato y de extremo a extremo de v0.5 (32);
3. un único encargo real en modo sombra: se calcula, se registra y no se usa;
4. revisión;
5. alta.

**Riesgos y cómo se tratan:**
- **Ancla no disponible:** el ejecutor debe fallar CERRADO; nunca seguir con el ancla local.
- **Bloqueo de un cálculo legítimo** por el rigor de las comprobaciones: aceptable. Un falso «no válido» cuesta tiempo;
  un falso «válido» cuesta la integridad.
- **Dependencia operativa nueva:** se documenta en el prerregistro de cada hipótesis.

## B-4. Datos reales: plan de adquisición y lectura, sin acceder
**Regla general:** ningún dato se lee para una ventana de evaluación antes de que el prerregistro esté **congelado y
anclado**. Lo que ya se vio (2017 → 2026-05 en BTC y ETH) está contaminado y el validador del prerregistro lo marca
(`pec.prerregistro.PERIODOS_CONTAMINADOS`).

| Paso | Control | Herramienta |
|---|---|---|
| 1. Fuente y licencia | Fuente primaria pública con suma de verificación publicada (p. ej. archivos diarios o mensuales con `.CHECKSUM`). Términos de uso revisados y registrados en el prerregistro (`datos.licencia`) | Prerregistro PEC-1.0 |
| 2. Descarga | Fuera del repositorio. Una entrada por archivo en un manifiesto de **solo añadidos**: URL, SHA-256, tamaño, cabecera `Date` del servidor y la suma publicada. Nunca se sobrescribe | Igual que H-CARRY y T-MULTI (`MANIFIESTO.json`) |
| 3. Integridad | SHA-256 = suma publicada. Si no coincide, el archivo se rechaza y no se reintenta en silencio | — |
| 4. Validación | V1–V9: orden, duplicados, conflictos, grilla, faltantes con umbral, OHLC, volumen, velas incompletas y ventana | `pec.datos.validar`, con 12 pruebas (serie limpia y 11 defectos o casos de borde inyectados) |
| 5. Procedencia independiente | Muestra cruzada con un **segundo proveedor** (otro exchange o un agregador con licencia), con una tolerancia fijada antes. Hoy no existe: es la debilidad de R-1 | Por implementar con la autorización |
| 6. Lectura por ventana | El lector de evaluación se niega a devolver filas fuera de la ventana autorizada; las lecturas se cuentan y se registran (B8 del plan) | Por implementar con la autorización |
| 7. Supervivencia | Si el universo tiene más de un activo, la lista de activos se fija con datos de la fecha de inicio (E3 mostró que no hay anuncios suficientes para reconstruirla) | Prerregistro (`universo.sesgo_supervivencia`) |

**Pedidos concretos que dependen de B-4** (heredados del expediente):
- A-EV-1: descargar ETHUSDT 1h;
- A-RS-1: los conteos F0 sin P&L;
- R-1: reproducir `contraste_btc` en solo lectura, solo si algún documento se va a apoyar en él.

**Recomendación:**
- no autorizar ninguno hasta decidir D-G1 con la criba de detectabilidad (05_PLAN_CUANTITATIVO.md §6);
- si alguna hipótesis la pasa, autorizar solo la lectura que su prerregistro congelado declare.

## B-7. Revisión por un tercero: alcance
**Quién:** una persona o un equipo que no haya participado.
- Perfil doble: estadística aplicada (series temporales y bootstrap) e ingeniería de seguridad o criptografía aplicada.
- Sin permisos de escritura sobre nada de lo revisado.

**Qué recibe** (por identidad y hash, sin copias sueltas):
- el ZIP v0.5 (`5bf9bc5d…`) y este ZIP;
- el expediente metodológico (`33ba77c1…`);
- acceso de lectura al repositorio en `692f2b2` o en la rama publicada (B-1).

**Preguntas que debe responder:**
1. ¿Puede P1 llegar a VERIFICADO sin una declaración de una raíz aprobada? ¿Hay alguna ruta de error que termine en
   aceptación?
2. ¿La implementación de Ed25519 es correcta (RFC 8032, sin cofactor, con rechazo de claves y R de orden pequeño o
   mixto)? ¿La prueba diferencial de 807 casos es suficiente?
3. ¿P4 garantiza el uso único con el ancla local y con un ancla externa que cumpla C1–C8? ¿Faltan modos de fallo?
4. ¿El MEC v0.2 y el PEC-1.0 son correctos? En particular:
   - las fórmulas del bootstrap-t y la dualidad;
   - las fronteras O'Brien–Fleming;
   - el diseño de la calibración;
   - la elección de ℓ fijo;
   - el benchmark de exposición equivalente.
5. ¿Son defendibles las decisiones técnicas tomadas (D-S1, D-S2, D-S3, D-S5, D-S6, D-S7, A9, A10, A13 y A14)?
6. Reproducción en **otra máquina**:
   - `ejecutar_todo.sh` de v0.5 y `ejecutar_verificacion.sh` de este paquete;
   - ¿coincide la evidencia?
7. ¿Cada cifra que declaran los documentos coincide con la evidencia? (`auditoria/afirmaciones_vs_evidencia.py` ayuda,
   pero lo escribió el mismo autor.)
8. ¿La matriz de amenazas está completa? ¿Hay amenazas sin control proporcional?

**Entregable:** un informe firmado por el revisor, con hallazgos clasificados y reproducibles.

**Esfuerzo estimado:** 3 a 5 días de una persona con ese perfil.
