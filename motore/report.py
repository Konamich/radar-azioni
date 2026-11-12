"""Genera la pagina HTML (unico file, funziona su telefono e PC, anche offline).

La pagina ha due parti:
  1. Oggi            -> cosa comprare (solo se serve) e cosa vendere (solo se serve), con budget mensile
  2. Tutte le azioni -> tutti i titoli DEGIRO studiati, con il loro punteggio
"""
import json
import math
import re
import shutil

import numpy as np
import pandas as pd

from . import config, costi, segnali

TEMPLATE = config.ROOT / "motore" / "report_template.html"

# Peso dei due orizzonti nel punteggio unico: il medio-lungo è quello che nei test funziona meglio
# e con 100 euro al mese conviene comprare poco e tenere a lungo (le commissioni pesano).
PESO_LUNGO = 0.7
PESO_SWING = 0.3


def _num(x, nd=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(x) else round(x, nd)


def punteggio_unico(tab):
    """Punteggio 0-100 che unisce i due orizzonti (100 = il titolo più favorevole di oggi)."""
    s = tab["swing_percentile"].astype(float).fillna(50)
    l = tab["lungo_percentile"].astype(float).fillna(50)
    grezzo = PESO_LUNGO * l + PESO_SWING * s
    return grezzo.rank(pct=True) * 100


def _trend_ok(r):
    """Titolo in salute: sopra la media a 200 giorni, medie in ordine, non ipercomprato."""
    return bool(r["dist_sma200"] > 0 and r["sma50_200"] > -0.02 and r["rsi14"] < 75)


_RUMORE = set("""inc corp corporation plc p l c ltd limited ag sa s a n v nv se asa ab spa
oyj co the d b a common shares share american depositary depository receipts ads adr new york registry
each representing of ordinary class b a
holding holdings group sponsored registered public company""".split())


def _nome_pulito(n):
    p = re.sub(r"\(.*?\)|\[.*?\]", " ", str(n).lower())
    p = re.sub(r"[^a-z0-9 ]", " ", p).split()
    return [w for w in p if w not in _RUMORE]


def _doppie_quotazioni(t):
    """Stessa società quotata negli USA (ADR) e in Europa (es. GMAB e GMAB.CO): segna come doppia
    la quotazione con il punteggio peggiore, così nei consigli compare una volta sola."""
    paese = t["paese"].astype(str) if "paese" in t else pd.Series("", index=t.index)
    usa_estera = (t["borsa"] == "USA") & ~paese.isin(["United States", "USA", "", "nan"])
    nomi = {i: _nome_pulito(n) for i, n in t["nome"].items()}
    europei = {}
    for i in t.index[t["borsa"] != "USA"]:
        if nomi[i]:
            europei.setdefault(nomi[i][0], []).append(i)
    doppio = pd.Series(False, index=t.index)
    for i in t.index[usa_estera]:
        a = nomi[i]
        if not a:
            continue
        migliore, lung = None, 0
        for j in europei.get(a[0], []):
            b = nomi[j]
            k = min(len(a), len(b))
            if k == 1 and len(a) > 1:
                continue                      # es. "Enel Chile" non è "Enel"
            if a[:k] == b[:k] and k > lung:   # un nome è l'inizio dell'altro
                migliore, lung = j, k
        if migliore is not None:
            peggiore = i if t.at[i, "punteggio"] < t.at[migliore, "punteggio"] else migliore
            doppio.at[peggiore] = True
    # stessa società su due borse europee (es. Stellantis a Milano e a Parigi)
    eu = t[(t["borsa"] != "USA") & ~doppio]
    chiave = eu.index.map(lambda i: " ".join(nomi[i]))
    for k, g in eu.groupby(chiave):
        if k and len(g) > 1:
            doppio.loc[g.index.drop(g["punteggio"].idxmax())] = True
    return doppio


def crea(oggi, tab, risultati, statistiche, riepilogo, storia, regime, demo=False):
    t = tab.copy()
    t["punteggio"] = punteggio_unico(t)
    t["prezzo_eur"] = [costi.prezzo_eur(c, v) for c, v in zip(t["close"], t.get("valuta", "EUR"))]
    t["stop"] = t["close"] - config.LUNGO_STOP_ATR * t["atr"]
    t["trend"] = [_trend_ok(r) for _, r in t.iterrows()]

    # motivazioni solo per i titoli che possono finire tra i consigli di acquisto
    forti = t["punteggio"] >= 85
    t["motivi"] = ""
    t.loc[forti, "motivi"] = [segnali.motivazioni(r, "lungo") for _, r in t[forti].iterrows()]

    # stessa società quotata su due borse (es. GMAB e GMAB.CO): tiene solo la quotazione migliore
    t["doppio"] = _doppie_quotazioni(t)

    tutti = []
    for _, r in t.iterrows():
        tutti.append([
            r["ticker"], str(r.get("nome", ""))[:48], r["borsa"], r.get("valuta", ""),
            _num(r["close"]), _num(r["prezzo_eur"], 2), _num(r["punteggio"], 1),
            _num(r["r21"]), _num(r["r252"]), 1 if r["trend"] else 0,
            _num(r["atr"]), _num(r["max60"]), _num(r["stop"]),
            r["motivi"] or "", 1 if r["doppio"] else 0,
        ])

    dati = {
        "data": pd.Timestamp(oggi).date().isoformat(),
        "demo": demo,
        "regime": regime,
        "tutti": tutti,
        "storia": storia,
        "stop_k": config.LUNGO_STOP_ATR,
        "track": {o: {"n": v.get("n", 0), "rend_acquisti": v.get("rend_acquisti"),
                      "rend_universo": v.get("rend_universo")} for o, v in riepilogo.items()},
        "costi": {"comm": config.DEGIRO_COMMISSIONE, "comm_altre": config.DEGIRO_COMMISSIONE_ALTRE,
                  "gestione": config.DEGIRO_GESTIONE, "autofx": config.DEGIRO_AUTOFX,
                  "ftt": config.TASSA_TRANSAZIONI, "tassa": config.TASSA_PLUSVALENZE},
    }
    js = json.dumps(dati, ensure_ascii=False, separators=(",", ":"),
                    default=lambda x: None if x is None else float(x))
    js = js.replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATI__", js)
    out = config.OUTPUT / "index.html"
    out.write_text(html, encoding="utf-8")
    for icona in ("icona.svg", "apple-touch-icon.png"):
        sorgente = config.ROOT / "motore" / icona
        if sorgente.exists():
            shutil.copy(sorgente, config.OUTPUT / icona)
    return out
