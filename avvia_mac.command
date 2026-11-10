#!/bin/bash
cd "$(dirname "$0")"
echo "Radar Azioni - analisi in corso (la prima volta puo durare 30-60 minuti)..."
python3 -m pip install -q -r requirements.txt
python3 main.py --apri
