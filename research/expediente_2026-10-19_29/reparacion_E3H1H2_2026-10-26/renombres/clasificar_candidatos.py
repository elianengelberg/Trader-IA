"""E3 · A3.11 y Adenda 1: clasificación manual de los 164 candidatos de renombre (115 títulos únicos) y tabla de mapeos.

Para cada título se fija a mano: tipo, símbolos, relación de canje, fecha de cese del viejo y de apertura del nuevo
según el texto, decisión, regla aplicada y certeza. El script:
  - agrupa los 164 candidatos por título y exige una decisión para cada uno (si falta alguna, aborta);
  - verifica que cada cita aparezca literalmente en el texto archivado (cuerpo o página) de algún candidato del título;
  - cruza cada mapeo con la actividad del bucket (episodios derivados de `estado`; sin precios);
  - agrega los renombres que la extracción no clasificó (BCHABC→BCH, XZC→FIRO) y los cortes y cambios de símbolo sin anuncio.
Uso: python -I clasificar_candidatos.py <dir_ejecucion_E3> <salida.json> <salida.md>
"""
import datetime as dt
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

E3, SAL_J, SAL_M = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CC = E3 / "datos_anuncios" / "commoncrawl"


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


ren = json.loads((CC / "renombres_candidatos.json").read_text())
usdt = set(json.loads((E3 / "datos_vision" / "listados" / "simbolos_usdt.json").read_text()))
aud = {a["simbolo"]: a for a in json.loads((E3 / "resultados" / "calidad" / "auditoria_por_simbolo.json").read_text())}
texto_pagina = {}
for f in (CC / "paginas").glob("*.json"):
    d = json.loads(f.read_text())
    texto_pagina[f.name] = norm(d.get("texto", ""))
    texto_pagina.setdefault("url:" + d["url"], texto_pagina[f.name])

# Tipos
MISMO = "canje_mismo_simbolo"         # canje de red o de contrato, mismo ticker, sin cambio de unidades ni corte de negociación anunciado
LISTADO = "listado_con_canje"         # el título agrega un par USDT y menciona un canje de red del mismo ticker
RENOMBRE = "renombre"                 # X → Y (Adenda 1, regla 1)
REDENOM = "redenominacion"            # X → X con r ≠ 1 (Adenda 1, regla 2)
NO_REN = "no_es_renombre"
# Decisiones
M1, M2 = "mapeo_regla_1", "mapeo_regla_2"
SIN_MAPEO = "sin_mapeo_necesario"
SIN_USDT = "registrado_sin_par_usdt"  # renombre o redenominación válidos, pero el viejo no tiene par USDT en el bucket: no afecta al universo
REMITE = "remite_a"                   # anuncio complementario (actualización o finalización) de otro título
DESC = "descartado"

# título (prefijo) → decisión.  r = unidades nuevas por unidad vieja (precio continuo: P_nuevo ≈ P_viejo / r)
D = OrderedDict()


def d(titulo, tipo, decision, cita, certeza="alta", **kw):
    D[titulo] = {"tipo": tipo, "decision": decision, "cita": cita, "certeza": certeza, **kw}


d("Binance Will Support EOS MainNet Token Swap", MISMO, SIN_MAPEO, "we will support the EOS MainNet Token Swap")
d("Binance Adds EOS/BNB, EOS/USDT Trading Pairs and EOS Mainnet Swap Update", LISTADO, SIN_MAPEO, "Binance will open trading for EOS/BNB and EOS/USDT trading pairs at 2018/05/28 05:00 AM (UTC)")
d("EOS Mainnet Swap Update", MISMO, SIN_MAPEO, "Binance will reopen EOS deposits until 2018/06/02 4:00 PM UTC")
d("Binance Supports ONT Mainnet Swap and Adds ONT/USDT Trading Pair", LISTADO, SIN_MAPEO, "Binance will also open trading for ONT/USDT trading pair at 2018/06/08 7:00 AM (UTC)")
d("Binance Supports TRX Mainnet Swap and Adds TRX/USDT Trading Pair", LISTADO, SIN_MAPEO, "Binance will also open trading for TRX/USDT trading pair at 2018/06/11 11:30 AM (UTC)")
d("Binance Supports ICX Mainnet Swap and Adds ICX/USDT Trading Pair", LISTADO, SIN_MAPEO, "Binance will also open trading for the ICX/USDT trading pair at 2018/06/13 8:00 AM (UTC)")
d("Binance Supports VEN Mainnet Swap and Adds VEN/USDT Trading Pair", LISTADO, SIN_MAPEO, "Binance will also open trading for the VEN/USDT trading pair at 2018/06/22 8:00 AM (UTC)")
d("Binance Completes TRX and ICX Mainnet Swaps", MISMO, SIN_MAPEO, "Binance has completed the TRX and ICX mainnet swaps")
d("Information Regarding the Upcoming VEN/VET Mainnet Swap", RENOMBRE, M1, "at a ratio of 1 VEN = 100 VET",
  viejo="VEN", nuevo="VET", r=100, E="2018-07-23", apertura="2018-07-25")
d("Binance Supports NULS Mainnet Swap and Adds NULS/USDT Trading Pair", LISTADO, SIN_MAPEO, "Binance will also open trading for the NULS/USDT trading pair at 2018/07/23 4:00 AM (UTC)")
d("Binance Completes VEN Mainnet Swap to VET", RENOMBRE, REMITE, "based on a ratio of 1 VEN = 100 VET", remite="Information Regarding the Upcoming VEN/VET Mainnet Swap")
d("Binance Completes ONT Mainnet Swap", MISMO, SIN_MAPEO, "Binance has completed the Ontology (ONT) mainnet swap")
d("Binance Supports Hcash (HSR) Mainnet Swap to HyperCash (HC)", RENOMBRE, SIN_USDT, "at a ratio of 1 HSR = 1 HC", viejo="HSR", nuevo="HC", r=1, E="2018-08-08")
d("Binance Supports Red Pulse (RPX) Token Swap to PHOENIX (PHX)", RENOMBRE, SIN_USDT, "at a ratio of 1 RPX = 1 PHX", viejo="RPX", nuevo="PHX", r=1, E="2018-08-14")
d("Binance Will Support YOYOW (YOYO) MainNet Token Swap", MISMO, SIN_MAPEO, "Deposits and withdrawals of YOYO will be suspended starting from 2018/08/08 4:00 AM (UTC)")
d("Binance Completes YOYO Mainnet Swap", MISMO, SIN_MAPEO, "Binance has completed the YOYOW (YOYO) mainnet swap")
d("Binance Completes HSR to HC Mainnet Swap and Opens Trading", RENOMBRE, REMITE, "We will open trading for HC/BTC and HC/ETH trading pairs at 2018/08/21 10:00 AM (UTC)", remite="Binance Supports Hcash (HSR) Mainnet Swap to HyperCash (HC)")
d("Binance Will Support Nuls (NULS) Mainnet Token Swap", MISMO, SIN_MAPEO, "Deposits and withdrawals of NULS will be suspended starting from 2018/08/22 10:00 AM (UTC)")
d("Binance Will Support CyberMiles (CMT) Mainnet Token Swap", MISMO, SIN_MAPEO, "Deposits and withdrawals of CMT will be suspended starting from 2018/10/08 4:00 AM (UTC)")
d("Binance Will Support AION (AION) Mainnet Token Swap", MISMO, SIN_MAPEO, "Deposits and withdrawals of AION will be suspended starting from 2018/10/15 10:00 AM (UTC)")
d("Binance Completes AION Mainnet Swap", MISMO, SIN_MAPEO, "Binance has completed the Aion (AION) mainnet swap")
d("Binance Completes CMT Mainnet Swap", MISMO, SIN_MAPEO, "Binance has completed the CyberMiles (CMT) mainnet swap")
d("Binance Will Support The Theta Network (THETA) Mainnet Token Swap and Distribution of TFUEL", MISMO, SIN_MAPEO, "Deposits and withdrawals of THETA will be suspended starting from 2019/03/12 0:00 AM (UTC)")
d("Binance Will Support The IOST Mainnet Token Swap", MISMO, SIN_MAPEO, "will suspend withdrawals for IOST starting from 2019/03/08 0:00 AM (UTC)")
d("Binance Completes THETA Mainnet Swap and Opens Deposits / Withdrawals", MISMO, SIN_MAPEO, "Binance has completed the Theta Network (THETA) mainnet swap")
d("Binance Will Support the ZIL Mainnet Token Swap", MISMO, SIN_MAPEO, "will suspend deposits and withdrawals of ZIL starting from 2019/04/22 0:00 AM (UTC)")
d("Binance Completes BNB Mainnet Swap and Opens Deposits / Withdrawals", MISMO, SIN_MAPEO, "Binance has completed the Binance Coin (BNB) mainnet swap")
d("Binance Will Support the Mithril (MITH) Token Migration to Binance Chain", MISMO, SIN_MAPEO, "token migration of ERC20 MITH tokens to BEP2 MITH tokens on Binance Chain")
d("Binance Has Completed the MITH Token Migration and Has Opened Deposits / Withdrawals", MISMO, SIN_MAPEO, "Binance has completed the Mithril (MITH) token migration to Binance Chain")
d("Binance Will Support the AE Mainnet Token Swap", MISMO, SIN_MAPEO, "confirm support for the upcoming AE mainnet token swap")
d("Binance Will Support the Red Pulse Phoenix (PHX) Token Migration to Binance Chain", RENOMBRE, SIN_USDT, "ratio of 1 PHX = 1 PHB", viejo="PHX", nuevo="PHB", r=1, E="2019-05-22")
d("Binance Will Support the BCPT, GTO and ARN Token Migration to Binance Chain", MISMO, SIN_MAPEO, "token migration of ERC20 BCPT, GTO and ARN tokens to BEP2 BCPT, GTO and ARN tokens on Binance Chain")
d("Binance Will Support the IOTX Mainnet Token Swap", MISMO, SIN_MAPEO, "will suspend withdrawals for IOTX starting from 2020/01/15 0:00 AM (UTC)")
d("Binance Will Support the WTC Mainnet Token Swap", MISMO, SIN_MAPEO, "will suspend withdrawals for WTC starting from 2020/01/20 0:00 AM (UTC)")
d("Notice Regarding Zilliqa Mainnet Token Swap Deadline", MISMO, SIN_MAPEO, "the deadline for the Zilliqa token swap from ERC20 ZIL to Mainnet ZIL has been set at 2020/02/15")
d("Binance Completes Mainnet Swaps and Opens Deposits & Withdrawals for IOTX & WTC", MISMO, SIN_MAPEO, "Binance has completed the mainnet swaps for IOTX and WTC")
d("Binance Will Support the Harmony (ONE) Mainnet Token Swap", MISMO, SIN_MAPEO, "will suspend withdrawals for ONE starting from 2020/02/03 02:00 AM (UTC)")
d("Binance Completes Harmony (ONE) Mainnet Swap and Opens Deposits & Withdrawals for ONE", MISMO, SIN_MAPEO, "Binance has completed the mainnet swap for Harmony (ONE)")
d("Binance Will Support the COCOS Mainnet Token Swap", MISMO, SIN_MAPEO, "will suspend withdrawals for COCOS starting from 2020/03/23 2:00 AM (UTC)")
d("Binance Completes Cocos-BCX (COCOS) Mainnet Swap and Opens Deposits & Withdrawals", MISMO, SIN_MAPEO, "Binance has completed the mainnet swap for Cocos-BCX (COCOS)")
d("Storm (STORM) Token Swap to STMX Will Be Supported on Binance", RENOMBRE, M1, "at a ratio of 1 STORM = 1 STMX",
  viejo="STORM", nuevo="STMX", r=1, E="2020-06-08", apertura="2020-06-11")
d("Augur (REP) Token Swap to Augur (REPV2) Will Be Supported on Binance", NO_REN, REMITE, "at a ratio of 1 REP = 1 REPV2",
  remite="Updates to the Augur (REP) Token Swap on Binance", nota="Plan reemplazado al día siguiente: el ticker siguió siendo REP; REPV2USDT no está en el bucket.")
d("Updates to the Augur (REP) Token Swap on Binance", MISMO, SIN_MAPEO, "The ticker will remain as REP and will not be updated to REPV2")
d("Binance Will List Polkadot (DOT) & Support 1:100 Redenomination Plan", LISTADO, SIN_MAPEO, "the DOT tokens traded on Binance will only be the post-redenominated DOT tokens",
  nota="La redenominación ocurrió en la red; en Binance solo se negoció el DOT redenominado: no hay discontinuidad en la serie.")
d("Binance Will Support the Enigma (ENG) Mainnet Swap", RENOMBRE, SIN_USDT, "the Enigma (ENG) mainnet swap to Secret Network (SCRT)", viejo="ENG", nuevo="SCRT", r=None)
d("Elrond (ERD) Mainnet & Token Swap to Elrond Gold (EGLD) Will Be Supported on Binance", RENOMBRE, M1, "at a ratio of 1000 ERD = 1 EGLD",
  viejo="ERD", nuevo="EGLD", r=0.001, E="2020-08-31", apertura="2020-09-03")
d("Binance Will Support the Ambrosus (AMB) Mainnet Swap", MISMO, SIN_MAPEO, "confirm support for the Ambrosus (AMB) mainnet token swap")
d("Binance Completes Elrond (ERD) Mainnet & Token Swap to Elrond Gold (EGLD)", RENOMBRE, REMITE, "All EGLD has been distributed at a rate of 1,000 ERD = 1 EGLD",
  remite="Elrond (ERD) Mainnet & Token Swap to Elrond Gold (EGLD) Will Be Supported on Binance")
d("Binance Completes the Enigma (ENG) to Secret Network (SCRT) Token Swap and Opens Deposits & Withdrawals", RENOMBRE, REMITE,
  "Users will be able to use the convert function to swap their ENG for SCRT tokens", remite="Binance Will Support the Enigma (ENG) Mainnet Swap")
d("Aave (LEND) Token Swap to AAVE Will Be Supported on Binance With Various Service Updates & Settlements", RENOMBRE, M1, "at a ratio of 100 LEND = 1 AAVE",
  viejo="LEND", nuevo="AAVE", r=0.01, E="2020-10-12", apertura="2020-10-15")
d("Fetch.ai (FET) Smart Contract Swap Supported on Binance", MISMO, SIN_MAPEO, "Deposits and withdrawals of FET will be suspended starting from 2020/10/14 10:00 AM (UTC)")
d("Binance has Completed the Ocean Protocol (OCEAN) & Chromia (CHR) Token Swaps", MISMO, SIN_MAPEO, "Binance has completed the OCEAN and CHR token swaps")
d("Binance Will Support the Aragon (ANT) Smart Contract Swap & Upgrade", MISMO, SIN_MAPEO, "swap their Old ANT (ANTOLD) for New ANT tokens (ANT)")
d("Stratis (STRAT) Token Swap to STRAX Will Be Supported on Binance", RENOMBRE, M1, "at a ratio of 1 STRAT = 1 STRAX",
  viejo="STRAT", nuevo="STRAX", r=1, E="2020-11-12", apertura="2020-11-18")
d("Binance Completes Ambrosus (AMB) Mainnet Swap", MISMO, SIN_MAPEO, "will automatically convert these to mainnet tokens")
d("Binance Will Support Golem (GNT) Token Swap to GLM", RENOMBRE, SIN_USDT, "at a ratio of 1 GNT = 1 GLM", viejo="GNT", nuevo="GLM", r=1, E="2020-12-07")
d("Binance Completes Stratis (STRAX) Token Swap", RENOMBRE, REMITE, "Binance has completed token swap for Stratis (STRAX)", remite="Stratis (STRAT) Token Swap to STRAX Will Be Supported on Binance")
d("Binance Will Support the Dock (DOCK) Mainnet Swap", MISMO, SIN_MAPEO, "More details will be released in a future announcement once the tech integration is complete")
d("Binance Will Support the Cocos-BCX (COCOS) 1,000:1 Redenomination Plan", REDENOM, M2, "begin swapping the old COCOS tokens with the new COCOS tokens at a ratio of 1,000:1",
  viejo="COCOS", nuevo="COCOS", r=0.001, E="2021-01-19", apertura="2021-01-23")
d("Binance Will Support the Bounce (BOT) Token Migration & Redenomination Plan", RENOMBRE, SIN_USDT, "swapped into AUCTION tokens at a swap ratio of 1:100", viejo="BOT", nuevo="AUCTION", r=100, E="2021-02-21")
d("Binance Will Initiate the Bounce (BOT) Token Migration & Redenomination Plan", RENOMBRE, REMITE, "at a ratio of 1 BOT = 100 AUCTION", remite="Binance Will Support the Bounce (BOT) Token Migration & Redenomination Plan")
d("Binance Will Support the BTC Standard Hashrate Token (BTCST) 1:10 Redenomination Plan", REDENOM, M2, "swap the old BTCST tokens with the new BTCST tokens at a ratio of 1:10",
  certeza="media", viejo="BTCST", nuevo="BTCST", r=10, E="2021-03-15", apertura="2021-03-19",
  nota="El texto dice «1:10» sin nombrar qué lado es el viejo; se lee 1 viejo = 10 nuevos por analogía con «COCOS 1,000:1» (1.000 viejos = 1 nuevo). Previo a A: no afecta a A.")
d("Binance Will Support the Loom Network (LOOM) Contract Swap/Upgrade", MISMO, SIN_MAPEO, "swap their Old LOOM (LOOMOLD) for New LOOM tokens (LOOM)")
d("Binance Has Completed the Tellor Tributes (TRB) Contract Swap", MISMO, SIN_MAPEO, "Binance has completed the Tellor Tributes (TRB) contract swap")
d("Binance Will Support the DREP (DREP) 100:1 Redenomination Plan", REDENOM, M2, "We will swap the old DREP tokens with the new DREP tokens at a ratio of 100:1",
  viejo="DREP", nuevo="DREP", r=0.01, E="2021-03-29", apertura="2021-04-02",
  nota="Fechas según la actualización del 2021-03-22 (cese 2021-03-29 04:00, apertura 2021-04-02 04:00).")
d("Updates to the DREP (DREP) 100:1 Redenomination Plan", REDENOM, REMITE, "Trading will be halted in all existing DREP trading pairs (DREP/BTC and DREP/USDT) at 2021-03-29 04:00 (UTC)",
  remite="Binance Will Support the DREP (DREP) 100:1 Redenomination Plan")
d("Binance To Initiate Dock (DOCK) Mainnet Token Swap", MISMO, SIN_MAPEO, "Deposits and withdrawals of DOCK will be suspended starting from 2021-03-28 01:00 AM (UTC)")
d("Binance Will Support the Pundi X (NPXS) Token Migration & Redenomination Plan", RENOMBRE, M1, "at a ratio of 1,000 NPXS = 1 PUNDIX",
  viejo="NPXS", nuevo="PUNDIX", r=0.001, E="2021-04-05", apertura="2021-04-09")
d("Binance Has Completed the DREP (DREP) 100:1 Redenomination Plan", REDENOM, REMITE, "Binance has completed the DREP (DREP) 100:1 redenomination plan", remite="Binance Will Support the DREP (DREP) 100:1 Redenomination Plan")
d("Binance Has Completed the Dock (DOCK) Mainnet Swap", MISMO, SIN_MAPEO, "Binance has completed the mainnet swap for Dock (DOCK)")
d("Binance Has Completed Pundi X (NPXS) Token Migration & Redenomination Plan", RENOMBRE, REMITE, "swap their NPXS for PUNDIX tokens", remite="Binance Will Support the Pundi X (NPXS) Token Migration & Redenomination Plan")
d("Binance Will Support the SONM (SNM) 10:1 Redenomination Plan", REDENOM, SIN_USDT, "We will swap the old SNM tokens with the new SNM tokens at a ratio of 10:1", viejo="SNM", nuevo="SNM", r=0.1, E="2021-04-26")
d("Binance Will Support the IOTA (IOTA) Token Migration to the Chrysalis Network", MISMO, SIN_MAPEO, "Binance will not support any IOTA deposits or withdrawals on the Legacy Network")
d("Notice Regarding the Upcoming EASY Hard Fork and Token Swap to EZ", RENOMBRE, SIN_USDT, "at the ratio of 1 EASY = 1 EZ", viejo="EASY", nuevo="EZ", r=1, E="2021-04-27")
d("Binance Has Completed SONM (SNM) Token Migration & Redenomination Plan", REDENOM, REMITE, "Binance has completed the SONM (SNM) 10:1 redenomination plan", remite="Binance Will Support the SONM (SNM) 10:1 Redenomination Plan")
d("Updates to the EASY Hard Fork and Token Migration Plan", RENOMBRE, REMITE, "Binance will postpone the opening of EZ/BTC and EZ/ETH markets till 2021-04-30 08:00 (UTC)", remite="Notice Regarding the Upcoming EASY Hard Fork and Token Swap to EZ")
d("Binance Will Support the Kyber Network (KNC) Contract Swap", MISMO, SIN_MAPEO, "swap their old KNC (KNCL) for new KNC tokens (KNC)")
d("Binance Will Support the Axie Infinity (AXS) & Smooth Love Potion (SLP) Contract Swap", MISMO, SIN_MAPEO, "Deposits and withdrawals of AXS & SLP will be suspended at 2021-05-24 02:00 AM (UTC)")
d("Binance Will Support the SingularityNET (AGI) Hard Fork and Token Migration Plan", RENOMBRE, SIN_USDT, "at a ratio of 1 AGI = 1 AGIX", viejo="AGI", nuevo="AGIX", r=1, E="2021-05-28")
d("Binance Has Completed the Axie Infinity (AXS) & Smooth Love Potion (SLP) Contract Swap", MISMO, SIN_MAPEO, "swap their old AXS (AXSOLD) and old SLP (SLPOLD) for new AXS and SLP tokens")
d("Binance Will Support the SUN (SUN) Token Migration & Redenomination Plan", REDENOM, M2, "at a ratio of 1 SUN (Old) = 1,000 SUN (New)",
  viejo="SUN", nuevo="SUN", r=1000, E="2021-06-14", apertura="2021-06-18")
d("The SingularityNET (AGI) Hard Fork and Token Migration Is Now Complete", RENOMBRE, REMITE, "Deposits and withdrawals for AGIX (new ticker after migration) are now open",
  remite="Binance Will Support the SingularityNET (AGI) Hard Fork and Token Migration Plan")
d("Binance Will Support the Spartan Protocol (SPARTA) Contract Swap", MISMO, SIN_MAPEO, "Binance will convert all SPARTA v1 holdings to SPARTA v2 tokens")
d("Ceasing Support for Stock Tokens on Binance.com and Migration to CM-Equity AG for EEA Users", NO_REN, DESC, "Binance.com will no longer support any stock tokens after 2021-10-14 19:55 (UTC)",
  nota="Tokens de acciones: no es un renombre ni un par spot contra USDT.")
d("Binance Will Initiate the Bitcoin Cash ABC (BCHA) Rebrand to eCash (XEC) & Redenomination Plan", RENOMBRE, SIN_USDT, "at a ratio of 1 BCHA = 1,000,000 XEC",
  viejo="BCHA", nuevo="XEC", r=1_000_000, E="2021-08-02")
d("Binance Will Support the Voyager Token (BQX) Token Swap to Voyager Token (VGX)", RENOMBRE, SIN_USDT, "at a ratio of 1 BQX = 1 VGX", viejo="BQX", nuevo="VGX", r=1, E="2021-08-16")
d("Binance Has Completed the Bitcoin Cash ABC (BCHA) Rebrand to eCash (XEC) & Redenomination Plan", RENOMBRE, REMITE, "has completed the Bitcoin Cash ABC (BCHA) rebrand to eCash (XEC)",
  remite="Binance Will Initiate the Bitcoin Cash ABC (BCHA) Rebrand to eCash (XEC) & Redenomination Plan")
d("Binance Will Support the Streamr (DATA) Token Migration Plan", MISMO, SIN_MAPEO, "The trading of DATA will not be affected during the migration")
d("Binance Will Support the Paxos Standard (PAX) Rebrand to Pax Dollar (USDP)", RENOMBRE, M1, "ratio of 1 PAX = 1 USDP",
  viejo="PAX", nuevo="USDP", r=1, E="2021-09-06", apertura="2021-09-10", nota="PAX y USDP están en la lista fija de exclusión (§4.5): el mapeo no cambia ningún universo.")
d("Binance Has Completed the Streamr (DATA) Token Migration", MISMO, SIN_MAPEO, "Binance has completed the token migration for Streamr (DATA)")
d("Binance Has Completed the Paxos Standard (PAX) Rebrand to Pax Dollar (USDP)", RENOMBRE, REMITE, "Rebrand to Pax Dollar (USDP)", remite="Binance Will Support the Paxos Standard (PAX) Rebrand to Pax Dollar (USDP)")
d("Binance Has Completed the IOTA (IOTA) Token Migration to the Chrysalis Network", MISMO, SIN_MAPEO, "Binance has completed the IOTA (IOTA) token migration to the Chrysalis Network")
d("Binance Will Support the Blox (CDT) Rebrand to ssv.network (SSV) & Redenomination Plan", RENOMBRE, SIN_USDT, "at a ratio of 100 CDT = 1 SSV", viejo="CDT", nuevo="SSV", r=0.01, E="2021-10-18")
d("The Blox (CDT) Rebrand to ssv.network (SSV) & Redenomination Is Now Complete", RENOMBRE, REMITE, "rebrand to ssv.network (SSV) and 100:1 redenomination is now complete",
  remite="Binance Will Support the Blox (CDT) Rebrand to ssv.network (SSV) & Redenomination Plan")
d("Binance Has Completed the LTO Network (LTO) Contract Swap", MISMO, SIN_MAPEO, "swap their old LTO (LTOOLD) deposits for new LTO tokens (LTO)")
d("Binance Will Support the Reserve Rights (RSR) Contract Swap", MISMO, SIN_MAPEO, "Spot trading will not be affected during the contract swap")
d("Binance Will Support the Anyswap (ANY) Token Migration and Renaming Plan", RENOMBRE, M1, "at a ratio of 1 ANY = 1 MULTI",
  viejo="ANY", nuevo="MULTI", r=1, E="2022-03-30", apertura="2022-04-06")
d("Binance Has Completed the Anyswap (ANY) Token Migration and Renaming Plan", RENOMBRE, REMITE, "The distribution of MULTI was conducted at a ratio of 1 ANY = 1 MULTI",
  remite="Binance Will Support the Anyswap (ANY) Token Migration and Renaming Plan")
d("Binance Has Completed the Mainnet Swap of ERC20 Injective Protocol (INJ)", MISMO, SIN_MAPEO, "was conducted at a ratio of 1:1")
d("Binance Will Support the TerraUSD (UST) Contract Swap", MISMO, SIN_MAPEO, "Spot and Margin trading for UST, as well as the Convert function and relevant services on Binance Earn for UST, will not be affected during the contract swap")
d("Binance Will Support the Mainnet Swap of BEP2 THORChain (RUNE)", MISMO, SIN_MAPEO, "The conversion to mainnet THORChain (RUNE) tokens will be conducted at a ratio of 1:1")
d("Binance Has Completed the Mainnet Swap of BEP2 THORChain (RUNE)", MISMO, SIN_MAPEO, "The conversion to mainnet THORChain (RUNE) tokens was conducted at a ratio of 1:1")
d("Binance Will Support the Polymath (POLY) Mainnet Swap and Rebranding Plan to Polymesh (POLYX)", RENOMBRE, M1, "at a ratio of 1 POLY = 1 POLYX",
  viejo="POLY", nuevo="POLYX", r=1, E="2022-10-10", apertura="2022-10-17")
d("Binance Will Support the Stargate Finance (STG) Contract Swap", MISMO, SIN_MAPEO, "Spot trading, margin trading, futures trading and Simple Earn subscriptions will not be affected during the contract swap")
d("Binance Will Support the Gala (GALA) Contract Swap", MISMO, SIN_MAPEO, "Spot trading, margin trading, futures trading and Simple Earn subscriptions will not be affected during the contract swap")
d("Binance Has Completed the Cocos-BCX (COCOS) Token Swap & Rebranding Plan to COMBO (COMBO)", RENOMBRE, M1, "The distribution of COMBO (COMBO) was conducted at a ratio of 1 COCOS = 1 COMBO",
  certeza="media", viejo="COCOS", nuevo="COMBO", r=1, E="2023-06-02", apertura=None,
  nota="Solo está archivado el anuncio de finalización (2023-06-02): fija símbolos, relación y fecha de finalización, no la hora de cese del par viejo. El anuncio previo que cita no está archivado. E = fecha del anuncio de finalización.")
d("Binance Will Support the TrueUSD (TUSD) Contract Swap", MISMO, SIN_MAPEO, "Spot trading, margin trading, Binance Pay, VIP Loan, Futures trading, and Simple Earn subscriptions will not be affected during the contract swap")
d("Binance Will Support the QuickSwap (QUICK) Token Swap and Redenomination Plan", REDENOM, M2, "at a ratio of 1 old QUICK = 1,000 new QUICK",
  viejo="QUICK", nuevo="QUICK", r=1000, E="2023-07-17", apertura="2023-07-21",
  cita_fechas="At 2023-07-17 03:00 (UTC) , Binance will suspend and delist all existing QUICK spot trading pairs")
d("Binance Will Support the Merit Circle (MC) Token Swap, Redenomination and Rebranding to Beam (BEAMX)", RENOMBRE, M1, "All MC tokens will be swapped for BEAMX at a ratio of 1 MC = 100 BEAMX",
  viejo="MC", nuevo="BEAMX", r=100, E="2023-11-07", apertura="2023-11-14")
d("Binance Has Completed the Virtua (TVK) Token Swap and Rebranding to Vanar (VANRY)", RENOMBRE, M1, "The distribution was conducted at a ratio of 1 TVK = 1 VANRY",
  certeza="media", viejo="TVK", nuevo="VANRY", r=1, E="2023-12-01", apertura=None,
  nota="Solo está archivado el anuncio de finalización (2023-12-01): fija símbolos, relación y fecha de finalización, no la hora de cese del par viejo. E = fecha del anuncio de finalización.")
d("Binance Will Support the PlayDapp (PLA) Token Swap to PlayDapp (PDA)", RENOMBRE, M1, "PLA tokens will assume the ticker of PDA on Binance",
  viejo="PLA", nuevo="PDA", r=1, E="2024-02-26", apertura="2024-03-01", cita_fechas="At 2024-03-01 08:00 (UTC) , trading will open for the PDA/BTC and PDA/USDT spot trading pairs")
d("Binance Will Support the Stratis (STRAX) Token Swap and Redenomination Plan", REDENOM, M2, "at a ratio of 1 old STRAX = 10 new STRAX",
  viejo="STRAX", nuevo="STRAX", r=10, E="2024-03-20", apertura="2024-03-28",
  cita_fechas="At 2024-03-28 08:00 (UTC) , trading will open for the STRAX/BTC, STRAX/USDT and STRAX/TRY spot trading pairs")
d("BNB Beacon Chain (BEP2) Network Sunset Plan", NO_REN, DESC, "The BNB Chain team will be completing its sunset of BNB Beacon Chain (BEP2) by June 2024",
  nota="Cierre de una red; no cambia símbolos ni unidades de ningún par spot.")
d("Binance Will Support the Polygon (MATIC) Token Swap to Polygon (POL)", RENOMBRE, M1, "All MATIC tokens will be swapped to POL at a ratio of 1 MATIC = 1 POL",
  viejo="MATIC", nuevo="POL", r=1, E="2024-09-10", apertura="2024-09-13")

# Renombres con anuncio oficial archivado que la extracción no clasificó como «renombre» (búsqueda en las 8028 páginas)
EXTRA = [
    {"titulo": "Binance Will Update the Ticker of BCHABC to BCH", "tipo": RENOMBRE, "decision": M1, "certeza": "alta",
     "cita": "at a ratio of 1 BCHABC = 1 BCH", "viejo": "BCHABC", "nuevo": "BCH", "r": 1, "E": "2019-11-28", "apertura": "2019-11-28",
     "archivo": "zd_360037219511_27e27ad63185.json"},
    {"titulo": "Binance Will Update the Ticker of XZC to FIRO", "tipo": RENOMBRE, "decision": M1, "certeza": "alta",
     "cita": "at a ratio of 1 XZC = 1 FIRO", "viejo": "XZC", "nuevo": "FIRO", "r": 1, "E": "2021-01-25", "apertura": "2021-01-29",
     "archivo": "bn_4a06d6ab6abb4f08b12bb93d6fec30ec_1d51d7029751.json"},
]


def clave_titulo(t):
    return t.split(" | ")[0].strip().rstrip(" |").strip()


def decision_de(t):
    hits = [k for k in D if t.startswith(k)]
    if len(hits) != 1:
        raise SystemExit(f"título sin decisión única: {t!r} → {hits}")
    return hits[0]


def actividad(base):
    s = base + "USDT"
    if s not in usdt:
        return {"simbolo": s, "en_bucket": False}
    a = aud.get(s, {})
    return {"simbolo": s, "en_bucket": True, "episodios": a.get("episodios"), "cortes_con_reanudacion": a.get("cortes_con_reanudacion")}


grupos = OrderedDict()
for i in sorted(range(len(ren)), key=lambda i: (ren[i].get("publicado") or "", ren[i]["titulo"])):
    grupos.setdefault(clave_titulo(ren[i]["titulo"]), []).append(i)
usados = set()
candidatos, por_titulo = [], []
for t, idx in grupos.items():
    k = decision_de(t)
    usados.add(k)
    dec = D[k]
    textos = [norm(ren[i].get("cuerpo")) for i in idx] + [texto_pagina.get(ren[i].get("archivo"), "") for i in idx] + \
             [texto_pagina.get("url:" + ren[i]["url"], "") for i in idx]
    for c in [dec["cita"], dec.get("cita_fechas")]:
        if c and not any(norm(c) in x for x in textos):
            raise SystemExit(f"CITA NO ENCONTRADA para {t!r}: {c!r}")
    fila_t = {"titulo": t, "candidatos": idx, "publicado": ren[idx[0]].get("publicado"), **dec}
    if dec.get("viejo"):
        fila_t["actividad_viejo"], fila_t["actividad_nuevo"] = actividad(dec["viejo"]), actividad(dec["nuevo"])
    por_titulo.append(fila_t)
    for i in idx:
        r = ren[i]
        candidatos.append({"indice": i, "titulo": r["titulo"], "url": r["url"], "archivo": r.get("archivo"), "warc": r.get("url_archivada"),
                           "captura": r.get("captura"), "publicado": r.get("publicado"), "pares_usdt_extraidos": r.get("pares_usdt"),
                           "decision_titulo": t, "tipo": dec["tipo"], "decision": dec["decision"], "certeza": dec["certeza"]})
if set(D) - usados:
    raise SystemExit(f"decisiones sin candidato: {set(D) - usados}")
if len(candidatos) != 164:
    raise SystemExit(f"se esperaban 164 candidatos y hay {len(candidatos)}")
for x in EXTRA:
    if norm(x["cita"]) not in texto_pagina[x["archivo"]]:
        raise SystemExit(f"CITA NO ENCONTRADA (extra): {x['cita']!r}")
    x["actividad_viejo"], x["actividad_nuevo"] = actividad(x["viejo"]), actividad(x["nuevo"])


def fuente_de(fila):
    if "archivo" in fila:
        return {"archivo": fila["archivo"]}
    i = fila["candidatos"][0]
    return {"url": ren[i]["url"], "archivo": ren[i].get("archivo"), "warc": ren[i].get("url_archivada"), "captura": ren[i].get("captura")}


def chequeo_actividad(m):
    """Coherencia (solo fechas de actividad): el viejo deja de estar activo ≤ E y el nuevo empieza ≥ E − 1."""
    av, an = m["actividad_viejo"], m["actividad_nuevo"]
    E = dt.date.fromisoformat(m["E"])
    if m["regla"] == 2:
        cortes = [c for c in (av.get("cortes_con_reanudacion") or []) if dt.date.fromisoformat(c[0]) <= E <= dt.date.fromisoformat(c[1])]
        return {"corte_en_datos": cortes[0] if cortes else None, "coherente": bool(cortes)}
    fin_v = [dt.date.fromisoformat(e[1]) for e in av.get("episodios") or [] if dt.date.fromisoformat(e[1]) <= E]
    ini_n = [dt.date.fromisoformat(e[0]) for e in an.get("episodios") or [] if dt.date.fromisoformat(e[0]) >= E - dt.timedelta(days=1)]
    L, S = (max(fin_v) if fin_v else None), (min(ini_n) if ini_n else None)
    return {"ultimo_activo_viejo": L and L.isoformat(), "primer_activo_nuevo": S and S.isoformat(),
            "coherente": bool(L and S and (E - L).days <= 7 and (S - E).days <= 14)}


mapeos = []
for fila in [*por_titulo, *EXTRA]:
    if fila["decision"] not in (M1, M2):
        continue
    m = {"regla": 1 if fila["decision"] == M1 else 2, "viejo_usdt": fila["viejo"] + "USDT", "nuevo_usdt": fila["nuevo"] + "USDT",
         "r": fila["r"], "E": fila["E"], "apertura_segun_texto": fila.get("apertura"), "cita": fila["cita"], "cita_fechas": fila.get("cita_fechas"),
         "certeza": fila["certeza"], "nota": fila.get("nota"), "titulo": fila["titulo"], "fuente": fuente_de(fila),
         "actividad_viejo": fila["actividad_viejo"], "actividad_nuevo": fila["actividad_nuevo"]}
    if not (m["actividad_viejo"]["en_bucket"] and m["actividad_nuevo"]["en_bucket"]):
        raise SystemExit(f"mapeo sin par USDT en el bucket: {m['viejo_usdt']} → {m['nuevo_usdt']}")
    m["chequeo_actividad"] = chequeo_actividad(m)
    mapeos.append(m)
mapeos.sort(key=lambda m: m["E"])

# Sin anuncio oficial archivado (Adenda 1, regla 3): se informan y NO se mapean
SIN_ANUNCIO = {
    "cortes_con_salto_sin_anuncio": [
        {"simbolo": "LUNAUSDT", "corte": ["2022-05-12", "2022-05-31"], "antes_de_A": True},
        {"simbolo": "VIDTUSDT", "corte": ["2022-10-30", "2022-11-09"], "antes_de_A": True},
        {"simbolo": "BNXUSDT", "corte": ["2023-02-15", "2023-02-22"], "antes_de_A": True},
    ],
    "cortes_sin_salto_x10": [
        {"simbolo": "AUDUSDT", "corte": ["2020-11-12", "2020-11-14"], "nota": "moneda fiat: lista fija de exclusión (§4.5)"},
        {"simbolo": "BTCSTUSDT", "corte": ["2021-03-14", "2021-03-19"], "nota": "redenominación con anuncio (regla 2), previa a A"},
        {"simbolo": "NBTUSDT", "corte": ["2022-09-11", "2022-10-01"], "nota": "sin anuncio archivado; previa a A"},
        {"simbolo": "KEYUSDT", "corte": ["2023-02-09", "2023-03-10"], "nota": "sin anuncio archivado del corte; previa a A"},
        {"simbolo": "AEURUSDT", "corte": ["2023-12-04", "2023-12-08"], "nota": "estable: lista fija de exclusión (§4.5)"},
        {"simbolo": "SCRUSDT", "corte": ["2024-10-20", "2024-10-22"], "nota": "sin anuncio archivado; dentro de A"},
        {"simbolo": "USUALUSDT", "corte": ["2024-12-16", "2024-12-18"], "nota": "posterior al archivo (2024-11-06); dentro de A"},
        {"simbolo": "AXSUSDT", "corte": ["2026-02-09", "2026-02-11"], "nota": "posterior al archivo; dentro de A"},
    ],
    "posibles_cambios_de_simbolo_dentro_de_A": [
        # Solo evidencia de actividad (el viejo termina y el nuevo empieza a ≤ 5 días). Sin anuncio archivado: regla 3.
        ("TOMOUSDT", "VICUSDT"), ("GALUSDT", "GUSDT"), ("RNDRUSDT", "RENDERUSDT"), ("KLAYUSDT", "KAIAUSDT"), ("DARUSDT", "DUSDT"),
        ("FTMUSDT", "SUSDT"), ("EOSUSDT", "AUSDT"), ("MKRUSDT", "SKYUSDT"), ("FXSUSDT", "FRAXUSDT"), ("OMUSDT", "MANTRAUSDT"),
    ],
}
SIN_ANUNCIO["posibles_cambios_de_simbolo_dentro_de_A"] = [
    {"viejo": v, "nuevo": n, "actividad_viejo": actividad(v[:-4]), "actividad_nuevo": actividad(n[:-4]),
     "tratamiento": "Regla 3 de la Adenda 1: el viejo sale (liquidación contable, §4.10) y el nuevo es un listado nuevo (edad 0). No se unen las series."}
    for v, n in SIN_ANUNCIO["posibles_cambios_de_simbolo_dentro_de_A"]]

res = {"n_candidatos": len(candidatos), "n_titulos": len(por_titulo), "mapeos": mapeos, "renombres_extra_sin_clasificar": EXTRA,
       "sin_anuncio_regla_3": SIN_ANUNCIO, "por_titulo": por_titulo, "candidatos": candidatos}
SAL_J.write_text(json.dumps(res, ensure_ascii=False, indent=1))

# Tabla legible
L = ["# Clasificación de los 164 candidatos de renombre (A3.11) y mapeos de la Adenda 1", "",
     f"- Candidatos: {len(candidatos)}; títulos únicos: {len(por_titulo)}; renombres extra hallados fuera de la lista: {len(EXTRA)}.",
     "- Cada cita se verificó literalmente contra el texto archivado local (el script aborta si falta).",
     "- `r` = unidades nuevas por unidad vieja; la serie es continua con P_nuevo ≈ P_viejo / r.", "",
     "## Mapeos (Adenda 1, reglas 1 y 2) con par USDT en el bucket", "",
     "| Regla | Viejo → nuevo | r | E (texto) | Apertura (texto) | Últ. activo viejo / corte | 1.er activo nuevo | Coherente | Certeza | Cita |",
     "|---|---|---|---|---|---|---|---|---|---|"]
for m in mapeos:
    ch = m["chequeo_actividad"]
    L.append(f"| {m['regla']} | {m['viejo_usdt']} → {m['nuevo_usdt']} | {m['r']} | {m['E']} | {m['apertura_segun_texto'] or '—'} | "
             f"{ch.get('ultimo_activo_viejo') or (ch.get('corte_en_datos') or ['—'])[0]} | {ch.get('primer_activo_nuevo') or (ch.get('corte_en_datos') or ['', '—'])[1]} | "
             f"{'sí' if ch['coherente'] else 'NO'} | {m['certeza']} | «{m['cita']}» |")
L += ["", "## Decisión por título", "", "| Publicado | Título | Candidatos | Tipo | Decisión | Certeza | Cita |", "|---|---|---|---|---|---|---|"]
for f in por_titulo:
    dd = f["decision"] + (f" ({f['remite'][:50]}…)" if f.get("remite") else "")
    L.append(f"| {f['publicado']} | {f['titulo'][:95]} | {', '.join(map(str, f['candidatos']))} | {f['tipo']} | {dd} | {f['certeza']} | «{f['cita'][:110]}» |")
SAL_M.write_text("\n".join(L) + "\n")
print(json.dumps({"candidatos": len(candidatos), "titulos": len(por_titulo), "mapeos_regla_1": sum(m["regla"] == 1 for m in mapeos),
                  "mapeos_regla_2": sum(m["regla"] == 2 for m in mapeos), "incoherentes": [m["viejo_usdt"] for m in mapeos if not m["chequeo_actividad"]["coherente"]],
                  "decisiones": {k: sum(1 for f in por_titulo if f["decision"] == k) for k in (M1, M2, SIN_MAPEO, SIN_USDT, REMITE, DESC)}}, ensure_ascii=False))
