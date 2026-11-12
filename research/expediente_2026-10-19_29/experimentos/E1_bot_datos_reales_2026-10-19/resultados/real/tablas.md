### Resultado principal (solo largos, costos base)

| Config. | Ops. | Media neta/op. | IC90 (mensual) | P(>0) | IC90 (trimestral) | Mediana | Acierto | Bruta/op. | Nulo: media | p_nulo | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 trend_following | 629 | -0.237 % | [-0.341, -0.135] | 0.000 | [-0.356, -0.119] | -0.656 | 0.33 | -0.037 % | -0.245 | 0.4488 | EVIDENCIA EN CONTRA de una ventaja neta (IC90 de la media neta por operación < 0) |
| P2 mean_reversion | 139 | -0.519 % | [-0.724, -0.310] | 0.000 | [-0.698, -0.334] | -0.850 | 0.17 | -0.319 % | -0.303 | 0.9390 | EVIDENCIA EN CONTRA de una ventaja neta (IC90 de la media neta por operación < 0) |
| P3 breakout | 185 | -0.198 % | [-0.381, -0.017] | 0.036 | [-0.411, -0.001] | -0.640 | 0.34 | +0.002 % | -0.254 | 0.3153 | EVIDENCIA EN CONTRA de una ventaja neta (IC90 de la media neta por operación < 0) |
| S1 fusión (bot) | 795 | -0.294 % | [-0.384, -0.209] | 0.000 | [-0.384, -0.199] | -0.695 | 0.30 | -0.094 % | -0.255 | 0.7476 | secundaria (no decide) |

### Holm

signo {'P3': (0.9639, 0.0167, False), 'P2': (0.9998, 0.025, False), 'P1': (1.0, 0.05, False)}
nulo {'P3': (0.3153, 0.0167, False), 'P1': (0.4488, 0.025, False), 'P2': (0.939, 0.05, False)}

### Estrés y variantes (media neta por operación, % ; n)

| Config. | Base | Comisión ×2 (S2) | +1 barra (S3) | Costos mínimos (S4) | Gobernadores en vivo (S6) | Motor original (S7) |
|---|---|---|---|---|---|---|
| P1 trend_following | -0.237 (629) | -0.421 (638) | -0.221 (543) | 0.007 (629) | -0.237 (629) | -0.013 (24) |
| P2 mean_reversion | -0.519 (139) | -0.716 (137) | -0.183 (129) | -0.309 (136) | -0.519 (139) | -0.545 (135) |
| P3 breakout | -0.198 (185) | -0.436 (184) | -0.306 (180) | 0.046 (185) | -0.198 (185) | -0.232 (87) |
| S1 fusión (bot) | -0.294 (795) | -0.488 (798) | -0.157 (695) | -0.054 (793) | -0.294 (795) | — |

### Subperíodos y régimen ex ante (media neta %, n)

P1 trend_following {'2019-10→2021-12': ('-0.224', 199), '2022': ('-0.437', 84), '2023-01→2026-05': ('-0.196', 346)} {'alcista': ('-0.172', 248), 'bajista': ('-0.527', 70), 'lateral': ('-0.247', 302)}
P2 mean_reversion {'2019-10→2021-12': ('-0.156', 35), '2022': ('-0.566', 26), '2023-01→2026-05': ('-0.666', 78)} {'alcista': ('-0.047', 28), 'bajista': ('-0.382', 36), 'lateral': ('-0.775', 74)}
P3 breakout {'2019-10→2021-12': ('-0.264', 62), '2022': ('-0.496', 18), '2023-01→2026-05': ('-0.109', 105)} {'alcista': ('-0.119', 77), 'bajista': ('-0.383', 22), 'lateral': ('-0.190', 85)}
S1 fusión (bot) {'2019-10→2021-12': ('-0.255', 244), '2022': ('-0.392', 109), '2023-01→2026-05': ('-0.291', 442)} {'alcista': ('-0.176', 288), 'bajista': ('-0.444', 107), 'lateral': ('-0.356', 390)}

### Curva de capital y referencias

| Serie | Rent. total | Anualizada | Vol. anual | Sharpe | Sortino | Caída máx. | Exposición |
|---|---|---|---|---|---|---|---|
| P1 trend_following | -1.17 % | -0.18 % | 0.17 % | -1.03 | -0.35 | 1.40 % | 8.4 % |
| P2 mean_reversion | -1.35 % | -0.20 % | 0.10 % | -2.08 | -0.24 | 1.40 % | 1.5 % |
| P3 breakout | -0.29 % | -0.04 % | 0.11 % | -0.39 | -0.07 | 0.49 % | 2.0 % |
| S1 fusión (bot) | -2.16 % | -0.33 % | 0.19 % | -1.70 | -0.62 | 2.35 % | 10.1 % |
| buy_and_hold | 797.44 % | 38.98 % | 61.59 % | 0.84 | 0.83 | 77.20 % | 100.0 % |
| efectivo | 0.00 % | 0.00 % | 0.00 % | — | — | 0.00 % | 0.0 % |
| cruce_medias_20_50_long_flat | 4.13 % | 0.61 % | 40.74 % | 0.22 | 0.16 | 69.78 % | 52.5 % |
| volatilidad_objetivo_15 | 33.44 % | 4.42 % | 17.08 % | 0.34 | 0.33 | 34.88 % | 99.9 % |

### Distribución por operación, salidas, confianza y cortos hipotéticos

P1 trend_following {'cuantiles_pct': {'5': -2.4364022460614114, '25': -1.2391060693412497, '50': -0.6557156277258337, '75': 0.5105240919738134, '95': 2.9704637931106084}, 'ganancia_media_pct': 1.652174134904961, 'perdida_media_pct': -1.170399004841849, 'factor_beneficio': 0.6974339979556753, 'peor_racha_perdedora': 13, 'comisiones_medias_pct': 0.19996294265493128, 'barras_medias': 7.790143084260731}
   salidas: {'break-even stop': {'n': 11, 'media_pct': -0.0674579423446569}, 'break-even stop+trailing stop': {'n': 2, 'media_pct': -0.37816109258171765}, 'protective stop': {'n': 12, 'media_pct': -2.4031103085367045}, 'target reached': {'n': 147, 'media_pct': 2.1549793487097655}, 'target reached+trailing stop': {'n': 3, 'media_pct': 0.29599409957843426}, 'trailing stop': {'n': 454, 'media_pct': -0.9612775865283311}}
   confianza: {'spearman': -0.021185179184429838, 'ic90_bootstrap_mensual': [-0.08545939370184598, 0.043338750005845354], 'bandas': {'0.55-0.65': {'n': 304, 'media_pct': -0.1990515079706924}, '0.65-0.75': {'n': 124, 'media_pct': -0.47957213380387254}, '0.75-1.00': {'n': 201, 'media_pct': -0.14481173116127302}}}
   cortos hipotéticos (S5): 710 -0.298 {'P_media_mayor_0': 0.0008, 'ic90': [-0.4291739197024779, -0.16038761727248751], 'replicas_validas': 10000} | largos en S5: 630 -0.230
   gobernadores en vivo (S6): {'primer_bloqueo': None, 'decisiones_bloqueadas': 0, 'ultima_entrada': '2026-05-24T03:00:00+00:00'}
   decisiones: {'signals_generated': 58282, 'intents_submitted': 636, 'fills': 1478, 'orders_rejected': 8, 'protective_stops_unplaced': 41, 'stops_tightened': 3128, 'exits_requested': {'target reached': 151}, 'budget_rejected': 0}
P2 mean_reversion {'cuantiles_pct': {'5': -2.2470342650723585, '25': -1.2712843949772714, '50': -0.8504445269855104, '75': -0.06197614496859026, '95': 1.843453988670869}, 'ganancia_media_pct': 1.8888191115852895, 'perdida_media_pct': -0.9959930599106129, 'factor_beneficio': 0.3760139028233004, 'peor_racha_perdedora': 16, 'comisiones_medias_pct': 0.19968103099226442, 'barras_medias': 6.41726618705036}
   salidas: {'break-even stop': {'n': 20, 'media_pct': -0.09299311308726187}, 'protective stop': {'n': 31, 'media_pct': -1.7078475712123684}, 'target reached': {'n': 15, 'media_pct': 2.522979570491166}, 'target reached+trailing stop': {'n': 3, 'media_pct': 0.08803929846582266}, 'trailing stop': {'n': 70, 'media_pct': -0.7914004266657967}}
   confianza: {'spearman': -0.08330577773805799, 'ic90_bootstrap_mensual': [-0.22183999802957174, 0.05988112859861709], 'bandas': {'0.55-0.65': {'n': 96, 'media_pct': -0.4279160455609025}, '0.65-0.75': {'n': 42, 'media_pct': -0.7076839778397526}, '0.75-1.00': {'n': 1, 'media_pct': 'menos de 30: no se informa'}}}
   cortos hipotéticos (S5): 209 -0.608 {'P_media_mayor_0': 0.0, 'ic90': [-0.7700302948010387, -0.4436410711278746], 'replicas_validas': 10000} | largos en S5: 139 -0.565
   gobernadores en vivo (S6): {'primer_bloqueo': None, 'decisiones_bloqueadas': 0, 'ultima_entrada': '2026-05-27T15:00:00+00:00'}
   decisiones: {'signals_generated': 58282, 'intents_submitted': 139, 'fills': 343, 'orders_rejected': 0, 'protective_stops_unplaced': 13, 'stops_tightened': 429, 'exits_requested': {'target reached': 18}, 'budget_rejected': 0}
P3 breakout {'cuantiles_pct': {'5': -2.328221040255346, '25': -1.2232329827640125, '50': -0.6397633559621531, '75': 0.6570555433603379, '95': 2.760203693265829}, 'ganancia_media_pct': 1.6271827043371436, 'perdida_media_pct': -1.11839686014853, 'factor_beneficio': 0.7333764473358878, 'peor_racha_perdedora': 12, 'comisiones_medias_pct': 0.20000174506328292, 'barras_medias': 6.464864864864865}
   salidas: {'break-even stop': {'n': 7, 'media_pct': -0.10791335788838434}, 'break-even stop+trailing stop': {'n': 1, 'media_pct': -1.004049581756995}, 'protective stop': {'n': 6, 'media_pct': -1.4336563900317258}, 'target reached': {'n': 49, 'media_pct': 1.9805609450510515}, 'trailing stop': {'n': 122, 'media_pct': -1.011176975489359}}
   confianza: {'spearman': 0.22047306773814487, 'ic90_bootstrap_mensual': [0.11354149355411874, 0.318966139611358], 'bandas': {'0.55-0.65': {'n': 72, 'media_pct': -0.6698110257303984}, '0.65-0.75': {'n': 36, 'media_pct': 0.19764007900801053}, '0.75-1.00': {'n': 77, 'media_pct': 0.057582660765376936}}}
   cortos hipotéticos (S5): 163 -0.602 {'P_media_mayor_0': 0.0, 'ic90': [-0.8107449354639115, -0.3974433529666999], 'replicas_validas': 10000} | largos en S5: 185 -0.198
   gobernadores en vivo (S6): {'primer_bloqueo': None, 'decisiones_bloqueadas': 0, 'ultima_entrada': '2026-05-14T16:00:00+00:00'}
   decisiones: {'signals_generated': 58282, 'intents_submitted': 189, 'fills': 440, 'orders_rejected': 5, 'protective_stops_unplaced': 11, 'stops_tightened': 640, 'exits_requested': {'target reached': 50}, 'budget_rejected': 0}
S1 fusión (bot) {'cuantiles_pct': {'5': -2.349902804522558, '25': -1.285337423770254, '50': -0.695422555877882, '75': 0.37456361277890954, '95': 2.9817648040250733}, 'ganancia_media_pct': 1.717267677052296, 'perdida_media_pct': -1.1426476934464649, 'factor_beneficio': 0.6344915510394653, 'peor_racha_perdedora': 15, 'comisiones_medias_pct': 0.1999062397128547, 'barras_medias': 7.432704402515723}
   salidas: {'break-even stop': {'n': 28, 'media_pct': -0.07591216329999585}, 'break-even stop+protective stop': {'n': 1, 'media_pct': -1.2961795109935863}, 'break-even stop+trailing stop': {'n': 4, 'media_pct': -0.43270040466490656}, 'protective stop': {'n': 43, 'media_pct': -1.7726750803205946}, 'protective stop+trailing stop': {'n': 1, 'media_pct': -2.1732439600264986}, 'target reached': {'n': 168, 'media_pct': 2.2091217483378407}, 'target reached+trailing stop': {'n': 8, 'media_pct': 0.12271326786572719}, 'trailing stop': {'n': 542, 'media_pct': -0.9631517612547046}}
   confianza: {'spearman': -0.019530856124642032, 'ic90_bootstrap_mensual': [-0.07739639390548116, 0.039495133726066486], 'bandas': {'0.55-0.65': {'n': 403, 'media_pct': -0.3035089948439825}, '0.65-0.75': {'n': 183, 'media_pct': -0.43026916529036346}, '0.75-1.00': {'n': 209, 'media_pct': -0.15507897933957182}}}
   cortos hipotéticos (S5): 943 -0.409 {'P_media_mayor_0': 0.0, 'ic90': [-0.5257461123735088, -0.28288016713593334], 'replicas_validas': 10000} | largos en S5: 781 -0.277
   gobernadores en vivo (S6): {'primer_bloqueo': None, 'decisiones_bloqueadas': 0, 'ultima_entrada': '2026-05-27T15:00:00+00:00'}
   decisiones: {'signals_generated': 58282, 'intents_submitted': 803, 'fills': 1880, 'orders_rejected': 10, 'protective_stops_unplaced': 46, 'stops_tightened': 3633, 'exits_requested': {'target reached': 178}, 'budget_rejected': 0}

meta: {'tipo': 'HISTÓRICO REAL', 'inicio_utc': '2026-10-19T19:02:58.377277+00:00', 'fin_utc': '2026-10-19T19:46:26.997831+00:00', 'B': 10000, 'R': 2000, 'validez': {'invariancia_prefijo_real': True, 'solo_largos_sin_cortos': True, 'stops_y_duraciones': True, 'problemas': [], 'todo_ok': True}, 'barras': 58402, 'primera': '2019-10-01T00:00:00+00:00', 'ultima': '2026-05-31T23:00:00+00:00'}
