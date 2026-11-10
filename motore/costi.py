"""Costi reali di un'operazione su DEGIRO (commissioni, cambio, tasse sulle transazioni)."""
from . import config


def commissione(borsa):
    return config.DEGIRO_COMMISSIONE.get(borsa, config.DEGIRO_COMMISSIONE_ALTRE) + config.DEGIRO_GESTIONE


def andata_ritorno(borsa, valuta, importo):
    """Costo totale in euro per comprare e poi rivendere `importo` euro di un titolo."""
    c = 2 * commissione(borsa)
    if valuta not in ("EUR", ""):
        c += 2 * importo * config.DEGIRO_AUTOFX
    c += importo * config.TASSA_TRANSAZIONI.get(borsa, 0.0)
    return c


def prezzo_eur(prezzo, valuta):
    return prezzo * config.FX_EUR.get(valuta, 1.0)
