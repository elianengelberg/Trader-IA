# Segunda pasada A3.11 · caso por caso

Todas las citas se verificaron literalmente contra el texto archivado local (los scripts abortan si una falta).
Evidencia: **positiva** = el texto o el bucket muestran el hecho; **negativa** = una regla congelada lo excluye; **ausencia de evidencia** = no se encontró nada (no se usa como prueba).

Resultado de `conciliacion.py` (6f764845…) con estas resoluciones: componentes {'i': '2020-05-11', 'ii': '2023-05-12', 'iii': '2019-01-01', 'iv': None}, última falla LINKUPUSDT 2023-05-11 (T), V-S2 49/50, V-S3 revisados 10, pendientes {'C': 0, 'D_sin_evidencia_ni_otro_par': 0, 'sin_fecha': 0, 'sin_par': 12} (las 12 «sin par» no tienen mecanismo en el código: se resuelven abajo).

## 1. Eventos (47 claves; se releyeron todas, no solo las listas de revisión)

| Clave (par · E de la 1.ª pasada) | Cat. 1.ª | Decisión | E según el texto | Certeza | Cita | Fuente (archivo · captura) |
|---|---|---|---|---|---|---|
| CLOAKUSDT|2019-02-22 | fuera_sin_par_usdt_documentado | confirmar | 2019-02-22 | alta | «for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)» | zd_360023570292_80190cd7d137.json · 20190323223148 |
| MODUSDT|2019-02-22 | fuera_sin_par_usdt_documentado | confirmar | 2019-02-22 | alta | «for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)» | zd_360023570292_80190cd7d137.json · 20190323223148 |
| SALTUSDT|2019-02-22 | fuera_sin_par_usdt_documentado | confirmar | 2019-02-22 | alta | «for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)» | zd_360023570292_80190cd7d137.json · 20190323223148 |
| SUBUSDT|2019-02-22 | fuera_sin_par_usdt_documentado | confirmar | 2019-02-22 | alta | «for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)» | zd_360023570292_80190cd7d137.json · 20190323223148 |
| WINGSUSDT|2019-02-22 | fuera_sin_par_usdt_documentado | confirmar | 2019-02-22 | alta | «for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)» | zd_360023570292_80190cd7d137.json · 20190323223148 |
| BCHSVUSDT|2019-04-22 | A | confirmar | 2019-04-22 | alta | «for the following coin on 2019/04/22 at 10:00 AM UTC: Bitcoin SV (BCHSV)» | zd_360026666152_70a328bf3f4b.json · 20190418150212 |
| BEARUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| BNBBEARUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| BNBBULLUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| BULLUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| EOSBEARUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| EOSBULLUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| ETHBEARUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| ETHBULLUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| XRPBEARUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| XRPBULLUSDT|2020-03-31 | A | confirmar | 2020-03-31 | alta | «and will stop trading at 2020/03/31 10:00 AM (UTC)» | zd_360041613471_7f63c6ebd36b.json · 20200605155228 |
| MCOUSDT|2020-10-23 | A | confirmar | 2020-10-23 | alta | «Binance will remove and cease trading on the following trading pairs at 2020/10/23 12:00 PM (UTC): BTS/BUSD, MCO/BTC, MCO/USDT» | bn_1841b3af92f34349a918f80cb8fcc9de_8ff1bf4780bd.json · 20201124034739 |
| HCUSDT|2020-11-10 | A | confirmar | 2020-11-10 | alta | «Binance will remove and cease trading on the following trading pairs at 2020/11/10 12:00 PM (UTC): AION/BUSD, DCR/BUSD, EVX/ETH, HC/USDT» | bn_dcb2722913ee4dec9a8be29da9e3aeb0_b1f63e7c797e.json · 20210227200051 |
| BKRWUSDT|2021-02-19 | T | descartar | 2021-02-19 | alta | «This announcement has been updated on 2021-02-20 to correct the BKRW/USDT trading pair to the USDT/BKRW trading pair» | bn_89c3426b722341269effb0c073b30cdf_4b94fd16208f.json · 20210303065648 |
| HNTUSDT|2022-10-14 | A | confirmar | 2022-10-14 | alta | «Binance will remove and cease trading on the following trading pairs at 2022-10-14 03:00 (UTC) : Spot Pairs : HNT/BTC, HNT/USDT» | url_https___www.binance.com_en_support_announcement_notice-o · 20221128155640 |
| FTTUSDT|2022-11-15 | A | confirmar | 2022-11-15 | alta | «Binance will remove and cease trading on the following trading pairs at 2022-11-15 04:30 (UTC) : Spot Pairs : FTT/BNB, FTT/BTC, FTT/ETH and FTT/USDT» | url_https___www.binance.com_en_support_announcement_notice-o · 20221208104318 |
| AUTOUSDT|2023-04-18 | A | confirmar | 2023-04-18 | alta | «for the following tokens at 2023-04-18 03:00 (UTC) : Kepple (QLC) Neblio (NEBL) Auto» | url_https___www.binance.com_en_support_announcement_binance- · 20230927092116 |
| NEBLUSDT|2023-04-18 | A | confirmar | 2023-04-18 | alta | «for the following tokens at 2023-04-18 03:00 (UTC) : Kepple (QLC) Neblio (NEBL) Auto» | url_https___www.binance.com_en_support_announcement_binance- · 20230927092116 |
| DOTDOWNUSDT|2023-04-27 | T | fecha_corregida | 2023-05-10 | alta | «At 2023-05-10 06:00 (UTC) : DOTUP, DOTDOWN» | url_https___www.binance.com_en_support_announcement_binance- · 20240810193751 |
| DOTUPUSDT|2023-04-27 | T | fecha_corregida | 2023-05-10 | alta | «At 2023-05-10 06:00 (UTC) : DOTUP, DOTDOWN» | url_https___www.binance.com_en_support_announcement_binance- · 20240810193751 |
| LINKUPUSDT|2023-04-27 | B | fecha_corregida | 2023-05-11 | alta | «At 2023-05-11 06:00 (UTC) : LINKUP, LINKDOWN» | url_https___www.binance.com_en_support_announcement_binance- · 20240810193751 |
| TRXDOWNUSDT|2023-04-27 | T | fecha_corregida | 2023-05-09 | alta | «At 2023-05-09 06:00 (UTC) : TRXUP, TRXDOWN» | url_https___www.binance.com_en_support_announcement_binance- · 20240810193751 |
| AUDUSDT|2023-06-01 | A | confirmar | 2023-06-01 | alta | «Binance will remove and cease trading on the following spot trading pairs at 2023-06-01 06:00 (UTC): Spot Pairs: ADA/AUD, AUD/BUSD, AUD/USDT» | url_https___www.binance.com_en_support_announcement_notice-o · 20230921100939 |
| YFIIUSDT|2023-08-22 | A | confirmar | 2023-08-22 | alta | «for the following tokens at 2023-08-22 03:00 (UTC) : Sonm (SNM) Serum (SRM) DFI.Mone» | url_https___www.binance.com_en_support_announcement_binance- · 20241102104255 |
| ARKUSDT|2023-09-22 | C_no_explicada | C_explicada | 2023-09-22 | alta | «Binance will open trading for the ARK/USDT, CREAM/USDT, FTT/USDT, GFT/USDT, IQ/USDT» | url_https___www.binance.com_en_support_announcement_notice-o · 20231204155528 |
| CREAMUSDT|2023-09-22 | C_no_explicada | C_explicada | 2023-09-22 | alta | «Binance will open trading for the ARK/USDT, CREAM/USDT, FTT/USDT, GFT/USDT, IQ/USDT» | url_https___www.binance.com_en_support_announcement_notice-o · 20231204155528 |
| FTTUSDT|2023-09-22 | C_no_explicada | C_explicada | 2023-09-22 | alta | «Binance will open trading for the ARK/USDT, CREAM/USDT, FTT/USDT, GFT/USDT, IQ/USDT» | url_https___www.binance.com_en_support_announcement_notice-o · 20231204155528 |
| GFTUSDT|2023-09-22 | C_no_explicada | C_explicada | 2023-09-22 | alta | «Binance will open trading for the ARK/USDT, CREAM/USDT, FTT/USDT, GFT/USDT, IQ/USDT» | url_https___www.binance.com_en_support_announcement_notice-o · 20231204155528 |
| IQUSDT|2023-09-22 | C_no_explicada | C_explicada | 2023-09-22 | alta | «Binance will open trading for the ARK/USDT, CREAM/USDT, FTT/USDT, GFT/USDT, IQ/USDT» | url_https___www.binance.com_en_support_announcement_notice-o · 20231204155528 |
| BTSUSDT|2023-12-07 | A | confirmar | 2023-12-07 | alta | «for the following token(s) at 2023-12-07 03:00 (UTC) : BitShares (BTS) PERL.eco (PER» | url_https___www.binance.com_en_support_announcement_binance- · 20240226113614 |
| PERLUSDT|2023-12-07 | A | confirmar | 2023-12-07 | alta | «for the following token(s) at 2023-12-07 03:00 (UTC) : BitShares (BTS) PERL.eco (PER» | url_https___www.binance.com_en_support_announcement_binance- · 20240226113614 |
| WTCUSDT|2023-12-07 | A | confirmar | 2023-12-07 | alta | «for the following token(s) at 2023-12-07 03:00 (UTC) : BitShares (BTS) PERL.eco (PER» | url_https___www.binance.com_en_support_announcement_binance- · 20240226113614 |
| ANTUSDT|2024-02-20 | A | confirmar | 2024-02-20 | alta | «for the following token(s) at 2024-02-20 03:00 (UTC) : Aragon (ANT) Multichain (MULT» | url_https___www.binance.com_en_support_announcement_binance- · 20240222002333 |
| MULTIUSDT|2024-02-20 | A | confirmar | 2024-02-20 | alta | «for the following token(s) at 2024-02-20 03:00 (UTC) : Aragon (ANT) Multichain (MULT» | url_https___www.binance.com_en_support_announcement_binance- · 20240222002333 |
| XMRUSDT|2024-02-20 | A | confirmar | 2024-02-20 | alta | «for the following token(s) at 2024-02-20 03:00 (UTC) : Aragon (ANT) Multichain (MULT» | url_https___www.binance.com_en_support_announcement_binance- · 20240222002333 |
| BONDUSDT|2024-07-22 | A | confirmar | 2024-07-22 | alta | «on all spot trading pairs for the following token(s) at 2024-07-22 03:00 (UTC) : BarnBridge (BOND) Dock (» | url_https___www.binance.com_en_support_announcement_binance- · 20240809061308 |
| DOCKUSDT|2024-07-22 | A | confirmar | 2024-07-22 | alta | «on all spot trading pairs for the following token(s) at 2024-07-22 03:00 (UTC) : BarnBridge (BOND) Dock (» | url_https___www.binance.com_en_support_announcement_binance- · 20240809061308 |
| MDXUSDT|2024-07-22 | A | confirmar | 2024-07-22 | alta | «on all spot trading pairs for the following token(s) at 2024-07-22 03:00 (UTC) : BarnBridge (BOND) Dock (» | url_https___www.binance.com_en_support_announcement_binance- · 20240809061308 |
| POLSUSDT|2024-07-22 | A | confirmar | 2024-07-22 | alta | «on all spot trading pairs for the following token(s) at 2024-07-22 03:00 (UTC) : BarnBridge (BOND) Dock (» | url_https___www.binance.com_en_support_announcement_binance- · 20240809061308 |
| KP3RUSDT|2024-11-06 | A | confirmar | 2024-11-06 | alta | «on all spot trading pairs for the following token(s) at 2024-11-06 03:00 (UTC) : Rupiah Token (IDRT) Keep» | url_https___www.binance.com_en_support_announcement_binance- · 20241207230630 |
| OOKIUSDT|2024-11-06 | A | confirmar | 2024-11-06 | alta | «on all spot trading pairs for the following token(s) at 2024-11-06 03:00 (UTC) : Rupiah Token (IDRT) Keep» | url_https___www.binance.com_en_support_announcement_binance- · 20241207230630 |
| UNFIUSDT|2024-11-06 | A | confirmar | 2024-11-06 | alta | «on all spot trading pairs for the following token(s) at 2024-11-06 03:00 (UTC) : Rupiah Token (IDRT) Keep» | url_https___www.binance.com_en_support_announcement_binance- · 20241207230630 |

Justificaciones por tipo de decisión:
- **C_explicada**: A3.5 (b): el texto agrega (abre) el par USDT en esa fecha; lo que remueve son los pares BUSD. Relisting documentado; no es una exclusión del par USDT.
- **confirmar**: El texto archivado fija la misma fecha de cese de la negociación spot que la primera pasada (N5).
- **descartar**: El propio anuncio corrige el par: el removido es USDT/BKRW (otro símbolo), no BKRW/USDT. Error de identificación del par.
- **fecha_corregida**: La primera pasada tomó la fecha del título (fecha de publicación, A3.1.5); el cuerpo fija el cese de la negociación del par en otra fecha. Se aplica N5: E = día UTC en que cesa la negociación spot según el texto.

## 2. Filas sin fecha (8 = BCN, CHAT, ICN, TRIG × 2 URL)

| Fila | E | Cita | Fuente | Decisión |
|---|---|---|---|---|
| BCNUSDT · ance.com/en/support/announcement/360017720731 | 2018-10-12 | «for the following coins and tokens at 2018/10/12 10:00 AM (UTC)» | url_https___www.binance.com_en_support_announcemen · 20210729084627 | A3.4.1: el cuerpo fija el cese (fecha explícita). Ningún par USDT del token en el bucket: sigue fuera del universo por A3.3.2. |
| CHATUSDT · ance.com/en/support/announcement/360017720731 | 2018-10-12 | «for the following coins and tokens at 2018/10/12 10:00 AM (UTC)» | url_https___www.binance.com_en_support_announcemen · 20210729084627 | A3.4.1: el cuerpo fija el cese (fecha explícita). Ningún par USDT del token en el bucket: sigue fuera del universo por A3.3.2. |
| ICNUSDT · ance.com/en/support/announcement/360017720731 | 2018-10-12 | «for the following coins and tokens at 2018/10/12 10:00 AM (UTC)» | url_https___www.binance.com_en_support_announcemen · 20210729084627 | A3.4.1: el cuerpo fija el cese (fecha explícita). Ningún par USDT del token en el bucket: sigue fuera del universo por A3.3.2. |
| TRIGUSDT · ance.com/en/support/announcement/360017720731 | 2018-10-12 | «for the following coins and tokens at 2018/10/12 10:00 AM (UTC)» | url_https___www.binance.com_en_support_announcemen · 20210729084627 | A3.4.1: el cuerpo fija el cese (fecha explícita). Ningún par USDT del token en el bucket: sigue fuera del universo por A3.3.2. |
| BCNUSDT · c/en-us/articles/360017720731?refer=coinsosik | 2018-10-12 | «for the following coins and tokens at 2018/10/12 10:00 AM (UTC)» | zd_360017720731_f8ac092ad057.json · 20181017200529 | A3.4.1: el cuerpo fija el cese (fecha explícita). Ningún par USDT del token en el bucket: sigue fuera del universo por A3.3.2. |
| CHATUSDT · c/en-us/articles/360017720731?refer=coinsosik | 2018-10-12 | «for the following coins and tokens at 2018/10/12 10:00 AM (UTC)» | zd_360017720731_f8ac092ad057.json · 20181017200529 | A3.4.1: el cuerpo fija el cese (fecha explícita). Ningún par USDT del token en el bucket: sigue fuera del universo por A3.3.2. |
| ICNUSDT · c/en-us/articles/360017720731?refer=coinsosik | 2018-10-12 | «for the following coins and tokens at 2018/10/12 10:00 AM (UTC)» | zd_360017720731_f8ac092ad057.json · 20181017200529 | A3.4.1: el cuerpo fija el cese (fecha explícita). Ningún par USDT del token en el bucket: sigue fuera del universo por A3.3.2. |
| TRIGUSDT · c/en-us/articles/360017720731?refer=coinsosik | 2018-10-12 | «for the following coins and tokens at 2018/10/12 10:00 AM (UTC)» | zd_360017720731_f8ac092ad057.json · 20181017200529 | A3.4.1: el cuerpo fija el cese (fecha explícita). Ningún par USDT del token en el bucket: sigue fuera del universo por A3.3.2. |

## 3. Eventos omitidos por la extracción (mismo anuncio que DOTUP, DOTDOWN, TRXDOWN y LINKUP)

| Par | E | Categoría (función congelada `clasificar`) | L | Uso |
|---|---|---|---|---|
| TRXUPUSDT | 2023-05-09 | T | 2022-11-28 | Se suman a (ii) y (ii′) como fallas; no mueven el inicio (E ≤ 2023-05-11) |
| LINKDOWNUSDT | 2023-05-11 | T | 2023-04-05 | Se suman a (ii) y (ii′) como fallas; no mueven el inicio (E ≤ 2023-05-11) |

Cita: «Binance will delist and cease redemption for the TRXUP, TRXDOWN, DOTUP, DOTDOWN, LINKUP and LINKDOWN leveraged tokens at the following timings: At 2023-05-09 06:00 (UTC) : TRXUP, TRXDOWN At 2023-05-10 06:00 (UTC) : DOTUP, DOTDOWN At 2023-05-11 06:00 (UTC) : LINKUP, LINKDOWN» (datos_anuncios/commoncrawl/paginas/url_https___www.binance.com_en_support_announcement_binance-to-delist-and-cease-_6079c69de2a3.json (captura 20240810193751)).

## 4. Las 12 filas «sin par» (sin par extraído ni lista de pares)

| URL (fragmento) | Tipo | Decisión | Certeza | Cita | Captura |
|---|---|---|---|---|---|
| …port/announcement/0a17fc70baad496aa2bbc47661aa6727 | canje de token (COVER-old → COVER-new) | Sin evento: canje 1:1 del mismo token; COVERUSDT no figura en el bucket | alta | «1 COVER-old = 1 COVER-new» | 20210413011543 |
| …port/announcement/52712c5af7284587b4e7dd2279a670d1 | remoción de pares | Fuera del universo: el texto lista los pares y ninguno es contra USDT (A3.2) | alta | «Binance will remove and cease trading on the following trading pairs at 2021-09-09 12:00 PM (UTC): AAVEBRL, EOSAUD, ICPR» | 20211204022729 |
| …port/announcement/a6e9bfe3106f4390abf96622139db6d8 | conversión posterior a exclusiones ya ocurridas | Sin evento nuevo: convierte saldos de tokens ya excluidos | alta | «Binance will perform a conversion of delisted tokens to BUSD» | 20210926015326 |
| …port/announcement/f45dde7da58b473aa885349946bed269 | cambio de API | Descartado: no es un token ni un par (error de extracción) | alta | «Binance will delist all WAPI endpoints from the Binance API at 2021-08-01 2:00 AM (UTC)» | 20210619043246 |
| …ng-wapi-endpoints-f45dde7da58b473aa885349946bed269 | cambio de API (duplicado) | Descartado: no es un token ni un par (error de extracción) | alta | «Binance will delist all WAPI endpoints from the Binance API» | 20221208173235 |
| …w.binance.com/en/support/announcement/360026666152 | exclusión de token (captura duplicada) | Cubierto por el evento BCHSVUSDT|2019-04-22 (categoría A) | alta | «for the following coin on 2019/04/22 at 10:00 AM UTC: Bitcoin SV (BCHSV)» | 20210622234107 |
| …w.binance.com/en/support/announcement/360041278332 | aviso posterior a la exclusión | Cubierto por los 10 eventos FTX del 2020-03-31 (categoría A) | alta | «Binance has now delisted all FTX leveraged tokens including BULL, BEAR, ETHBULL, ETHBEAR» | 20210805011125 |
| …aged-Tokens-and-Will-Complete-Distribution-of-BUSD | aviso posterior a la exclusión (duplicado) | Cubierto por los 10 eventos FTX del 2020-03-31 (categoría A) | alta | «Binance has now delisted all FTX leveraged tokens» | 20200605170300 |
| …inance.com/en/support/announcement/c-161?navId=161 | página índice de la sección | Descartado: solo navegación, sin contenido de anuncio. La ausencia de contenido no prueba que no hubo eventos | alta | «Delisting» | 20220528082306 |
| …/en/support/announcement/delisting?c=161&navId=161 | página índice de la sección | Descartado: solo navegación, sin contenido de anuncio. La ausencia de contenido no prueba que no hubo eventos | alta | «Delisting» | 20221127121631 |
| …ed-tokens-to-usdt-9972ee7df32144d099c78c7df39011a2 | reapertura de retiros y conversión de 12 tokens ya excluidos | Sin evento nuevo; cada token se revisa abajo (A3.3) | alta | «Binance will re-open withdrawals for the following 12 delisted tokens» | 20240304105357 |
| …o-usdc-2024-08-12-9ec5cabbc8974a1c8890e1c9d87a98a7 | conversión de 15 tokens ya excluidos | Sin evento nuevo; cada token se revisa abajo (A3.3) | alta | «Binance will perform a conversion of the below tokens to USDC» | 20240909104852 |

## 5. Tokens de los dos avisos de conversión (2023-12-04 y 2024-08-12), incluidos NSBT, SGB, SOLO y XYM

| Aviso | Token | USDT en bucket | Otros pares en bucket | Evidencia USDT en páginas | Decisión | Evidencia |
|---|---|---|---|---|---|---|
| 2023-12-04 | AION | sí | AIONBNB, AIONBTC, AIONBUSD, AIONETH | 3 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2023-12-04 | BEAM | sí | BEAMBNB, BEAMBTC | 3 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2023-12-04 | BCD | no | BCDBTC, BCDETH | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2023-12-04 | GO | no | GOBNB, GOBTC | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2023-12-04 | NEBL | sí | NEBLBNB, NEBLBTC, NEBLBUSD, NEBLETH | 2 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2023-12-04 | NAS | no | NASBNB, NASBTC, NASETH | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2023-12-04 | NSBT | no | — | 0 | A3.3.3, lectura manual: el archivo identifica el token como distribuido por airdrop; ninguna página menciona un par de negociación spot. No es D | positiva de airdrop; ausencia de evidencia de negociación spot (no se toma como prueba de que no existió) |
| 2023-12-04 | NXS | no | NXSBNB, NXSBTC, NXSETH | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2023-12-04 | VIA | no | VIABNB, VIABTC, VIAETH | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2023-12-04 | SKY | sí | SKYBNB, SKYBTC, SKYETH, SKYTRY | 0 | A3.3.2: el SKYUSDT del bucket empieza el 2025-09-17, casi dos años después del aviso: es otro activo (cambio de símbolo MKR→SKY). Para Skycoin no hay evidencia de par USDT y sí otros pares en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla; certeza media-alta (la identidad del SKYUSDT de 2025 se infiere de la actividad) |
| 2023-12-04 | SGB | no | — | 0 | A3.3.3, lectura manual: el archivo identifica el token como distribuido por airdrop; ninguna página menciona un par de negociación spot. No es D | positiva de airdrop; ausencia de evidencia de negociación spot (no se toma como prueba de que no existió) |
| 2023-12-04 | YOYO | no | YOYOBNB, YOYOBTC, YOYOETH | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2024-08-12 | BTG | sí | BTGBTC, BTGBUSD, BTGETH | 3 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2024-08-12 | BTCST | sí | BTCSTBTC, BTCSTBUSD | 3 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2024-08-12 | BTS | sí | BTSBNB, BTSBTC, BTSBUSD, BTSETH | 3 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2024-08-12 | DNT | sí | DNTBTC, DNTBUSD, DNTETH | 2 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2024-08-12 | GRS | no | GRSBTC, GRSETH | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2024-08-12 | HEGIC | no | HEGICBUSD, HEGICETH | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2024-08-12 | MOB | sí | MOBBTC, MOBBUSD | 3 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2024-08-12 | XMR | sí | XMRBNB, XMRBTC, XMRBUSD, XMRETH | 3 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2024-08-12 | MTH | no | MTHBTC, MTHETH | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2024-08-12 | MULTI | sí | MULTIBTC, MULTIBUSD | 2 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
| 2024-08-12 | NAV | no | NAVBNB, NAVBTC, NAVETH | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2024-08-12 | SOLO | no | — | 0 | A3.3.3, lectura manual: el archivo identifica el token como distribuido por airdrop; ninguna página menciona un par de negociación spot. No es D | positiva de airdrop; ausencia de evidencia de negociación spot (no se toma como prueba de que no existió) |
| 2024-08-12 | SPARTA | no | SPARTABNB | 0 | A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo) | negativa por regla (el bucket conserva pares retirados) |
| 2024-08-12 | XYM | no | — | 0 | A3.3.3, lectura manual: el archivo identifica el token como distribuido por airdrop; ninguna página menciona un par de negociación spot. No es D | positiva de airdrop; ausencia de evidencia de negociación spot (no se toma como prueba de que no existió) |
| 2024-08-12 | TRIBE | sí | TRIBEBNB, TRIBEBTC, TRIBEBUSD | 3 | Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R) | positiva (par en Vision) |
- **NSBT**: «The QiSwap (QI) and Neutrino Token (NSBT) airdrop programs were complete» (bn_c890d42730f44cc082ba5d1f927689bf_0373e66395ea.json, captura 20211028184120). Pares mencionados en el archivo: ninguno.
- **SGB**: «Binance will support the Songbird (SGB) Airdrop Program for XRP (XRP) holders» (bn_4acc20ea6da14660a61f84b862afc1ed_59387378b62f.json, captura 20211202065539). Pares mencionados en el archivo: ninguno.
- **SOLO**: «Binance will support the Sologenic (SOLO) Airdrop Program for XRP (XRP) holders» (url_https___www.binance.com_en_support_announcement_binance-, captura 20230921161716). Pares mencionados en el archivo: ninguno.
- **XYM**: «When Binance performs the snapshot on users’ NEM (XEM) holdings for the Symbol (XYM) airdrop» (bn_17aaa4d4b0884875b241e85199e8bf61_ce99af404598.json, captura 20210418154058). Pares mencionados en el archivo: ninguno.

## 6. Controles de muestreo

- **V-S2** (1 desacierto, ETHBEARUSDT|2020-01-17): Sin corrección. El texto de listado es correcto (apertura 2020-01-17); el primer día activo del bucket es 2020-02-03 porque hubo una suspensión documentada en otro anuncio archivado (reanudación 2020-02-03). El par y la fecha extraídos no estaban mal, así que A3.6 no permite corregir: sigue siendo un desacierto (49/50 = 98 % ≥ 95 %).
- **V-S3**: la muestra de la primera pasada (10) se revisó completa; el código congelado vuelve a sortear sobre el universo de la segunda pasada y los 10 sorteados también tienen revisión (se revisaron los 47 eventos). Resultado: 10/10 revisados.

## 7. Renombres (164 candidatos) — ver `../renombres/CLASIFICACION_RENOMBRES.md`
