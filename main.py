"""Analizzatore Azioni - analisi giornaliera e segnali di acquisto/vendita.

Uso:
    python main.py              analisi completa (scarica dati, addestra, genera report)
    python main.py --demo       prova con dati simulati, senza internet
    python main.py --limite 300 analizza solo i primi N titoli (prova veloce)
"""
import argparse
import json
import sys
import time
import webbrowser
from datetime import datetime

import numpy as np
import pandas as pd

from motore import config, dati, demo, indicatori as ind, modello, report, segnali, tracciamento, universo


def esegui(args):
    t0 = time.time()
    if args.demo:
        uni = demo.universo()
        prezzi = demo.prezzi(uni)
    else:
        uni = universo.carica_universo(forza=args.aggiorna_universo)
        if args.limite:
            uni = uni.groupby("borsa", group_keys=False).apply(
                lambda g: g.head(max(5, args.limite * len(g) // len(uni))))
        prezzi = dati.aggiorna_prezzi(uni["ticker"].tolist())
    if args.fino_a:
        prezzi = prezzi[prezzi["date"] <= pd.Timestamp(args.fino_a)]

    print("Calcolo indicatori...")
    m = dati.matrici(prezzi)
    uni = uni[uni["ticker"].isin(m["close"].columns)].reset_index(drop=True)
    f, regime, extra = ind.calcola(m, uni)
    valido = modello.maschera_validi(m, f, extra)
    oggi = m["close"].index[-1]
    ok = valido.loc[oggi]
    tick = ok.index[ok.values]
    print(f"Data analisi: {oggi.date()} | titoli validi oggi: {len(tick)} su {m['close'].shape[1]}")

    perf = tracciamento.valuta(m)

    tab = uni.set_index("ticker").reindex(tick)
    tab["close"] = m["close"].loc[oggi, tick]
    for k in ["r5", "r21", "r63", "r126", "r252", "rsi14", "dist_sma200", "dist_max252", "vol_rel5",
              "rs_borsa63", "sma50_200", "vol63", "atr_pct"]:
        tab[k] = f[k].loc[oggi, tick]
    for k in ["atr", "sma200", "max60", "scambi_eur"]:
        tab[k] = extra[k].loc[oggi, tick]
    tab = tab.reset_index().rename(columns={"index": "ticker"})

    risultati, statistiche = {}, {}
    for o in config.ORIZZONTI:
        prev, st = modello.addestra_e_prevedi(m, f, regime, extra, valido, o, tracciamento.ic_live(perf, o))
        statistiche[o] = st
        prev = prev.rename(columns={c: f"{o}_{c}" for c in prev.columns if c != "ticker"})
        tab = tab.merge(prev, on="ticker", how="left")
        t_o = tab.assign(punteggio=tab[f"{o}_punteggio"], percentile=tab[f"{o}_percentile"])
        acq, ven = segnali.genera(t_o, o)
        tab[f"{o}_acquisto"] = tab["ticker"].isin(acq["ticker"])
        tab[f"{o}_vendita"] = tab["ticker"].isin(ven["ticker"])
        risultati[o] = {"acquisti": acq, "vendite": ven}

    tracciamento.salva_punteggi(oggi, tab)
    perf = tracciamento.valuta(m)  # nel caso servisse a ricalcolare
    riep = tracciamento.riepilogo(perf)

    # mini-grafici: ultimi 90 prezzi per i titoli più forti (possibili acquisti)
    pu = report.punteggio_unico(tab)
    in_lista = set(tab.loc[pu >= 90, "ticker"])
    storia = {t: [float(f"{x:.4g}") for x in m["close"][t].iloc[-60:].values if np.isfinite(x)]
              for t in in_lista}

    regime_oggi = {k: float(regime.loc[oggi, k]) for k in regime.columns}
    percorso = report.crea(oggi, tab, risultati, statistiche, riep, storia, regime_oggi, demo=args.demo)
    meta = {"data": oggi.date().isoformat(), "generato": datetime.now().isoformat(timespec="minutes"),
            "titoli": int(len(tab)), "durata_sec": round(time.time() - t0), "statistiche": statistiche}
    (config.STATO / "ultima_esecuzione.json").write_text(json.dumps(meta, indent=2, default=float))
    print(f"Fatto in {time.time() - t0:.0f}s. Report: {percorso}")
    return percorso


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--limite", type=int)
    ap.add_argument("--fino-a", dest="fino_a")
    ap.add_argument("--aggiorna-universo", action="store_true")
    ap.add_argument("--apri", action="store_true", help="apre il report nel browser alla fine")
    a = ap.parse_args()
    p = esegui(a)
    if a.apri:
        webbrowser.open(p.resolve().as_uri())
    sys.exit(0)
