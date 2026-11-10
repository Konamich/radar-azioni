"""Genera il report HTML (unico file, funziona su telefono e PC, anche offline)."""
import json
import math

import numpy as np
import pandas as pd

from . import config

TEMPLATE = config.ROOT / "motore" / "report_template.html"


def _num(x, nd=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(x) else round(x, nd)


def _righe_lista(df, o, storia):
    out = []
    for _, r in df.iterrows():
        out.append({
            "t": r["ticker"], "n": str(r.get("nome", ""))[:40], "b": r["borsa"],
            "v": r.get("valuta", ""), "c": _num(r["close"]), "p": _num(r.get(f"{o}_percentile"), 1),
            "stop": _num(r.get("stop")), "tgt": _num(r.get("target")),
            "r21": _num(r["r21"]), "r252": _num(r["r252"]), "rsi": _num(r["rsi14"], 0),
            "mot": r.get("motivi", ""), "sp": storia.get(r["ticker"], []),
        })
    return out


def crea(oggi, tab, risultati, statistiche, riepilogo, storia, regime, demo=False):
    tutti = []
    for _, r in tab.iterrows():
        tutti.append([r["ticker"], str(r.get("nome", ""))[:40], r["borsa"], _num(r["close"]),
                      _num(r.get("swing_percentile"), 1), _num(r.get("lungo_percentile"), 1),
                      _num(r["atr"]), _num(r["max60"]), _num(r["r21"]), _num(r["r252"]),
                      _num(r["rsi14"], 0), r.get("valuta", "")])
    dati = {
        "data": pd.Timestamp(oggi).date().isoformat(),
        "demo": demo,
        "regime": regime,
        "orizzonti": {o: c["nome"] for o, c in config.ORIZZONTI.items()},
        "liste": {o: {"acquisti": _righe_lista(v["acquisti"], o, storia),
                      "vendite": _righe_lista(v["vendite"], o, storia)} for o, v in risultati.items()},
        "stat": statistiche,
        "track": riepilogo,
        "tutti": tutti,
        "param": {"swing_stop": config.SWING_STOP_ATR, "swing_tgt": config.SWING_TARGET_ATR,
                  "lungo_stop": config.LUNGO_STOP_ATR},
    }
    js = json.dumps(dati, ensure_ascii=False, default=lambda x: None if x is None else float(x))
    js = js.replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATI__", js)
    out = config.OUTPUT / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
