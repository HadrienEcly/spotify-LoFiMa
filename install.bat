@echo off
REM ==========================================================================
REM  install.bat - Installe tout ce qu'il faut pour LoFiMa (a lancer une fois,
REM  puis a relancer de temps en temps pour mettre a jour yt-dlp).
REM
REM  Etapes :
REM    1. Trouve Python 3.11+
REM    2. Cree l'environnement virtuel .venv (si absent)
REM    3. Installe / met a jour les dependances Python dans .venv
REM    4. Installe ffmpeg avec winget s'il n'est pas deja dans le PATH
REM
REM  (Pas d'accents dans les messages : la console Windows les affiche mal.)
REM ==========================================================================
setlocal
REM Se placer dans le dossier du script, meme si lance depuis ailleurs
cd /d "%~dp0"

REM ---------- 1. Python ----------------------------------------------------
REM On prefere le lanceur "py" (installe avec Python sur Windows), sinon "python".
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [ERREUR] Python introuvable. Installe Python 3.11+ depuis https://www.python.org
    echo          en cochant "Add python.exe to PATH", puis relance install.bat.
    goto :fail
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo [ERREUR] Python 3.11 ou plus recent est requis.
    %PY% --version
    goto :fail
)
echo [1/4] Python OK

REM ---------- 2. Environnement virtuel --------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Creation de l'environnement virtuel .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo [2/4] .venv existe deja
)

REM ---------- 3. Dependances Python -----------------------------------------
REM -U : met a jour les paquets (important pour yt-dlp, que YouTube casse souvent).
echo [3/4] Installation des dependances Python ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -U -r requirements.txt
if errorlevel 1 goto :fail

REM ---------- 4. ffmpeg ------------------------------------------------------
REM ffmpeg n'est pas un paquet Python : il est installe sur le systeme via winget.
where ffmpeg >nul 2>&1
if not errorlevel 1 (
    echo [4/4] ffmpeg deja installe
    goto :done
)
where winget >nul 2>&1
if errorlevel 1 (
    echo [ATTENTION] ffmpeg et winget sont introuvables.
    echo             Installe ffmpeg a la main : https://www.gyan.dev/ffmpeg/builds/
    echo             et ajoute son dossier "bin" au PATH.
    goto :done
)
echo [4/4] Installation de ffmpeg avec winget ...
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo [ATTENTION] L'installation de ffmpeg a echoue. Voir le message ci-dessus.
    goto :done
)
echo.
echo ffmpeg installe. Ferme cette fenetre : le PATH n'est pris en compte
echo que dans les nouvelles fenetres.

:done
echo.
echo Installation terminee. Lance start.bat pour demarrer LoFiMa.
pause
exit /b 0

:fail
echo.
echo Installation interrompue.
pause
exit /b 1
