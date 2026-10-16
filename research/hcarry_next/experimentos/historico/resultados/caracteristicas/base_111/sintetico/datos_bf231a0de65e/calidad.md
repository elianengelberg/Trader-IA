# Informe de calidad de datos

**SINTÉTICO** — datos fabricados para ensayar el pipeline; no son datos de mercado.

- Directorio: `/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/caracteristicas/base_111`
- Manifiesto: `bf231a0de65e270fa07f54636fbeaf4b3b2b8a8fb4235717d7c795cb9316facb`
- Ventana: ['2019-10-01T00:00Z', '2026-06-01T00:00Z']  ·  horas: 58440
- **Apto para la evaluación: SÍ**

| Filtro | Resultado | Detalle |
|---|---|---|
| C1_procedencia | OK | `{"procedencia": "sintetico", "via": "fabricado en formato oficial para ensayar el pipeline", "archivos": 400, "sin_checksum": 0, "checksum_no_coincide": []}` |
| C2_cobertura | OK | `{"inicio_comun": "2019-10-01", "hasta": "2026-06-01", "meses": 80, "primer_mes": {"spot": "2019-10", "perp": "2019-10", "mark": "2019-10", "funding": "2019-10", "premium": "2019-10"}, "faltan": {}, "meses_con_prima": 80}` |
| C3_horas | OK | `{"horas": 58440, "rellenadas": 0, "fraccion": 0.0, "racha_max_h": 0}` |
| C4_funding | OK | `{"incidencias": [], "eventos": 7305, "intervalos_h": {"8": 7304}, "cambios": [], "tasa_modal": {"tasa": 0.0001, "fraccion": 0.6179329226557153}, "fraccion_negativas": 0.16632443531827515, "apr_medio_nocional": 0.10982187453798445}` |
| C5_coherencia | OK | `{"incidencias": [], "base_abs_mediana": 0.000391496570505967, "base_abs_p99": 0.0023596113195798463, "base_abs_max": 0.003941667026214013, "mark_perp_abs_p99": 0.0006365677035221617, "mark_perp_abs_max": 0.001158384054244399}` |
| C6_periodo | OK | `{"inicio": "2019-10-01T00:00Z", "fin": "2026-06-01T00:00Z"}` |

Umbrales (fijados antes de ver datos): `{"horas_rellenadas_frac_max": 0.005, "racha_rellenada_max_h": 24, "base_mediana_abs_max": 0.002, "mark_perp_p99_abs_max": 0.01, "funding_bloqueantes": ["A2", "A2b", "A4", "A7", "A8"], "coherencia_bloqueantes": ["A6", "P2"]}`
