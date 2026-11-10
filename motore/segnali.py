"""Trasforma i punteggi in liste operative (acquisti / vendite) con livelli di stop e target."""
import numpy as np
import pandas as pd

from . import config


def motivazioni(r, orizzonte):
    m = []
    if r["r126"] > 0.15:
        m.append(f"trend 6 mesi +{r['r126'] * 100:.0f}%")
    if r["dist_sma200"] > 0:
        m.append("sopra MM200")
    else:
        m.append("sotto MM200")
    if r["rsi14"] < 35:
        m.append(f"ipervenduto (RSI {r['rsi14']:.0f})")
    elif r["rsi14"] > 70:
        m.append(f"ipercomprato (RSI {r['rsi14']:.0f})")
    if r["dist_max252"] > -0.05:
        m.append("vicino ai massimi annuali")
    elif r["dist_max252"] < -0.4:
        m.append(f"{r['dist_max252'] * 100:.0f}% dai massimi")
    if r["vol_rel5"] > 1.8:
        m.append("volumi in forte aumento")
    if r["rs_borsa63"] > 0.1:
        m.append("più forte della sua borsa")
    elif r["rs_borsa63"] < -0.1:
        m.append("più debole della sua borsa")
    return ", ".join(m[:4])


def _diversifica(df, n):
    scelti, per_borsa = [], {}
    for _, r in df.iterrows():
        b = r["borsa"]
        if per_borsa.get(b, 0) >= config.MAX_PER_MERCATO:
            continue
        scelti.append(r)
        per_borsa[b] = per_borsa.get(b, 0) + 1
        if len(scelti) >= n:
            break
    return pd.DataFrame(scelti)


def genera(tab, orizzonte):
    """tab: una riga per titolo con punteggio, percentile e indicatori del giorno."""
    t = tab.copy()
    if orizzonte == "swing":
        cand = t[(t["rsi14"] < 72) & (t["dist_sma200"] > -0.25)]
        stop_k, tgt_k = config.SWING_STOP_ATR, config.SWING_TARGET_ATR
    else:
        cand = t[(t["dist_sma200"] > 0) & (t["sma50_200"] > -0.02)]
        stop_k, tgt_k = config.LUNGO_STOP_ATR, None
    acq = _diversifica(cand.sort_values("punteggio", ascending=False), config.N_ACQUISTI)
    acq = acq.copy()
    acq["stop"] = acq["close"] - stop_k * acq["atr"]
    acq["target"] = acq["close"] + tgt_k * acq["atr"] if tgt_k else np.nan
    acq["motivi"] = [motivazioni(r, orizzonte) for _, r in acq.iterrows()]

    ven = t.sort_values("punteggio").head(config.N_VENDITE).copy()
    ven["motivi"] = [motivazioni(r, orizzonte) for _, r in ven.iterrows()]
    return acq, ven
