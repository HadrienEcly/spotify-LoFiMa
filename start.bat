@echo off
REM ==========================================================================
REM  start.bat - Demarre LoFiMa avec l'environnement virtuel .venv.
REM  Ouvre automatiquement le navigateur sur http://127.0.0.1:8000
REM  Fermer cette fenetre (ou Ctrl+C) arrete l'application.
REM
REM  Options transmises a l'appli, ex :  start.bat --port 8080 --no-browser
REM ==========================================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] Environnement .venv introuvable : lance d'abord install.bat
    pause
    exit /b 1
)

REM Pas besoin d'"activer" la venv : utiliser directement son python suffit.
".venv\Scripts\python.exe" -m lofima %*

REM Si l'appli s'arrete sur une erreur, on garde la fenetre ouverte pour la lire.
if errorlevel 1 pause
