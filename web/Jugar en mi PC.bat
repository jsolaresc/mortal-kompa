@echo off
REM Abre Mortal Kompa (navegador) en el navegador (necesita Python instalado)
cd /d "%~dp0"
start "" http://localhost:8000/
python -m http.server 8000
