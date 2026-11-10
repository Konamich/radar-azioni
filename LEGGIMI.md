# Radar Azioni – guida

Programma che ogni sera analizza circa 4.000-5.000 azioni quotate sulle borse trattate da DEGIRO
(USA, Milano, Xetra, Parigi, Amsterdam, Bruxelles, Madrid, Lisbona, Londra, Zurigo, Nordici, Vienna, Dublino, Varsavia)
e pubblica una pagina che apri dal telefono o dal PC con:

- **Oggi** – stato del mercato e i 5 migliori titoli per ciascun orizzonte
- **Segnali** – 20 da comprare e 20 da vendere/evitare, per *swing (1-4 settimane)* e *medio-lungo (6 mesi)*, con prezzo di stop e obiettivo
- **Portafoglio** – inserisci le tue posizioni DEGIRO e ti dice TIENI / ALLEGGERISCI / VENDI / PRENDI PROFITTO (i dati restano sul tuo dispositivo)
- **Cerca** – punteggio 0-100 di ogni titolo analizzato
- **Affidabilità** – quanto ha azzeccato finora, verificato sui prezzi reali

---

## 1. Metterlo online gratis (gira da solo ogni sera) – circa 15 minuti, una volta sola

1. Crea un account gratuito su **github.com**.
2. In alto a destra **+ → New repository**. Nome a piacere (es. `radar-azioni`), scegli **Public**, poi **Create repository**.
   *(Pubblico serve per avere la pagina gratis. Nel repository finiscono solo punteggi dei titoli: il tuo portafoglio NON viene mai caricato.)*
3. Nella pagina del repository clicca **uploading an existing file** e trascina **tutto il contenuto** della cartella `analizzatore-azioni` (non la cartella stessa). Poi **Commit changes**.
4. Controlla che esista il file `.github/workflows/analisi_giornaliera.yml`. Su Mac la cartella `.github` è nascosta e spesso non viene caricata: in quel caso **Add file → Create new file**, scrivi come nome `.github/workflows/analisi_giornaliera.yml`, incolla il contenuto del file e salva.
5. **Settings → Actions → General** → in fondo, *Workflow permissions* → **Read and write permissions** → Save.
6. **Settings → Pages** → *Source*: **GitHub Actions**.
7. **Actions** → *Analisi giornaliera* → **Run workflow**. La prima volta scarica 5 anni di storia di tutti i titoli: 30-60 minuti. Dalle volte successive scarica solo gli ultimi giorni.
8. Finito, la pagina è su `https://TUONOME.github.io/radar-azioni/`. Sull'iPhone aprila con Safari → Condividi → **Aggiungi alla schermata Home**: diventa un'app.

Da quel momento il programma parte da solo **dal lunedì al venerdì alle 23:30** (a mercati USA chiusi). GitHub a volte ritarda le esecuzioni programmate di qualche decina di minuti: è normale.

## 2. Usarlo dal PC

Serve Python 3.10 o superiore (python.org, durante l'installazione su Windows spunta *Add Python to PATH*).

- Windows: doppio clic su `avvia_windows.bat`
- Mac: doppio clic su `avvia_mac.command` (la prima volta: tasto destro → Apri)

Alla fine si apre il report nel browser (file `output/index.html`).
Prova veloce senza internet: `python main.py --demo`. Prova con pochi titoli: `python main.py --limite 300`.

Nota: la versione su GitHub e quella sul PC tengono ciascuna il proprio storico delle previsioni. Per il track record conta quella che gira ogni giorno (GitHub).

## 3. Come decide

Per ogni titolo calcola ~30 indicatori (momentum a 1-12 mesi, medie mobili 20/50/200, RSI, MACD, Bollinger, ATR, volumi, distanza da massimi e minimi, forza rispetto alla propria borsa, stato generale del mercato) e li confronta con quelli di tutti gli altri titoli dello stesso giorno.

Due "cervelli" danno un voto:
1. **Regole tecniche** classiche (swing: trend di fondo + ritracciamento + accumulo; lungo: momentum 12-1 mesi, MM50 > MM200, vicinanza ai massimi, bassa volatilità).
2. **Modello di machine learning** (gradient boosting) che impara da 5 anni di storia quali combinazioni di indicatori hanno preceduto i titoli migliori nei 15 giorni (swing) o 6 mesi (lungo) successivi.

Il voto finale è una media pesata dei due. Filtri: liquidità minima ~750.000 € scambiati al giorno, prezzo > 1, e per il lungo periodo solo titoli sopra la media a 200 giorni. Massimo 6 titoli per borsa nella lista acquisti.

## 4. Come migliora nel tempo

- **Ogni sera il modello viene riaddestrato** con i dati nuovi del giorno.
- **Ogni previsione viene salvata** (`stato/punteggi/`) e, passati 15 giorni (swing) o 126 giorni (lungo), viene **confrontata con quello che è successo davvero** (`stato/performance.csv`).
- I **pesi** tra regole e modello ML si spostano verso quello che ha funzionato meglio: all'inizio contano i risultati della verifica sull'ultimo anno, poi via via di più quelli reali.
- Nella scheda *Affidabilità* vedi tutto: se la lista acquisti batte il mercato, e quali indicatori stanno contando di più.

## 5. Da sapere prima di usarlo con soldi veri

- Sono **segnali statistici, non consulenza finanziaria**. Nessun modello prevede il mercato in modo affidabile: un vantaggio realistico è battere la media di poco e non sempre.
- Usalo prima **solo osservando** per qualche settimana e guarda il track record reale prima di seguirlo.
- Dimensiona le posizioni rispetto allo stop: rischia una piccola parte del capitale per operazione.
- Costi DEGIRO, cambio valuta (USD, GBP, CHF…) e tasse (26% sulle plusvalenze) riducono il risultato, soprattutto nello swing con molte operazioni.
- I dati vengono da Yahoo Finance (gratuiti, con possibili errori o blocchi temporanei). Prima di comprare **controlla sempre il prezzo e il titolo su DEGIRO**: il programma non può verificare che ogni singolo ticker sia acquistabile dal tuo conto.
- Il programma non è collegato al tuo conto e non esegue ordini.

## 6. Personalizzare

- `motore/config.py`: capitalizzazione minima USA, liquidità minima, numero di segnali, stop e obiettivi in multipli di ATR, orizzonti.
- `tickers_extra.txt`: titoli in più da analizzare (formato Yahoo, es. `LDO.MI`).

## Struttura

```
main.py                    avvio
motore/universo.py         elenco titoli (Nasdaq screener + indici europei da Wikipedia)
motore/dati.py             download prezzi con cache
motore/indicatori.py       indicatori tecnici
motore/modello.py          modello ML + regole + pesi adattivi
motore/segnali.py          liste acquisti/vendite, stop, obiettivi
motore/tracciamento.py     registro previsioni e verifica
motore/report.py           pagina HTML
stato/                     memoria del programma (salvata su GitHub)
```
