"""Modello predittivo: si riaddestra ogni giorno su tutto lo storico disponibile e combina
un modello di machine learning con un punteggio a regole. I pesi della combinazione
dipendono da quanto ciascuno dei due ha funzionato (validazione + verifiche reali)."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from . import config, indicatori as ind


def punteggio_regole(p, orizzonte):
    g = lambda k: p[f"rk_{k}"].fillna(0.5)  # noqa: E731
    if orizzonte == "swing":
        # trend di fondo positivo + ritracciamento di breve + volumi in accumulo
        return (0.25 * g("r126") + 0.15 * g("dist_sma200") + 0.15 * g("rs_borsa63")
                + 0.20 * (1 - g("rsi2")) + 0.10 * g("updown_vol")
                + 0.15 * g("pend_sma50"))
    # lungo: momentum 12-1, trend strutturale, vicinanza ai massimi, bassa volatilità
    return (0.35 * g("mom12_1") + 0.20 * g("sma50_200") + 0.20 * g("dist_max252")
            + 0.15 * (1 - g("vol63")) + 0.10 * g("updown_vol"))


def _ic_giornaliero(df, col):
    def sp(x):
        if len(x) < 30:
            return np.nan
        return x[col].rank().corr(x["y"].rank())
    return df.groupby("date").apply(sp, include_groups=False).dropna()


def _modello():
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                         min_samples_leaf=400, l2_regularization=1.0,
                                         early_stopping=True, validation_fraction=0.1,
                                         n_iter_no_change=20, random_state=42)


def maschera_validi(m, f, extra):
    reale_recente = m["reale"].rolling(5, min_periods=1).max().astype(bool)
    return (reale_recente & (m["close"] >= config.MIN_PREZZO)
            & (extra["scambi_eur"] >= config.MIN_SCAMBI_EUR_GIORNO) & f["r126"].notna())


def addestra_e_prevedi(m, f, regime, extra, valido, orizzonte, ic_live=None):
    h = config.ORIZZONTI[orizzonte]["giorni"]
    rk = ind.ranghi(f, valido)
    logc = np.log(m["close"])
    fwd = (logc.shift(-h) - logc).where(valido)
    # gli ultimi h giorni non hanno ancora un esito: esclusi dall'addestramento
    target = fwd.rank(axis=1, pct=True)

    date = m["close"].index
    con_esito = date[: max(0, len(date) - h)]
    con_esito = con_esito[260:]  # serve storia per gli indicatori
    sel = con_esito[::config.CAMPIONA_OGNI_N_GIORNI]
    cols = ind.colonne_modello()
    oggi = date[-1]

    stats = {"orizzonte": orizzonte, "giorni": h}
    if len(sel) < 60:
        print(f"  [{orizzonte}] storia insufficiente per il modello: uso solo le regole")
        modello, w_ml = None, 0.0
    else:
        p = ind.pannello(rk, f, regime, sel, valido, target)
        p = p.dropna(subset=["y"])
        if len(p) > config.MAX_RIGHE_TRAIN:
            p = p.sample(config.MAX_RIGHE_TRAIN, random_state=1)
        # validazione "a ritroso": addestro sul passato, misuro sull'ultimo anno mai visto
        d_unique = np.sort(p["date"].unique())
        n_val = min(config.FINESTRA_VALIDAZIONE // config.CAMPIONA_OGNI_N_GIORNI, len(d_unique) // 3)
        inizio_val = d_unique[-n_val]
        fine_train = date[max(0, date.get_loc(inizio_val) - h)]
        tr = p[p["date"] < fine_train]
        va = p[p["date"] >= inizio_val].copy()
        mod_v = _modello().fit(tr[cols], tr["y"])
        va["ml"] = mod_v.predict(va[cols])
        va["regole"] = punteggio_regole(va, orizzonte)
        ic_ml = _ic_giornaliero(va, "ml")
        ic_rg = _ic_giornaliero(va, "regole")
        # rendimento reale medio del miglior 10% vs media
        va["fwd"] = [fwd.at[d, t] for d, t in zip(va["date"], va["ticker"])]
        va["comb_tmp"] = 0.5 * va["ml"].rank(pct=True) + 0.5 * va["regole"].rank(pct=True)
        top = va.groupby("date").apply(
            lambda x: np.expm1(x.nlargest(max(1, len(x) // 10), "comb_tmp")["fwd"]).mean()
            - np.expm1(x["fwd"]).mean(), include_groups=False)
        stats.update({
            "val_ic_ml": float(ic_ml.mean()), "val_ic_regole": float(ic_rg.mean()),
            "val_ic_ml_positivo": float((ic_ml > 0).mean()),
            "val_extra_top10": float(top.mean()), "val_giorni": int(len(ic_ml)),
            "righe_addestramento": int(len(p)),
        })
        # pesi della combinazione
        a, b = max(stats["val_ic_ml"], 0), max(stats["val_ic_regole"], 0)
        if ic_live and ic_live.get("n", 0) >= config.MIN_VALUTAZIONI_LIVE:
            k = ic_live["n"] / (ic_live["n"] + 60)
            a = (1 - k) * a + k * max(ic_live["ic_ml"], 0)
            b = (1 - k) * b + k * max(ic_live["ic_regole"], 0)
            stats["pesi_da_track_record"] = round(k, 2)
        w_ml = 0.5 if a + b == 0 else float(np.clip(a / (a + b), 0.15, 0.9))
        # modello finale su TUTTO lo storico (ogni giorno include i dati più recenti)
        modello = _modello().fit(p[cols], p["y"])
        imp = _importanza(modello, p[cols].iloc[-20000:], p["y"].iloc[-20000:], cols)
        stats["feature_principali"] = imp
    stats["peso_ml"] = round(w_ml, 3)

    oggi_p = ind.pannello(rk, f, regime, [oggi], valido)
    oggi_p["regole"] = punteggio_regole(oggi_p, orizzonte)
    oggi_p["ml"] = modello.predict(oggi_p[cols]) if modello is not None else 0.5
    oggi_p["punteggio"] = (w_ml * oggi_p["ml"].rank(pct=True)
                           + (1 - w_ml) * oggi_p["regole"].rank(pct=True))
    oggi_p["percentile"] = (oggi_p["punteggio"].rank(pct=True) * 100).round(1)
    print(f"  [{orizzonte}] peso ML {w_ml:.2f} | IC validazione ML {stats.get('val_ic_ml', float('nan')):.3f}"
          f" regole {stats.get('val_ic_regole', float('nan')):.3f}")
    return oggi_p[["ticker", "ml", "regole", "punteggio", "percentile"]], stats


NOMI_FEATURE = {
    "r5": "rendimento 1 sett.", "r21": "rendimento 1 mese", "r63": "rendimento 3 mesi",
    "r126": "rendimento 6 mesi", "r252": "rendimento 12 mesi", "mom12_1": "momentum 12-1 mesi",
    "vol21": "volatilità 1 mese", "vol63": "volatilità 3 mesi", "vol_ratio_ret": "variazione volatilità",
    "dist_sma20": "distanza MM20", "dist_sma50": "distanza MM50", "dist_sma200": "distanza MM200",
    "sma50_200": "MM50 vs MM200", "pend_sma50": "pendenza MM50", "dist_max252": "distanza dal massimo annuo",
    "dist_min252": "distanza dal minimo annuo", "dist_max20": "distanza dal massimo 1 mese",
    "rsi14": "RSI 14", "rsi2": "RSI 2", "macd_hist": "MACD", "boll_z": "Bollinger",
    "atr_pct": "ATR %", "vol_rel5": "volumi relativi", "updown_vol": "volumi rialzo/ribasso",
    "rs_borsa63": "forza relativa vs borsa", "ampiezza200": "ampiezza mercato",
    "mercato_r21": "trend mercato 1 mese", "mercato_vol21": "volatilità mercato",
}


def _importanza(modello, X, y, cols):
    """Importanza per permutazione semplificata (quanto peggiora la previsione se mescolo la colonna)."""
    rng = np.random.default_rng(0)
    base = np.corrcoef(modello.predict(X), y)[0, 1]
    imp = {}
    for c in cols:
        Xp = X.copy()
        Xp[c] = rng.permutation(Xp[c].values)
        imp[c] = base - np.corrcoef(modello.predict(Xp), y)[0, 1]
    top = sorted(imp.items(), key=lambda kv: -kv[1])[:6]
    out = []
    for c, v in top:
        k = c.replace("rk_", "").replace("raw_", "")
        out.append({"nome": NOMI_FEATURE.get(k, k), "valore": round(float(v), 4)})
    return out
