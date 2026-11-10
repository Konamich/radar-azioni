"""Impostazioni del programma. Modifica qui i parametri principali."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATO = ROOT / "stato"            # file piccoli da conservare (salvati su GitHub)
CACHE = ROOT / "cache"            # prezzi scaricati (ri-scaricabili)
OUTPUT = ROOT / "output"          # report generato
SCORES_DIR = STATO / "punteggi"   # un file per giorno con i punteggi di tutti i titoli

# ---- Universo -------------------------------------------------------------
MIN_MARKET_CAP_USD = 300e6        # azioni USA: capitalizzazione minima
MIN_SCAMBI_EUR_GIORNO = 750_000   # liquidità minima (controvalore medio giornaliero)
MIN_PREZZO = 1.0                  # esclude penny stock
UNIVERSO_GIORNI_VALIDITA = 7      # ricostruisce la lista titoli una volta a settimana

# ---- Dati -----------------------------------------------------------------
ANNI_STORIA = 5
BATCH_DOWNLOAD = 120
PAUSA_TRA_BATCH = 1.5             # secondi (evita blocchi di Yahoo)

# ---- Orizzonti ------------------------------------------------------------
ORIZZONTI = {
    "swing": {"giorni": 15, "nome": "Swing (1-4 settimane)"},
    "lungo": {"giorni": 126, "nome": "Medio-lungo (circa 6 mesi)"},
}

# ---- Segnali --------------------------------------------------------------
N_ACQUISTI = 20
N_VENDITE = 20
SWING_STOP_ATR = 2.0
SWING_TARGET_ATR = 3.5
LUNGO_STOP_ATR = 4.0
MAX_PER_MERCATO = 6               # diversificazione: massimo titoli per borsa nella lista acquisti

# ---- Modello --------------------------------------------------------------
CAMPIONA_OGNI_N_GIORNI = 3        # per l'addestramento usa un giorno ogni N
MAX_RIGHE_TRAIN = 900_000
FINESTRA_VALIDAZIONE = 250        # giorni di borsa tenuti da parte per misurare il modello
MIN_VALUTAZIONI_LIVE = 15         # dopo quante verifiche reali i pesi seguono il track record

# Tasso di cambio approssimativo (solo per il filtro di liquidità)
FX_EUR = {"USD": 0.92, "EUR": 1.0, "GBP": 1.17, "GBp": 0.0117, "CHF": 1.05,
          "SEK": 0.087, "DKK": 0.134, "NOK": 0.085, "PLN": 0.23}

for d in (STATO, CACHE, OUTPUT, SCORES_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---- Costi DEGIRO (tariffario Italia, verificati a novembre 2026) ----------
# commissione per ordine in EUR, esclusa la commissione di gestione
DEGIRO_COMMISSIONE = {"USA": 1.00, "Milano": 1.00}
DEGIRO_COMMISSIONE_ALTRE = 3.90       # Xetra, Parigi, Amsterdam, Londra, Zurigo, nordici, ecc.
DEGIRO_GESTIONE = 1.00                # "handling fee" su ogni ordine
DEGIRO_ETF_CORE = 1.00                # ETF Core Selection su Tradegate (solo gestione)
DEGIRO_AUTOFX = 0.0025                # cambio automatico per titoli non in euro (a ogni operazione)
DEGIRO_CONNETTIVITA = 2.50            # all'anno per ogni borsa estera usata (non Milano / Tradegate)
TASSA_TRANSAZIONI = {"Milano": 0.002, "Parigi": 0.004}   # Tobin tax IT e TTF FR, solo sull'acquisto
IVAFE = 0.002                         # 0,2% annuo sul valore (DEGIRO = regime dichiarativo)
TASSA_PLUSVALENZE = 0.26
IMPORTO_RIFERIMENTO = 150             # importo d'ordine usato per mostrare il peso dei costi
