"""Registro delle previsioni: salva i punteggi di ogni giorno e, quando l'orizzonte è
trascorso, verifica cosa è successo davvero. Il risultato alimenta i pesi del modello."""
import numpy as np
import pandas as pd

from . import config

FILE_PERF = config.STATO / "performance.csv"


def salva_punteggi(giorno, tab):
    cols = ["ticker", "close", "borsa"]
    for o in config.ORIZZONTI:
        cols += [f"{o}_ml", f"{o}_regole", f"{o}_punteggio", f"{o}_acquisto", f"{o}_vendita"]
    f = config.SCORES_DIR / f"{pd.Timestamp(giorno).date().isoformat()}.parquet"
    tab[cols].to_parquet(f, index=False)


def _ic(a, b):
    ok = a.notna() & b.notna()
    if ok.sum() < 30:
        return np.nan
    return float(a[ok].rank().corr(b[ok].rank()))


def valuta(m):
    close = m["close"]
    date = close.index
    perf = pd.read_csv(FILE_PERF, parse_dates=["data"]) if FILE_PERF.exists() else pd.DataFrame()
    fatti = set(zip(perf["data"].dt.date.astype(str), perf["orizzonte"])) if len(perf) else set()
    nuove = []
    for f in sorted(config.SCORES_DIR.glob("*.parquet")):
        giorno = f.stem
        d = pd.Timestamp(giorno)
        pos = date.searchsorted(d, side="right") - 1
        if pos < 0:
            continue
        for o, cfg in config.ORIZZONTI.items():
            if (giorno, o) in fatti:
                continue
            h = cfg["giorni"]
            if pos + h >= len(date):
                continue  # esito non ancora disponibile
            s = pd.read_parquet(f)
            futuro = close.iloc[pos + h].reindex(s["ticker"]).values
            s["ritorno"] = futuro / s["close"].values - 1
            s = s[np.isfinite(s["ritorno"])]
            if len(s) < 30:
                continue
            buy = s[s[f"{o}_acquisto"]]
            sell = s[s[f"{o}_vendita"]]
            med = s["ritorno"].median()
            nuove.append({
                "data": d, "orizzonte": o, "titoli": len(s),
                "ic_ml": _ic(s[f"{o}_ml"], s["ritorno"]),
                "ic_regole": _ic(s[f"{o}_regole"], s["ritorno"]),
                "ic_combinato": _ic(s[f"{o}_punteggio"], s["ritorno"]),
                "rend_acquisti": float(buy["ritorno"].mean()) if len(buy) else np.nan,
                "rend_vendite": float(sell["ritorno"].mean()) if len(sell) else np.nan,
                "rend_universo": float(s["ritorno"].mean()),
                "acquisti_positivi": float((buy["ritorno"] > 0).mean()) if len(buy) else np.nan,
                "acquisti_battono_mediana": float((buy["ritorno"] > med).mean()) if len(buy) else np.nan,
                "vendite_sotto_mediana": float((sell["ritorno"] < med).mean()) if len(sell) else np.nan,
            })
    if nuove:
        perf = pd.concat([perf, pd.DataFrame(nuove)], ignore_index=True).sort_values(["orizzonte", "data"])
        perf.to_csv(FILE_PERF, index=False)
        print(f"Verificate {len(nuove)} previsioni passate")
    return perf


def ic_live(perf, orizzonte, ultimi=120):
    if not len(perf):
        return None
    p = perf[perf["orizzonte"] == orizzonte].tail(ultimi)
    if not len(p):
        return None
    return {"n": int(len(p)), "ic_ml": float(p["ic_ml"].mean()), "ic_regole": float(p["ic_regole"].mean())}


def riepilogo(perf):
    out = {}
    for o in config.ORIZZONTI:
        p = perf[perf["orizzonte"] == o] if len(perf) else pd.DataFrame()
        if not len(p):
            out[o] = {"n": 0}
            continue
        ultimi = p.tail(60)
        out[o] = {
            "n": int(len(p)),
            "ic_medio": float(p["ic_combinato"].mean()),
            "ic_recente": float(ultimi["ic_combinato"].mean()),
            "rend_acquisti": float(p["rend_acquisti"].mean()),
            "rend_universo": float(p["rend_universo"].mean()),
            "rend_vendite": float(p["rend_vendite"].mean()),
            "acquisti_positivi": float(p["acquisti_positivi"].mean()),
            "acquisti_battono_mediana": float(p["acquisti_battono_mediana"].mean()),
            "serie": [{"d": r["data"].date().isoformat(),
                       "extra": round(float(r["rend_acquisti"] - r["rend_universo"]) * 100, 2),
                       "ic": round(float(r["ic_combinato"]), 3)} for _, r in p.tail(250).iterrows()],
        }
    return out
