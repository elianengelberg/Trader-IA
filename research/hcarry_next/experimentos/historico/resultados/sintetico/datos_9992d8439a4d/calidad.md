# Informe de calidad de datos

**SINTÉTICO** — datos fabricados para ensayar el pipeline; no son datos de mercado.

- Directorio: `/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/ensayo2/imp`
- Manifiesto: `9992d8439a4d5b2399d5e4c177a36522354383694d64d06ef72f8419393a7a72`
- Ventana: ['2019-10-01T00:00Z', '2026-06-01T00:00Z']  ·  horas: 58440
- **Apto para la evaluación: SÍ**

| Filtro | Resultado | Detalle |
|---|---|---|
| C1_procedencia | OK | `{"procedencia": "sintetico", "via": "importación de archivos FABRICADOS (marca SINTÉTICO); no los aportó el usuario", "archivos": 400, "sin_checksum": 0, "checksum_no_coincide": []}` |
| C2_cobertura | OK | `{"inicio_comun": "2019-10-01", "hasta": "2026-06-01", "meses": 80, "primer_mes": {"spot": "2019-10", "perp": "2019-10", "mark": "2019-10", "funding": "2019-10", "premium": "2019-10"}, "faltan": {}, "meses_con_prima": 80}` |
| C3_horas | OK | `{"horas": 58440, "rellenadas": 0, "fraccion": 0.0, "racha_max_h": 0}` |
| C4_funding | OK | `{"incidencias": [], "eventos": 7305, "intervalos_h": {"8": 7304}, "cambios": [], "tasa_modal": {"tasa": 0.0001, "fraccion": 0.6288843258042437}, "fraccion_negativas": 0.13114305270362767, "apr_medio_nocional": 0.14485039090348478}` |
| C5_coherencia | OK | `{"incidencias": [], "base_abs_mediana": 0.0003772351457801415, "base_abs_p99": 0.002281524865490936, "base_abs_max": 0.003410541561244429, "mark_perp_abs_p99": 0.0006189502637029554, "mark_perp_abs_max": 0.0011933242163971736}` |
| C6_periodo | OK | `{"inicio": "2019-10-01T00:00Z", "fin": "2026-06-01T00:00Z"}` |

Umbrales (fijados antes de ver datos): `{"horas_rellenadas_frac_max": 0.005, "racha_rellenada_max_h": 24, "base_mediana_abs_max": 0.002, "mark_perp_p99_abs_max": 0.01, "funding_bloqueantes": ["A2", "A2b", "A4", "A7", "A8"], "coherencia_bloqueantes": ["A6", "P2"]}`
