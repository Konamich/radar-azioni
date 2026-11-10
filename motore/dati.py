"""Scarica i prezzi giornalieri (Yahoo Finance via yfinance) con cache incrementale."""
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config

FILE_PREZZI = config.CACHE / "prezzi.parquet"
CAMPI = ["Open", "High", "Low", "Close", "Volume"]


def _scarica_batch(tickers, start):
    import yfinance as yf
    for tentativo in range(4):
        try:
            df = yf.download(tickers, start=start, auto_adjust=True, group_by="ticker",
                             threads=True, progress=False, timeout=30)
            break
        except Exception as e:  # noqa: BLE001
            attesa = 10 * (tentativo + 1)
            print(f"    errore download ({e.__class__.__name__}), riprovo tra {attesa}s")
            time.sleep(attesa)
    else:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    pezzi = []
    if isinstance(df.columns, pd.MultiIndex):
        livello0 = set(df.columns.get_level_values(0))
        for t in tickers:
            if t not in livello0:
                continue
            sub = df[t]
            sub = sub[[c for c in CAMPI if c in sub.columns]].dropna(subset=["Close"])
            if sub.empty:
                continue
            sub = sub.assign(ticker=t)
            pezzi.append(sub)
    else:
        sub = df[[c for c in CAMPI if c in df.columns]].dropna(subset=["Close"]).assign(ticker=tickers[0])
        pezzi.append(sub)
    if not pezzi:
        return pd.DataFrame()
    out = pd.concat(pezzi)
    out.index.name = "date"
    out = out.reset_index()
    out.columns = [c.lower() for c in out.columns]
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    return out


def aggiorna_prezzi(tickers):
    tickers = list(dict.fromkeys(tickers))
    cache = pd.read_parquet(FILE_PREZZI) if FILE_PREZZI.exists() else pd.DataFrame(
        columns=["date", "ticker", "open", "high", "low", "close", "volume"])
    inizio_completo = (date.today() - timedelta(days=int(365.25 * config.ANNI_STORIA))).isoformat()

    noti = set(cache["ticker"].unique()) if len(cache) else set()
    nuovi = [t for t in tickers if t not in noti]
    vecchi = [t for t in tickers if t in noti]
    ultimo = cache["date"].max() if len(cache) else None

    gruppi = []
    if nuovi:
        gruppi.append((nuovi, inizio_completo, "storico completo"))
    if vecchi:
        da = (pd.Timestamp(ultimo) - pd.Timedelta(days=10)).date().isoformat()
        gruppi.append((vecchi, da, "aggiornamento"))

    scaricati = []
    for lista, start, tipo in gruppi:
        print(f"Download {tipo}: {len(lista)} titoli da {start}")
        for i in range(0, len(lista), config.BATCH_DOWNLOAD):
            batch = lista[i:i + config.BATCH_DOWNLOAD]
            d = _scarica_batch(batch, start)
            if len(d):
                scaricati.append(d)
            print(f"  {min(i + config.BATCH_DOWNLOAD, len(lista))}/{len(lista)}", end="\r")
            time.sleep(config.PAUSA_TRA_BATCH)
        print()

    if scaricati:
        nuovo = pd.concat(scaricati, ignore_index=True)
        tutto = pd.concat([cache, nuovo], ignore_index=True)
        # i dati appena scaricati prevalgono (eventuali rettifiche per dividendi/split)
        tutto = tutto.drop_duplicates(["ticker", "date"], keep="last")
        # se un ticker ha avuto uno split/dividendo, i prezzi rettificati vecchi non combaciano:
        # controlla il punto di giunzione e riscarica quelli incoerenti
        tutto = _ripara_giunzioni(tutto, nuovo, inizio_completo)
    else:
        tutto = cache
    if len(tutto) == 0:
        raise RuntimeError("Nessun prezzo scaricato: Yahoo Finance non raggiungibile o blocco temporaneo.")
    limite = pd.Timestamp(inizio_completo) - pd.Timedelta(days=30)
    tutto = tutto[tutto["date"] >= limite]
    tutto = tutto.astype({"open": "float32", "high": "float32", "low": "float32",
                          "close": "float32", "volume": "float64"})
    tutto.sort_values(["ticker", "date"]).to_parquet(FILE_PREZZI, index=False)
    return tutto[tutto["ticker"].isin(tickers)]


def _ripara_giunzioni(tutto, nuovo, inizio):
    """Se nel periodo sovrapposto il prezzo nuovo differisce >2% dal vecchio, c'è stata una
    rettifica (split/dividendo): riscarica lo storico completo di quel titolo."""
    if not len(nuovo):
        return tutto
    primo_nuovo = nuovo.groupby("ticker")["date"].min()
    da_riparare = []
    vecchi = tutto.set_index(["ticker", "date"])["close"]
    for t, d0 in primo_nuovo.items():
        n = nuovo[(nuovo["ticker"] == t) & (nuovo["date"] == d0)]["close"]
        try:
            v = vecchi.loc[(t, d0)]
        except KeyError:
            continue
        if isinstance(v, pd.Series):
            v = v.iloc[0]
        if len(n) and v and abs(float(n.iloc[0]) / float(v) - 1) > 0.02:
            da_riparare.append(t)
    if da_riparare:
        print(f"  Rettifiche (split/dividendi) per {len(da_riparare)} titoli: riscarico lo storico")
        fix = []
        for i in range(0, len(da_riparare), config.BATCH_DOWNLOAD):
            d = _scarica_batch(da_riparare[i:i + config.BATCH_DOWNLOAD], inizio)
            if len(d):
                fix.append(d)
        if fix:
            fix = pd.concat(fix)
            tutto = pd.concat([tutto[~tutto["ticker"].isin(fix["ticker"].unique())], fix], ignore_index=True)
    return tutto


def matrici(prezzi):
    """Converte in matrici date x ticker. Riempie i giorni di festa di una sola borsa."""
    out = {}
    for c in ["open", "high", "low", "close", "volume"]:
        m = prezzi.pivot_table(index="date", columns="ticker", values=c, aggfunc="last").sort_index()
        out[c] = m
    reale = out["close"].notna()
    for c in ["open", "high", "low", "close"]:
        out[c] = out[c].ffill(limit=5)
    out["volume"] = out["volume"].where(reale)
    out["reale"] = reale
    return out
