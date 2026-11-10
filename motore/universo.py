"""Costruisce l'elenco dei titoli da analizzare (borse trattate da DEGIRO).

Fonti:
- USA: screener ufficiale Nasdaq (tutte le azioni NYSE/Nasdaq/AMEX) filtrato per capitalizzazione
- Europa: composizione dei principali indici da Wikipedia
- tickers_extra.txt: titoli aggiunti a mano (uno per riga, formato Yahoo, es. ENI.MI)
"""
import io
import re
import time
from datetime import datetime

import pandas as pd
import requests

from . import config

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

# suffisso Yahoo -> (borsa, valuta)
BORSE = {
    "": ("USA", "USD"), ".MI": ("Milano", "EUR"), ".DE": ("Xetra", "EUR"),
    ".PA": ("Parigi", "EUR"), ".AS": ("Amsterdam", "EUR"), ".BR": ("Bruxelles", "EUR"),
    ".LS": ("Lisbona", "EUR"), ".MC": ("Madrid", "EUR"), ".L": ("Londra", "GBp"),
    ".SW": ("Zurigo", "CHF"), ".ST": ("Stoccolma", "SEK"), ".HE": ("Helsinki", "EUR"),
    ".CO": ("Copenaghen", "DKK"), ".OL": ("Oslo", "NOK"), ".VI": ("Vienna", "EUR"),
    ".IR": ("Dublino", "EUR"), ".WA": ("Varsavia", "PLN"),
}

# (pagina Wikipedia, suffisso Yahoo, nome indice)
INDICI_EUROPA = [
    ("FTSE_MIB", ".MI", "FTSE MIB"),
    ("FTSE_Italia_Mid_Cap", ".MI", "FTSE Italia Mid Cap"),
    ("DAX", ".DE", "DAX"), ("MDAX", ".DE", "MDAX"), ("SDAX", ".DE", "SDAX"), ("TecDAX", ".DE", "TecDAX"),
    ("CAC_40", ".PA", "CAC 40"), ("SBF_120", ".PA", "SBF 120"), ("CAC_Mid_60", ".PA", "CAC Mid 60"),
    ("AEX_index", ".AS", "AEX"), ("AMX_index", ".AS", "AMX"), ("AScX", ".AS", "AScX"),
    ("BEL_20", ".BR", "BEL 20"), ("IBEX_35", ".MC", "IBEX 35"), ("PSI_(stock_index)", ".LS", "PSI"),
    ("FTSE_100_Index", ".L", "FTSE 100"), ("FTSE_250_Index", ".L", "FTSE 250"),
    ("Swiss_Market_Index", ".SW", "SMI"), ("SMI_MID", ".SW", "SMIM"),
    ("OMX_Stockholm_30", ".ST", "OMXS30"), ("OMX_Helsinki_25", ".HE", "OMXH25"),
    ("OMX_Copenhagen_25", ".CO", "OMXC25"), ("OBX_Index", ".OL", "OBX"),
    ("Austrian_Traded_Index", ".VI", "ATX"), ("ISEQ_20", ".IR", "ISEQ 20"), ("WIG20", ".WA", "WIG20"),
    ("EURO_STOXX_50", None, "Euro Stoxx 50"),
]

COLONNE_TICKER = re.compile(r"^(ticker|symbol|ticker symbol|epic|code|stock symbol|ticker\s*\(.*\)|symbol\s*\(.*\))$", re.I)
COLONNE_NOME = re.compile(r"^(company|name|security|company name|constituent|stock)$", re.I)


def _get(url, **kw):
    for tentativo in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=30, **kw)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            if tentativo == 2:
                raise
            time.sleep(2 + tentativo * 3)


def universo_usa():
    url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25000&offset=0&download=true"
    js = _get(url).json()
    rows = js["data"]["rows"]
    df = pd.DataFrame(rows)
    df["marketCap"] = pd.to_numeric(df["marketCap"], errors="coerce")
    df = df[df["marketCap"] >= config.MIN_MARKET_CAP_USD]
    df["symbol"] = df["symbol"].str.strip()
    # escludi warrant, unit, preferred, diritti
    df = df[~df["symbol"].str.contains(r"[\^/ ]", regex=True)]
    df = df[~df["name"].str.contains(r"\b(Warrant|Units?|Rights?|Preferred|Depositary Shares? Representing)\b",
                                      case=False, regex=True, na=False)]
    out = pd.DataFrame({
        "ticker": df["symbol"].str.replace(".", "-", regex=False),
        "nome": df["name"].str.replace(r"\s+(Common Stock|Class [A-C] Common Stock|Ordinary Shares).*$", "",
                                       regex=True),
        "borsa": "USA", "valuta": "USD", "indice": "USA (Nasdaq screener)",
        "settore": df.get("sector", ""), "paese": df.get("country", ""),
    })
    return out


def _normalizza(raw, suffisso):
    t = str(raw).strip()
    if not t or t.lower() == "nan":
        return None
    t = t.split(":")[-1].strip()                 # "XETRA: ADS" -> "ADS"
    t = re.sub(r"\[.*?\]", "", t).strip()        # note wiki
    t = t.split()[0] if " " in t and "." in t.split()[0] else t
    for suf in BORSE:
        if suf and t.upper().endswith(suf.upper()):
            return t[: -len(suf)].upper().replace(" ", "-") + suf
    if suffisso is None:
        return None
    t = t.upper().replace(" ", "-")
    if suffisso == ".L":
        t = t.rstrip(".").replace(".", "-")      # BT.A -> BT-A.L
    return t + suffisso


def universo_europa():
    righe = []
    for pagina, suf, nome_indice in INDICI_EUROPA:
        try:
            html = _get(f"https://en.wikipedia.org/wiki/{pagina}").text
            tabelle = pd.read_html(io.StringIO(html))
        except Exception as e:  # noqa: BLE001
            print(f"  ! {nome_indice}: pagina non leggibile ({e.__class__.__name__})")
            continue
        trovati = 0
        for tab in tabelle:
            if isinstance(tab.columns, pd.MultiIndex):
                tab.columns = [" ".join(str(x) for x in c if "Unnamed" not in str(x)).strip() for c in tab.columns]
            cols = [str(c).strip() for c in tab.columns]
            tab.columns = cols
            ct = next((c for c in cols if COLONNE_TICKER.match(c)), None)
            if ct is None or len(tab) < 5:
                continue
            cn = next((c for c in cols if COLONNE_NOME.match(c)), None)
            for _, r in tab.iterrows():
                t = _normalizza(r[ct], suf)
                if not t:
                    continue
                s = "" if t.find(".") < 0 else t[t.rfind("."):]
                borsa, valuta = BORSE.get(s, (None, None))
                if borsa is None:
                    continue
                righe.append({"ticker": t, "nome": str(r[cn]) if cn else t, "borsa": borsa,
                              "valuta": valuta, "indice": nome_indice, "settore": "", "paese": borsa})
                trovati += 1
        print(f"  {nome_indice}: {trovati} titoli")
        time.sleep(0.5)
    return pd.DataFrame(righe)


def extra():
    f = config.ROOT / "tickers_extra.txt"
    if not f.exists():
        return pd.DataFrame()
    righe = []
    for line in f.read_text(encoding="utf-8").splitlines():
        t = line.split("#")[0].strip()
        if not t:
            continue
        s = "" if "." not in t else t[t.rfind("."):]
        borsa, valuta = BORSE.get(s, ("Altro", "EUR"))
        righe.append({"ticker": t, "nome": t, "borsa": borsa, "valuta": valuta, "indice": "Manuale",
                      "settore": "", "paese": borsa})
    return pd.DataFrame(righe)


def carica_universo(forza=False):
    f = config.STATO / "universo.csv"
    if f.exists() and not forza:
        eta = (datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)).days
        if eta < config.UNIVERSO_GIORNI_VALIDITA:
            return pd.read_csv(f, keep_default_na=False)
    print("Costruisco l'universo dei titoli...")
    parti = []
    try:
        us = universo_usa()
        print(f"  USA: {len(us)} titoli")
        parti.append(us)
    except Exception as e:  # noqa: BLE001
        print(f"  ! USA non disponibile ({e})")
    try:
        parti.append(universo_europa())
    except Exception as e:  # noqa: BLE001
        print(f"  ! Europa non disponibile ({e})")
    parti.append(extra())
    parti = [p for p in parti if len(p)]
    if not parti:
        if f.exists():
            print("  Uso l'universo salvato in precedenza.")
            return pd.read_csv(f, keep_default_na=False)
        raise RuntimeError("Impossibile costruire l'universo: controlla la connessione internet.")
    uni = pd.concat(parti, ignore_index=True)
    # stesso titolo in più indici: tieni il primo, unisci i nomi indice
    idx = uni.groupby("ticker")["indice"].apply(lambda s: ", ".join(sorted(set(s))))
    uni = uni.drop_duplicates("ticker").set_index("ticker")
    uni["indice"] = idx
    uni = uni.reset_index()
    # se il salvataggio precedente era più ricco (es. una fonte è caduta), non perdere titoli
    if f.exists():
        vecchio = pd.read_csv(f, keep_default_na=False)
        if len(uni) < 0.8 * len(vecchio):
            uni = pd.concat([uni, vecchio[~vecchio["ticker"].isin(uni["ticker"])]], ignore_index=True)
    uni.to_csv(f, index=False)
    print(f"Universo totale: {len(uni)} titoli")
    return uni
