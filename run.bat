@echo off
REM Lanceur Windows : double-cliquer pour démarrer LoFiMa.
REM Au premier lancement, crée l'environnement Python et installe les dépendances.
cd /d "%~dp0"
if not exist .venv (
    echo Creation de l'environnement Python...
    py -3 -m venv .venv || python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m lofima %*
pause
