# Tabla completa de renombres y redenominaciones (Adenda 1)

Generada por `tabla_a_markdown.py` desde `TABLA_RENOMBRES_COMPLETA.json`, que generó y verificó `construir_tabla.py`:
- cada cita es una subcadena del texto archivado del archivo citado;
- la actividad sale de episodios y cortes, sin ningún precio ni volumen.

**Convenciones:**
- r = unidades nuevas por unidad vieja;
- E = día UTC en que cesa la negociación spot del par viejo, según el texto (N5);
- la apertura es la que dice el texto; la actividad es la de Vision.

**Resumen:** 76 entradas.
- se aplican **50** mapeos (23 de regla 1, 1 de regla 1R y 26 de regla 2);
- 3 quedan para la decisión D-1;
- 4 son anuncios fuera de la regla;
- 19 son casos de la regla 3;
- los 117 pares del barrido por cuerpo están clasificados en `clasificacion_barrido.json`.

## Regla 1 · renombre con cambio de símbolo (se mapea) (23)

| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |
|---|---|---|---|---|---|---|---|---|
| T001 | VENUSDT → VETUSDT | 100 | 2018-07-23 | 2018-07-25 | 2018-07-22 → 2018-07-25 (hueco 2 d) | `zd_360007439672_d538039394aa.json…` (20180821): «at a ratio of 1 VEN = 100 VET» | alta | Ninguno en A |
| T002 | BCHABCUSDT → BCHUSDT | 1 | 2019-11-28 | 2019-11-28 | 2019-11-27 → 2019-11-28 (hueco 0 d) | `zd_360037219511_27e27ad63185.json…` (20220119): «at a ratio of 1 BCHABC = 1 BCH» | alta | Ninguno en A |
| T003 | STORMUSDT → STMXUSDT | 1 | 2020-06-08 | 2020-06-11 | 2020-06-07 → 2020-06-11 (hueco 3 d) | `url_https___www.binance.com_en_support_announc…` (20211207): «at a ratio of 1 STORM = 1 STMX» | alta | Ninguno en A |
| T004 | ERDUSDT → EGLDUSDT | 0.001 | 2020-08-31 | 2020-09-03 | 2020-08-30 → 2020-09-03 (hueco 3 d) | `bn_aa864b2d4db24379b606249d0cba87fb_923aec2ca1…` (20210724): «at a ratio of 1000 ERD = 1 EGLD» | alta | Ninguno en A |
| T005 | LENDUSDT → AAVEUSDT | 0.01 | 2020-10-12 | 2020-10-15 | 2020-10-11 → 2020-10-15 (hueco 3 d) | `bn_17595222999545348c8acdd5dc41c00a_7cbc5104a0…` (20201124): «at a ratio of 100 LEND = 1 AAVE» | alta | Ninguno en A |
| T006 | STRATUSDT → STRAXUSDT | 1 | 2020-11-12 | 2020-11-18 | 2020-11-11 → 2020-11-18 (hueco 6 d) | `bn_1937b7781c5043efa66c07141be3bdc2_e3f3ac372b…` (20201127): «at a ratio of 1 STRAT = 1 STRAX» | alta | Ninguno en A |
| T008 | XZCUSDT → FIROUSDT | 1 | 2021-01-25 | 2021-01-29 | 2021-01-24 → 2021-01-29 (hueco 4 d) | `bn_4a06d6ab6abb4f08b12bb93d6fec30ec_1d51d70297…` (20210302): «at a ratio of 1 XZC = 1 FIRO» | alta | Ninguno en A |
| T013 | NPXSUSDT → PUNDIXUSDT | 0.001 | 2021-04-05 | 2021-04-09 | 2021-04-04 → 2021-04-09 (hueco 4 d) | `bn_8bdcb060635b491d912247fb00603d4d_821867c8b6…` (20210514): «at a ratio of 1,000 NPXS = 1 PUNDIX» | alta | Ninguno en A |
| T027 | PAXUSDT → USDPUSDT | 1 | 2021-09-06 | 2021-09-10 | 2021-09-05 → 2021-09-10 (hueco 4 d) | `bn_c313480177e4457bb1e1b848c88bbf78_5cdfdffc3e…` (20211021): «ratio of 1 PAX = 1 USDP» | alta | Ninguno en A |
| T032 | BZRXUSDT → OOKIUSDT | 10 | 2021-12-20 | 2021-12-24 | 2021-12-19 → 2021-12-24 (hueco 4 d) | `bn_dff27dc6bcbb432c902bcbea5e24ddfa_1175382161…` (20220529): «Binance will support the bZx Protocol Token (BZRX) token swap and redenomination plan to OokiDAO Token (OOKI)» (+3 citas) | alta | Ninguno en A |
| T033 | BTTUSDT → BTTCUSDT | 1000 | 2022-01-17 | 2022-01-25 | 2022-01-16 → 2022-01-25 (hueco 8 d) | `bn_2722e6da4f5141dd9b2fb07b5b1f3f75_372793e0ce…` (20220120): «at a ratio of 1 BTT (Old) = 1,000 BTTC» (+3 citas) | alta | Ninguno en A |
| T034 | NANOUSDT → XNOUSDT | 1 | 2022-01-24 | 2022-01-28 | 2022-01-23 → 2022-01-28 (hueco 4 d) | `bn_3dc8f6de281f4781a246a1658a21cb80_e7bc3f2767…` (20220701): «Binance will update the ticker of NANO to XNO» (+3 citas) | alta | Ninguno en A |
| T035 | ANYUSDT → MULTIUSDT | 1 | 2022-03-30 | 2022-04-06 | 2022-03-29 → 2022-04-06 (hueco 7 d) | `url_https___www.binance.com_en_support_announc…` (20221130): «at a ratio of 1 ANY = 1 MULTI» | alta | Ninguno en A |
| T036 | GXSUSDT → REIUSDT | 10 | 2022-04-25 | 2022-05-04 | 2022-04-24 → 2022-05-04 (hueco 9 d) | `bn_bdfb52830f2f4bfcba496f3f92876b5c_ccba14b6e6…` (20220809): «Binance will support the GXChain (GXS) mainnet token swap and redenomination plan to REI Network (REI)» (+3 citas) | alta | Ninguno en A |
| T037 | EPSUSDT → EPXUSDT | 88 | 2022-05-09 | 2022-05-18 | 2022-05-08 → 2022-05-23 (hueco 14 d) | `bn_cf9526489aa041508f4cd57612f34119_c6ec648a66…` (20220819): «The ticker of EPS will be updated to EPX» (+4 citas) | alta | Ninguno en A |
| T039 | RAMPUSDT → LEVERUSDT | 35 | 2022-07-04 | 2022-07-13 | 2022-07-03 → 2022-07-13 (hueco 9 d) | `bn_0a445bbdac634512886df1bdce74f3da_3631af0d92…` (20220819): «Binance will support the RAMP (RAMP) token swap, redenomination and rebranding plan to LeverFi (LEVER)» (+3 citas) | alta | Ninguno en A |
| T040 | POLYUSDT → POLYXUSDT | 1 | 2022-10-10 | 2022-10-17 | 2022-10-09 → 2022-10-17 (hueco 7 d) | `url_https___www.binance.com_en_support_announc…` (20221203): «at a ratio of 1 POLY = 1 POLYX» | alta | Ninguno en A |
| T042 | MFTUSDT → HIFIUSDT | 0.01 | 2023-01-12 | — | 2023-01-02 → 2023-01-12 (hueco 9 d) | `url_https___www.binance.com_en_support_announc…` (20230322): «Binance has completed the Mainframe (MFT) token swap, redenomination and rebranding plan to Hifi Finance (HIFI)» (+2 citas) | media | **Dentro de A** (edad del nuevo) |
| T044 | COCOSUSDT → COMBOUSDT | 1 | 2023-06-02 | — | 2023-05-28 → 2023-06-02 (hueco 4 d) | `url_https___www.binance.com_en_support_announc…` (20230927): «The distribution of COMBO (COMBO) was conducted at a ratio of 1 COCOS = 1 COMBO» | media | Dentro de A (ya en la tabla de 22) |
| T046 | MCUSDT → BEAMXUSDT | 100 | 2023-11-07 | 2023-11-14 | 2023-11-06 → 2023-11-14 (hueco 7 d) | `url_https___www.binance.com_en_support_announc…` (20241104): «All MC tokens will be swapped for BEAMX at a ratio of 1 MC = 100 BEAMX» | alta | Dentro de A (ya en la tabla de 22) |
| T047 | TVKUSDT → VANRYUSDT | 1 | 2023-12-01 | — | 2023-11-26 → 2023-12-01 (hueco 4 d) | `url_https___www.binance.com_en_support_announc…` (20240301): «The distribution was conducted at a ratio of 1 TVK = 1 VANRY» | media | Dentro de A (ya en la tabla de 22) |
| T048 | PLAUSDT → PDAUSDT | 1 | 2024-02-26 | 2024-03-01 | 2024-02-25 → 2024-03-01 (hueco 4 d) | `url_https___www.binance.com_en_support_announc…` (20240528): «PLA tokens will assume the ticker of PDA on Binance» (+1 citas) | alta | Dentro de A (ya en la tabla de 22) |
| T050 | MATICUSDT → POLUSDT | 1 | 2024-09-10 | 2024-09-13 | 2024-09-09 → 2024-09-13 (hueco 3 d) | `url_https___www.binance.com_en_support_announc…` (20241009): «All MATIC tokens will be swapped to POL at a ratio of 1 MATIC = 1 POL» | alta | Dentro de A (ya en la tabla de 22) |

**Notas:**
- **T027 PAXUSDT → USDPUSDT:** PAX y USDP están en la lista fija de exclusión (§4.5): el mapeo no cambia ningún universo.
- **T037 EPSUSDT → EPXUSDT:** El texto anuncia la apertura de EPX/USDT para el 2022-05-18; un anuncio posterior archivado informa una demora («Binance will require additional time…»). La actividad muestra el primer día de EPXUSDT el 2022-05-23 (hueco de 14 días, < 30).
- **T042 MFTUSDT → HIFIUSDT:** Solo está archivado el anuncio de finalización (fechado 2023-01-12); fija símbolos, relación y fecha de finalización, no la hora de cese del par viejo. E = fecha del anuncio de finalización (mismo criterio que COCOS→COMBO y TVK→VANRY en la tabla de 22).
- **T044 COCOSUSDT → COMBOUSDT:** Solo está archivado el anuncio de finalización (2023-06-02): fija símbolos, relación y fecha de finalización, no la hora de cese del par viejo. El anuncio previo que cita no está archivado. E = fecha del anuncio de finalización.
- **T047 TVKUSDT → VANRYUSDT:** Solo está archivado el anuncio de finalización (2023-12-01): fija símbolos, relación y fecha de finalización, no la hora de cese del par viejo. E = fecha del anuncio de finalización.

## Regla 1, última oración · ticker reutilizado (el tramo nuevo es otro listado) (1)

| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |
|---|---|---|---|---|---|---|---|---|
| T038 | LUNAUSDT → (listado nuevo) | — | 2022-05-31 | 2022-05-31 | corte 2022-05-12 → 2022-05-31 | `bn_9c8abd90df5d4890822e6988f7dc8f0c_da2dc14576…` (20220812): «LUNA (old) was renamed as LUNC while LUNA (new) assumes the ticker LUNA» (+2 citas) | alta | Ninguno en A |

**Notas:**
- **T038 LUNAUSDT → —:** Adenda 1, regla 1: «Si después X vuelve a negociarse, ese tramo es un listado nuevo (otro activo), aunque el corte haya durado menos de 30 días». LUNAUSDT desde el 2022-05-31 es Terra 2.0: listado nuevo. La fecha exacta del cambio de ticker no está archivada («has since been renamed»); el corte de actividad (2022-05-12 → 2022-05-31) y la apertura de Terra 2.0 sí. La continuación del LUNA viejo por LUNCUSDT (primer día 2022-09-09, 120 días después) es la decisión D-1.

## Regla 2 · redenominación con el mismo símbolo (se mapea) (26)

| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |
|---|---|---|---|---|---|---|---|---|
| T007 | COCOSUSDT → COCOSUSDT | 0.001 | 2021-01-19 | 2021-01-23 | corte 2021-01-18 → 2021-01-23 | `bn_f555f8013eff42bc9c91eaa48b9da24b_83402e98fd…` (20211129): «begin swapping the old COCOS tokens with the new COCOS tokens at a ratio of 1,000:1» | alta | Ninguno en A |
| T009 | SXPDOWNUSDT → SXPDOWNUSDT | 1/10.000 | 2021-03-10 | — | corte 2021-03-09 → 2021-03-11 | `bn_a43a407fd48f44d29ecc59bb86772c25_d91c653791…` (20210412): «10,000-for-1 reverse token split, starting at 2021-03-10» | media | Ninguno (apalancado, §4.5) |
| T010 | BTCSTUSDT → BTCSTUSDT | 10 | 2021-03-15 | 2021-03-19 | corte 2021-03-14 → 2021-03-19 | `bn_2c08ba9e1a1b409fb6a4a2cb2f5ed58b_ca587e4ce6…` (20211203): «swap the old BTCST tokens with the new BTCST tokens at a ratio of 1:10» | media | Ninguno en A |
| T011 | SUSHIDOWNUSDT → SUSHIDOWNUSDT | 1/10.000 | 2021-03-23 | — | corte 2021-03-22 → 2021-03-24 | `bn_a00da142c1c549faaa7c1f78817930b7_58f2001193…` (20210801): «10,000-for-1 reverse token split, starting at 2021-03-23» | media | Ninguno (apalancado, §4.5) |
| T012 | DREPUSDT → DREPUSDT | 0.01 | 2021-03-29 | 2021-04-02 | corte 2021-03-28 → 2021-04-02 | `url_https___www.binance.com_en_support_announc…` (20230929): «We will swap the old DREP tokens with the new DREP tokens at a ratio of 100:1» | alta | Ninguno en A |
| T014 | AAVEDOWNUSDT → AAVEDOWNUSDT | 1/10.000 | 2021-04-06 | 2021-04-07 | corte 2021-04-05 → 2021-04-07 | `bn_c72f436a7847451eb403bfbdaf617984_1d0bcb863d…` (20210413): «10,000-for-1 reverse token split» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T015 | DOTDOWNUSDT → DOTDOWNUSDT | 1/10.000 | 2021-04-06 | 2021-04-07 | corte 2021-04-05 → 2021-04-07 | `bn_c72f436a7847451eb403bfbdaf617984_1d0bcb863d…` (20210413): «10,000-for-1 reverse token split» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T016 | ADADOWNUSDT → ADADOWNUSDT | 1/10.000 | 2021-04-07 | 2021-04-08 | corte 2021-04-06 → 2021-04-08 | `bn_c72f436a7847451eb403bfbdaf617984_1d0bcb863d…` (20210413): «10,000-for-1 reverse token split» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T017 | LINKDOWNUSDT → LINKDOWNUSDT | 1/10.000 | 2021-04-07 | 2021-04-08 | corte 2021-04-06 → 2021-04-08 | `bn_c72f436a7847451eb403bfbdaf617984_1d0bcb863d…` (20210413): «10,000-for-1 reverse token split» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T018 | XRPDOWNUSDT → XRPDOWNUSDT | 1/10.000 | 2021-04-07 | 2021-04-08 | corte 2021-04-06 → 2021-04-08 | `bn_c72f436a7847451eb403bfbdaf617984_1d0bcb863d…` (20210413): «10,000-for-1 reverse token split» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T019 | BNBDOWNUSDT → BNBDOWNUSDT | 1/100.000 | 2021-04-13 | 2021-04-14 | corte 2021-04-12 → 2021-04-14 | `bn_8587ebb4c3c94f92a4fa7ecb23781f20_9b3b1796cc…` (20210513): «100,000-for-1 reverse token split» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T020 | SXPDOWNUSDT → SXPDOWNUSDT | 1/100.000 | 2021-04-13 | 2021-04-14 | corte 2021-04-12 → 2021-04-14 | `bn_8587ebb4c3c94f92a4fa7ecb23781f20_9b3b1796cc…` (20210513): «100,000-for-1 reverse token split» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T021 | YFIDOWNUSDT → YFIDOWNUSDT | 1/100.000 | 2021-05-31 | — | corte 2021-05-30 → 2021-06-01 | `bn_23d1357993cd43749a5f682ab2e8c739_5be41422d5…` (20211129): «100,000-for-1 reverse token split, starting at 2021-05-31» | media | Ninguno (apalancado, §4.5) |
| T022 | SUNUSDT → SUNUSDT | 1000 | 2021-06-14 | 2021-06-18 | corte 2021-06-13 → 2021-06-18 | `bn_f923f2e4056843a9a9b87beb2aaa2f31_e761d45b0d…` (20210729): «at a ratio of 1 SUN (Old) = 1,000 SUN (New)» | alta | Ninguno en A |
| T023 | ETHDOWNUSDT → ETHDOWNUSDT | 1/100.000 | 2021-07-08 | 2021-07-09 | corte 2021-07-07 → 2021-07-09 | `url_https___www.binance.com_en_support_announc…` (20230324): «100,000-for-1 reverse token split, starting at 2021-07-08» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T024 | LTCDOWNUSDT → LTCDOWNUSDT | 1/100.000 | 2021-08-17 | 2021-08-18 | corte 2021-08-16 → 2021-08-18 | `bn_1b9392b259744884b342dc9708aa9b90_d55d5ecd06…` (20211205): «100,000-for-1 reverse token split» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T025 | UNIDOWNUSDT → UNIDOWNUSDT | 1/100.000 | 2021-08-17 | 2021-08-18 | corte 2021-08-16 → 2021-08-18 | `bn_1b9392b259744884b342dc9708aa9b90_d55d5ecd06…` (20211205): «100,000-for-1 reverse token split» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T026 | XLMDOWNUSDT → XLMDOWNUSDT | 1/100.000 | 2021-08-26 | — | corte 2021-08-25 → 2021-08-27 | `bn_3c970877a4d446b1a7f42b8b731a773f_bf2e5f6cda…` (20211027): «100,000-for-1 reverse token split, starting at 2021-08-26» | media | Ninguno (apalancado, §4.5) |
| T028 | XTZDOWNUSDT → XTZDOWNUSDT | 1/100.000 | 2021-09-08 | 2021-09-09 | corte 2021-09-07 → 2021-09-09 | `bn_e48368c945b84bf89cea20339ec345bf_f761bfa564…` (20211018): «100,000-for-1 reverse token split, starting at 2021-09-08» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T029 | TRXDOWNUSDT → TRXDOWNUSDT | 1/100.000 | 2021-09-13 | 2021-09-14 | corte 2021-09-12 → 2021-09-14 | `bn_c057c3e6e3c644d7b087ab1d6e2446b7_3db55726a5…` (20211205): «100,000-for-1 reverse token split, starting at 2021-09-13» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T030 | SUSHIDOWNUSDT → SUSHIDOWNUSDT | 1/100.000 | 2021-09-23 | 2021-09-24 | corte 2021-09-22 → 2021-09-24 | `bn_2e762fb338374b17adde728059708ff2_4583557ade…` (20211017): «100,000-for-1 reverse token split, starting at 2021-09-23» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T031 | DOTDOWNUSDT → DOTDOWNUSDT | 1/100.000 | 2021-10-21 | 2021-10-22 | corte 2021-10-20 → 2021-10-22 | `bn_e5b1ce92490b490480d3f4cbac923d12_a84a9353fd…` (20211024): «100,000-for-1 reverse token split, starting at 2021-10-21» (+1 citas) | alta | Ninguno (apalancado, §4.5) |
| T041 | VIDTUSDT → VIDTUSDT | 10 | 2022-10-31 | 2022-11-09 | corte 2022-10-30 → 2022-11-09 | `url_https___www.binance.com_en_support_announc…` (20230204): «at a ratio of 1 old VIDT = 10 new VIDT» (+2 citas) | alta | Ninguno en A |
| T043 | BNXUSDT → BNXUSDT | 100 | 2023-02-16 | 2023-02-22 | corte 2023-02-15 → 2023-02-22 | `url_https___www.binance.com_en_support_announc…` (20230609): «at a ratio of 1 old BNX = 100 new BNX» (+3 citas) | alta | Ninguno en A |
| T045 | QUICKUSDT → QUICKUSDT | 1000 | 2023-07-17 | 2023-07-21 | corte 2023-07-16 → 2023-07-21 | `url_https___www.binance.com_en_support_announc…` (20240222): «at a ratio of 1 old QUICK = 1,000 new QUICK» (+1 citas) | alta | Ninguno en A |
| T049 | STRAXUSDT → STRAXUSDT | 10 | 2024-03-20 | 2024-03-28 | corte 2024-03-19 → 2024-03-28 | `url_https___www.binance.com_en_support_announc…` (20241011): «at a ratio of 1 old STRAX = 10 new STRAX» (+1 citas) | alta | Ninguno en A |

**Notas:**
- **T010 BTCSTUSDT → BTCSTUSDT:** El texto dice «1:10» sin nombrar qué lado es el viejo; se lee 1 viejo = 10 nuevos por analogía con «COCOS 1,000:1» (1.000 viejos = 1 nuevo). Previo a A: no afecta a A.
- **T012 DREPUSDT → DREPUSDT:** Fechas según la actualización del 2021-03-22 (cese 2021-03-29 04:00, apertura 2021-04-02 04:00).
- **T043 BNXUSDT → BNXUSDT:** El anuncio previo fija la reapertura para el 2023-02-24; un anuncio posterior archivado la adelanta al 2023-02-22, que coincide con la actividad.

## Decisión D-1 · la regla 1 no resuelve el caso (NO se mapea con la lectura literal) (3)

| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |
|---|---|---|---|---|---|---|---|---|
| T062 | GTOUSDT → GFTUSDT | 1 | — | 2023-09-22 | 2022-11-27 → 2023-09-22 (hueco 298 d) | `url_https___www.binance.com_en_support_announc…` (20230202): «Binance will remove and cease trading on the following trading pairs at 2022-11-28 03:00 (UTC) : Spot Pairs : ARK/BTC, BEAM/BTC, BTCST/BTC, BTCST/USDT…» (+3 citas) | alta | **Dentro de A** solo con la opción (b) |
| T065 | LUNAUSDT → LUNCUSDT | 1 | — | — | 2022-05-12 → 2022-09-09 (hueco 119 d) | `bn_9c8abd90df5d4890822e6988f7dc8f0c_da2dc14576…` (20220812): «LUNA (old) was renamed as LUNC while LUNA (new) assumes the ticker LUNA» | alta | Ninguno en A |
| T075 | USTUSDT → USTCUSDT | 1 | — | — | 2022-05-12 → 2023-03-10 (hueco 301 d) | `bn_9c8abd90df5d4890822e6988f7dc8f0c_da2dc14576…` (20220812): «UST (old) was renamed as USTC» | alta | Ninguno en A |

**Notas:**
- **T062 GTOUSDT → GFTUSDT:** El par GTO/USDT se retiró por anuncio el 2022-11-28 (último día activo 2022-11-27), antes del canje (anunciado con calendario desde el 2023-01-18; completado con 1 GTO = 1 GFT). GFT/USDT abrió el 2023-09-22 (299 días después). En la fecha efectiva del canje no había «listado vigente» de X en USDT.
- **T065 LUNAUSDT → LUNCUSDT:** Continuación del LUNA viejo (último día en LUNAUSDT 2022-05-12) por LUNCUSDT (primer día 2022-09-09). La reutilización del ticker sí está resuelta (entrada regla_1_reutilizacion).
- **T075 USTUSDT → USTCUSDT:** USTUSDT termina el 2022-05-12; USTCUSDT empieza el 2023-03-10. UST y USTC están en la lista fija (§4.5): sin efecto con cualquier lectura.

## Anunciado, fuera de la regla 1 · bifurcación (1)

| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |
|---|---|---|---|---|---|---|---|---|
| T055 | BCCUSDT → BCHABCUSDT | — | — | — | — | `url_https___www.binance.com_en_support_announc…` (20210517): «BCHABC and BCHSV balances were each distributed to users in a ratio of 1 BCC = 1 BCHABC and 1 BCC = 1 BCHSV» | alta | Ninguno en A |

**Notas:**
- **T055 BCCUSDT → BCHABCUSDT:** Bifurcación: BCC se reemplazó por dos activos (BCHABC y BCHSV, 1:1 cada uno). La regla 1 presupone un único Y que hereda posiciones; aquí no hay uno. Salida de BCC y dos listados nuevos. Sin efecto en A (2018).

## Anunciado, fuera de la regla 1 · fusión en un par que ya cotizaba (1)

| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |
|---|---|---|---|---|---|---|---|---|
| T070 | RGTUSDT → TRIBEUSDT | — | — | — | — | `bn_260d553938db4d568d7d58414fa317fa_7e314ae2c5…` (20220808): «1 RGT : 26.7 TRIBE» | alta | Ninguno en A |

**Notas:**
- **T070 RGTUSDT → TRIBEUSDT:** Canje de RGT por TRIBE (1 RGT : 26,7 TRIBE). TRIBEUSDT ya cotizaba desde 2021-08-24, antes del fin de RGTUSDT (2022-03-13): Y no puede «continuar» a X. Salida de RGT. Sin efecto en A.

## Anunciado, fuera de la regla 1 · conversión con solapamiento (2)

| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |
|---|---|---|---|---|---|---|---|---|
| T056 | BETHUSDT → WBETHUSDT | — | — | — | — | `url_https___www.binance.com_en_support_announc…` (20230930): «1 WBETH = 1 BETH» | alta | Ninguno en A |
| T074 | USDSBUSDT → USDSUSDT | — | — | — | — | `url_https___www.binance.com_en_support_announc…` (20220120): «1 USDSB = 1 USDS» | alta | Ninguno en A |

**Notas:**
- **T056 BETHUSDT → WBETHUSDT:** WBETHUSDT cotiza desde 2023-07-19 y BETHUSDT hasta 2023-10-10: se solapan; no hay continuación posible. Salida de BETH (2023, con evidencia en (iv′)).
- **T074 USDSBUSDT → USDSUSDT:** USDSUSDT ya cotizaba desde 2019-02-14. Ambos en la lista fija (§4.5): sin efecto.

## Regla 3 · cambio de símbolo SIN anuncio archivado (limitación) (12)

| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |
|---|---|---|---|---|---|---|---|---|
| T052 | AGIXUSDT → FETUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T057 | DARUSDT → DUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T058 | EOSUSDT → AUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T059 | FTMUSDT → SUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T060 | FXSUSDT → FRAXUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T061 | GALUSDT → GUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T064 | KLAYUSDT → KAIAUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T066 | MKRUSDT → SKYUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T068 | OCEANUSDT → FETUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T069 | OMUSDT → MANTRAUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T071 | RNDRUSDT → RENDERUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |
| T073 | TOMOUSDT → VICUSDT | — | — | — | — | — (sin cuerpo archivado) | — | Ninguno en A |

**Notas:**
- **T052 AGIXUSDT → FETUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T057 DARUSDT → DUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T058 EOSUSDT → AUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T059 FTMUSDT → SUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T060 FXSUSDT → FRAXUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T061 GALUSDT → GUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T064 KLAYUSDT → KAIAUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T066 MKRUSDT → SKYUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T068 OCEANUSDT → FETUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T069 OMUSDT → MANTRAUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T071 RNDRUSDT → RENDERUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.
- **T073 TOMOUSDT → VICUSDT:** Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con liquidación contable (§4.10) y listado nuevo; se informa como limitación.

## Regla 3 · corte con reanudación SIN anuncio de canje (mismo listado) (7)

| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |
|---|---|---|---|---|---|---|---|---|
| T051 | AEURUSDT → AEURUSDT | — | — | — | corte 2023-12-04 → 2023-12-08 | — (sin cuerpo archivado) | — | Ninguno en A |
| T053 | AUDUSDT → AUDUSDT | — | — | — | corte 2020-11-12 → 2020-11-14 | — (sin cuerpo archivado) | — | Ninguno en A |
| T054 | AXSUSDT → AXSUSDT | — | — | — | corte 2026-02-09 → 2026-02-11 | — (sin cuerpo archivado) | — | Ninguno en A |
| T063 | KEYUSDT → KEYUSDT | — | — | — | corte 2023-02-09 → 2023-03-10 | `url_https___www.binance.com_en_support_announc…` (20230321): «Binance will remove and cease trading on the following spot trading pairs: At 2023-02-10 03:00 (UTC) : BOND/ETH, BSW/ETH, C98/BNB, C98/BRL, ERN/BNB, E…» | — | Ninguno en A |
| T067 | NBTUSDT → NBTUSDT | — | — | — | corte 2022-09-11 → 2022-10-01 | — (sin cuerpo archivado) | — | Ninguno en A |
| T072 | SCRUSDT → SCRUSDT | — | — | — | corte 2024-10-20 → 2024-10-22 | `url_https___www.binance.com_en_support_announc…` (20241210): «Binance will end the Scroll (SCR) Pre-Market at 2024-10-21 09:00 (UTC) and open spot trading for the following pairs at 2024-10-22 08:00 (UTC)» | — | Ninguno en A |
| T076 | USUALUSDT → USUALUSDT | — | — | — | corte 2024-12-16 → 2024-12-18 | — (sin cuerpo archivado) | — | Ninguno en A |

**Notas:**
- **T051 AEURUSDT → AEURUSDT:** Corte con reanudación sin anuncio archivado de canje o redenominación: mismo listado (corte < 30 días, v3 §2.2.3).
- **T053 AUDUSDT → AUDUSDT:** Corte con reanudación sin anuncio archivado de canje o redenominación: mismo listado (corte < 30 días, v3 §2.2.3).
- **T054 AXSUSDT → AXSUSDT:** Corte con reanudación sin anuncio archivado de canje o redenominación: mismo listado (corte < 30 días, v3 §2.2.3).
- **T063 KEYUSDT → KEYUSDT:** Retiro del par KEY/USDT el 2023-02-10 (anuncio archivado: «Binance will remove and cease trading on the following spot trading pairs: At 2023-02-10 03:00 (UTC) : … KEY/USDT») y reanudación el 2023-03-10, 28 días después. No es canje ni redenominación: mismo listado por la regla de 30 días (v3 §2.2.3). Previo a A.
- **T067 NBTUSDT → NBTUSDT:** Corte con reanudación sin anuncio archivado de canje o redenominación: mismo listado (corte < 30 días, v3 §2.2.3).
- **T072 SCRUSDT → SCRUSDT:** Fin del pre-mercado y apertura spot (anuncio archivado: «end the Scroll (SCR) Pre-Market at 2024-10-21 09:00 (UTC) and open spot trading … at 2024-10-22 08:00 (UTC)»). No es canje. Mismo listado (corte de 1 día).
- **T076 USUALUSDT → USUALUSDT:** Corte con reanudación sin anuncio archivado de canje o redenominación: mismo listado (corte < 30 días, v3 §2.2.3).

## Clasificación de los 117 pares del barrido por cuerpo

| Clase | Pares |
|---|---|
| airdrop_o_bifurcacion | 29 |
| regla_1 | 23 |
| canje_mismo_simbolo_r1 | 18 |
| sin_par_usdt_del_viejo | 12 |
| conversion_al_retirar | 12 |
| parte_de | 8 |
| regla_2 | 5 |
| sin_par_usdt_del_nuevo | 4 |
| D1_sin_continuidad_lectura_literal | 3 |
| bifurcacion_un_X_dos_Y | 1 |
| fusion_en_par_existente | 1 |
| conversion_con_solapamiento | 1 |
