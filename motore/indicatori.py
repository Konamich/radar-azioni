"""Indicatori tecnici calcolati su matrici date x ticker (veloce anche con migliaia di titoli)."""
import numpy as np
import pandas as pd

from . import config


def _rsi(close, n=14):
    d = close.diff()
    su = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    giu = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = su / giu.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def calcola(m, universo):
    c, h, l, v = m["close"], m["high"], m["low"], m["volume"]
    ret = c.pct_change(fill_method=None)
    logc = np.log(c)
    f = {}
    # rendimenti / momentum
    for n in (5, 21, 63, 126, 252):
        f[f"r{n}"] = logc - logc.shift(n)
    f["mom12_1"] = logc.shift(21) - logc.shift(252)
    # volatilità
    f["vol21"] = ret.rolling(21, min_periods=15).std() * np.sqrt(252)
    f["vol63"] = ret.rolling(63, min_periods=40).std() * np.sqrt(252)
    f["vol_ratio_ret"] = f["vol21"] / f["vol63"]
    # medie mobili
    sma20 = c.rolling(20, min_periods=15).mean()
    sma50 = c.rolling(50, min_periods=35).mean()
    sma200 = c.rolling(200, min_periods=150).mean()
    f["dist_sma20"] = c / sma20 - 1
    f["dist_sma50"] = c / sma50 - 1
    f["dist_sma200"] = c / sma200 - 1
    f["sma50_200"] = sma50 / sma200 - 1
    f["pend_sma50"] = sma50 / sma50.shift(10) - 1
    # massimi / minimi
    max252 = c.rolling(252, min_periods=120).max()
    min252 = c.rolling(252, min_periods=120).min()
    f["dist_max252"] = c / max252 - 1
    f["dist_min252"] = c / min252 - 1
    f["dist_max20"] = c / c.rolling(20, min_periods=15).max() - 1
    # oscillatori
    f["rsi14"] = _rsi(c, 14)
    f["rsi2"] = _rsi(c, 2)
    ema12 = c.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = c.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    f["macd_hist"] = (macd - macd.ewm(span=9, adjust=False, min_periods=9).mean()) / c
    std20 = c.rolling(20, min_periods=15).std()
    f["boll_z"] = (c - sma20) / std20
    # ATR
    prev = c.shift(1)
    tr = np.fmax(np.fmax(h - l, (h - prev).abs()), (l - prev).abs())
    atr = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    f["atr_pct"] = atr / c
    # volumi
    vma50 = v.rolling(50, min_periods=20).mean()
    f["vol_rel5"] = v.rolling(5, min_periods=3).mean() / vma50
    f["updown_vol"] = (v.where(ret > 0).rolling(50, min_periods=20).sum()
                       / v.where(ret < 0).rolling(50, min_periods=20).sum())
    # liquidità in EUR
    valuta = universo.set_index("ticker")["valuta"].reindex(c.columns).fillna("USD")
    fx = valuta.map(config.FX_EUR).fillna(1.0)
    scambi = (c * v).rolling(20, min_periods=10).median() * fx
    # forza relativa vs propria borsa
    borsa = universo.set_index("ticker")["borsa"].reindex(c.columns).fillna("Altro")
    r63 = f["r63"]
    med_borsa = r63.T.groupby(borsa).transform("median").T
    f["rs_borsa63"] = r63 - med_borsa

    # regime di mercato (uguale per tutti i titoli in quella data)
    sopra200 = (c > sma200).where(sma200.notna())
    regime = pd.DataFrame({
        "ampiezza200": sopra200.mean(axis=1),
        "mercato_r21": f["r21"].median(axis=1),
        "mercato_vol21": f["vol21"].median(axis=1),
    })
    extra = {"atr": atr, "sma50": sma50, "sma200": sma200, "scambi_eur": scambi,
             "max60": c.rolling(60, min_periods=20).max(), "ret": ret}
    f = {k: v.astype("float32") for k, v in f.items()}
    return f, regime, extra


FEATURE_RANK = ["r5", "r21", "r63", "r126", "r252", "mom12_1", "vol21", "vol63", "vol_ratio_ret",
                "dist_sma20", "dist_sma50", "dist_sma200", "sma50_200", "pend_sma50", "dist_max252",
                "dist_min252", "dist_max20", "rsi14", "rsi2", "macd_hist", "boll_z", "atr_pct",
                "vol_rel5", "updown_vol", "rs_borsa63"]
FEATURE_RAW = ["rsi14", "dist_sma200", "r21", "atr_pct"]
FEATURE_REGIME = ["ampiezza200", "mercato_r21", "mercato_vol21"]


_CACHE_RANGHI = {}


def ranghi(f, valido):
    """Rango percentile per data (0-1) calcolato solo sui titoli validi quel giorno."""
    chiave = (id(f), id(valido))
    if chiave in _CACHE_RANGHI:
        return _CACHE_RANGHI[chiave]
    _CACHE_RANGHI.clear()
    out = {}
    for k in FEATURE_RANK:
        x = f[k].where(valido)
        out[k] = x.rank(axis=1, pct=True).astype("float32")
    _CACHE_RANGHI[chiave] = out
    return out


def pannello(rk, f, regime, date_sel, valido, target=None):
    """Costruisce la tabella lunga (data, ticker, feature...) per le date richieste."""
    pezzi = []
    for d in date_sel:
        ok = valido.loc[d]
        tick = ok.index[ok.values]
        if len(tick) == 0:
            continue
        cols = {f"rk_{k}": rk[k].loc[d, tick].values for k in FEATURE_RANK}
        for k in FEATURE_RAW:
            cols[f"raw_{k}"] = f[k].loc[d, tick].values
        for k in FEATURE_REGIME:
            cols[k] = np.full(len(tick), regime.loc[d, k])
        df = pd.DataFrame(cols, index=tick)
        df.index.name = "ticker"
        df["date"] = d
        if target is not None:
            df["y"] = target.loc[d, tick].values
        pezzi.append(df.reset_index())
    if not pezzi:
        return pd.DataFrame()
    p = pd.concat(pezzi, ignore_index=True)
    num = p.columns.difference(["ticker", "date"])
    p[num] = p[num].astype("float32")
    return p


def colonne_modello():
    return [f"rk_{k}" for k in FEATURE_RANK] + [f"raw_{k}" for k in FEATURE_RAW] + FEATURE_REGIME
