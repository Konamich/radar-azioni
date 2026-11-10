"""Dati simulati per provare il programma senza internet (python main.py --demo)."""
import numpy as np
import pandas as pd

BORSE = [("", "USA", "USD"), (".MI", "Milano", "EUR"), (".DE", "Xetra", "EUR"),
         (".PA", "Parigi", "EUR"), (".L", "Londra", "GBp"), (".AS", "Amsterdam", "EUR")]


def universo(n=None):
    import os
    n = n or int(os.environ.get("DEMO_TITOLI", 360))
    rng = np.random.default_rng(7)
    righe = []
    for i in range(n):
        suf, borsa, val = BORSE[i % len(BORSE)]
        righe.append({"ticker": f"T{i:03d}{suf}", "nome": f"Società Demo {i}", "borsa": borsa,
                      "valuta": val, "indice": "Demo", "settore": rng.choice(["Tech", "Banche", "Energia"]),
                      "paese": borsa})
    return pd.DataFrame(righe)


def prezzi(uni, anni=5):
    rng = np.random.default_rng(11)
    date = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=int(252 * anni))
    n = len(uni)
    T = len(date)
    mercato = rng.normal(0.0003, 0.01, T)
    # drift persistente per titolo (genera momentum reale, che il modello deve scoprire)
    drift = np.zeros((T, n))
    d = rng.normal(0, 0.0008, n)
    for t in range(T):
        d = 0.995 * d + rng.normal(0, 0.00008, n)
        drift[t] = d
    beta = rng.uniform(0.6, 1.4, n)
    vol = rng.uniform(0.012, 0.03, n)
    ret = drift + beta * mercato[:, None] + rng.normal(0, 1, (T, n)) * vol
    close = 50 * np.exp(np.cumsum(ret, axis=0)) * rng.uniform(0.2, 4, n)
    high = close * (1 + np.abs(rng.normal(0, 0.008, (T, n))))
    low = close * (1 - np.abs(rng.normal(0, 0.008, (T, n))))
    volume = rng.lognormal(13, 0.5, (T, n)) * (1 + 3 * (np.abs(ret) > 2 * vol))
    df = pd.DataFrame({
        "date": np.repeat(date, n), "ticker": np.tile(uni["ticker"].values, T),
        "open": close.ravel(), "high": high.ravel(), "low": low.ravel(),
        "close": close.ravel(), "volume": volume.ravel()})
    # alcune IPO recenti
    giovani = uni["ticker"].values[:10]
    df = df[~(df["ticker"].isin(giovani) & (df["date"] < date[-300]))]
    return df
