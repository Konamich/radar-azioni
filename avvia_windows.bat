@echo off
cd /d "%~dp0"
echo Radar Azioni - analisi in corso (la prima volta puo durare 30-60 minuti)...
py -m pip install -q -r requirements.txt
py main.py --apri
pause
