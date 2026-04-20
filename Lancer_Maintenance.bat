@echo off
title Maintenance CILAM PLF - Recherche Profonde
setlocal enabledelayedexpansion

:: 1. On se place dans le dossier du script
cd /d "%~dp0"

echo Recherche du moteur Python dans WPy64-313110...
echo.

:: 2. Recherche du fichier python.exe dans toute l'arborescence du dossier WinPython
set "PYTHON_EXE="
for /r "%~dp0WPy64-313110" %%f in (python.exe) do (
    if exist "%%f" (
        set "PYTHON_EXE=%%f"
        set "PYTHON_DIR=%%~dpf"
        goto :found
    )
)

:found
if not defined PYTHON_EXE (
    echo [ERREUR] Le fichier python.exe est introuvable.
    echo.
    echo Verifiez que le dossier WPy64-313110 contient bien les fichiers extraits.
    echo Dossier actuel : %~dp0WPy64-313110
    pause
    exit
)

:: 3. Configuration du PATH avec le dossier trouvé
set "PATH=!PYTHON_DIR!;!PYTHON_DIR!\Scripts;%PATH%"

echo -----------------------------------------------------------
echo   LANCEMENT MAINTENANCE CILAM PLF
echo   Moteur trouve : !PYTHON_EXE!
echo -----------------------------------------------------------
echo.

:: 4. Lancement de Streamlit
python -m streamlit run maintenanceplf.py

pause