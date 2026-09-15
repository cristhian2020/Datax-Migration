@echo off
title Datax Migration Studio

echo ================================================================
echo            Iniciando Datax Migration Studio (Web)
echo ================================================================
echo.

echo Verificando librerias necesarias...
python -m pip install -r requirements.txt

echo.
echo Abriendo plataforma en tu navegador...
python -m streamlit run app.py

pause
