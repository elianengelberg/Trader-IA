# Informe de calidad de datos

**SINTÉTICO** — datos fabricados para ensayar el pipeline; no son datos de mercado.

- Directorio: `/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/caracteristicas/base_110`
- Manifiesto: `97dd1e60a1442ad828e4f072b680f8ed8243a154385fc7098954e1ec11cff0d8`
- Ventana: ['2019-10-01T00:00Z', '2026-06-01T00:00Z']  ·  horas: 58440
- **Apto para la evaluación: SÍ**

| Filtro | Resultado | Detalle |
|---|---|---|
| C1_procedencia | OK | `{"procedencia": "sintetico", "via": "fabricado en formato oficial para ensayar el pipeline", "archivos": 400, "sin_checksum": 0, "checksum_no_coincide": []}` |
| C2_cobertura | OK | `{"inicio_comun": "2019-10-01", "hasta": "2026-06-01", "meses": 80, "primer_mes": {"spot": "2019-10", "perp": "2019-10", "mark": "2019-10", "funding": "2019-10", "premium": "2019-10"}, "faltan": {}, "meses_con_prima": 80}` |
| C3_horas | OK | `{"horas": 58440, "rellenadas": 0, "fraccion": 0.0, "racha_max_h": 0}` |
| C4_funding | OK | `{"incidencias": [], "eventos": 7305, "intervalos_h": {"8": 7304}, "cambios": [], "tasa_modal": {"tasa": 0.0001, "fraccion": 0.5204654346338125}, "fraccion_negativas": 0.2187542778918549, "apr_medio_nocional": 0.0898060390143681}` |
| C5_coherencia | OK | `{"incidencias": [], "base_abs_mediana": 0.0004888752496414184, "base_abs_p99": 0.0023963476828643415, "base_abs_max": 0.003641631395713718, "mark_perp_abs_p99": 0.0006560730885389887, "mark_perp_abs_max": 0.0010901341110323148}` |
| C6_periodo | OK | `{"inicio": "2019-10-01T00:00Z", "fin": "2026-06-01T00:00Z"}` |

Umbrales (fijados antes de ver datos): `{"horas_rellenadas_frac_max": 0.005, "racha_rellenada_max_h": 24, "base_mediana_abs_max": 0.002, "mark_perp_p99_abs_max": 0.01, "funding_bloqueantes": ["A2", "A2b", "A4", "A7", "A8"], "coherencia_bloqueantes": ["A6", "P2"]}`
